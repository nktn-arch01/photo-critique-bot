"""Guided Web ローカル API。"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ai_vision import prepare_vision_image_bytes
from guided_metadata import build_guided_api_parameters
from guided_web.critique_runner import run_phase1, run_phase2
from guided_web.file_picker import pick_image_file
from guided_web.folder_picker import pick_folder
from guided_web.parameter_display import build_parameter_display
from guided_web.settings import (
    default_suggested_folder,
    get_save_folder,
    set_save_folder,
)
from guided_web.stock_export import export_guided_session, render_card_preview, critique_text_for_session
from guided_web.reflect_prompts import REFLECTION_GROUPS

APP_ROOT = Path(__file__).resolve().parent
STATIC_DIR = APP_ROOT / "static"
DEFAULT_PORT = int(os.getenv("GUIDED_WEB_PORT", "8765"))

app = FastAPI(title="Lumina Notes Guided", version="0.2.0")
_sessions: dict[str, dict] = {}
_executor = ThreadPoolExecutor(max_workers=2)


class CritiqueStartBody(BaseModel):
    lens: str = "self"
    user_note: str = Field(default="", max_length=4000)


class CardPreviewBody(BaseModel):
    card_theme: str = "dark"
    user_stars: int = Field(ge=0, le=5, default=0)
    user_note: str = Field(default="", max_length=4000)


class ReflectionItemBody(BaseModel):
    checked: bool = False
    text: str = Field(default="", max_length=4000)
    label: str = Field(default="", max_length=200)


class ExportBody(BaseModel):
    user_stars: int = Field(ge=1, le=5)
    card_theme: str = "dark"
    user_note: str = Field(default="", max_length=4000)
    reflections: dict[str, ReflectionItemBody] = Field(default_factory=dict)


class SaveFolderBody(BaseModel):
    save_folder: str


def _critique_public(sess: dict) -> dict[str, Any]:
    c = sess.get("critique") or {"status": "idle"}
    out: dict[str, Any] = {
        "status": c.get("status", "idle"),
        "error": c.get("error"),
        "lens": c.get("lens"),
    }
    if c.get("phase1_parsed"):
        p1 = c["phase1_parsed"]
        out["phase1"] = {
            "title": p1.get("title"),
            "summary": p1.get("summary"),
            "critique_summary": p1.get("point_text"),
            "scores": p1.get("scores"),
        }
    if c.get("sections") is not None:
        out["sections"] = c.get("sections")
    if c.get("full_parsed"):
        fp = c["full_parsed"]
        out["body"] = fp.get("body")
    return out


def _finish_phase2(session_id: str, lens: str, user_note: str, phase1_text: str) -> None:
    sess = _sessions.get(session_id)
    if not sess:
        return
    try:
        full, parsed, sections = run_phase2(
            Path(sess["path"]),
            sess["metadata"],
            sess["dop_info"],
            phase1_text,
            lens=lens,
            user_note=user_note,
        )
        sess["critique"].update(
            {
                "status": "complete",
                "full_raw": full,
                "full_parsed": parsed,
                "sections": sections,
            }
        )
    except Exception as e:
        sess["critique"]["status"] = "error"
        sess["critique"]["error"] = str(e)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _build_photo_session(
    source_path: Path,
    *,
    original_path: str,
    original_filename: str,
) -> tuple[str, dict[str, Any]]:
    """画像ファイルからセッションを作成し登録する。"""
    session_id = uuid.uuid4().hex
    tmp_dir = Path(tempfile.gettempdir()) / "lumina_guided" / session_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_path.suffix or ".jpg"
    dest = tmp_dir / f"upload{suffix}"
    if source_path.resolve() != dest.resolve():
        shutil.copy2(source_path, dest)
    else:
        dest = source_path

    api_params, metadata, dop_info, meta_block = build_guided_api_parameters(
        dest, image_id=session_id, geocode=True
    )
    preview_path = tmp_dir / "preview.jpg"
    try:
        preview_bytes, _ = prepare_vision_image_bytes(dest)
        preview_path.write_bytes(preview_bytes)
    except Exception:
        preview_path = dest

    session = {
        "path": str(dest),
        "preview_path": str(preview_path),
        "original_filename": original_filename,
        "original_path": original_path,
        "metadata": metadata,
        "dop_info": dop_info,
        "meta_block": meta_block,
        "api_params": api_params.to_dict(),
        "critique": {"status": "idle"},
        "card_preview_path": None,
        "card_preview_theme": None,
    }
    _sessions[session_id] = session
    return session_id, session


def _photo_session_response(session_id: str, session: dict[str, Any]) -> dict[str, Any]:
    original_filename = session["original_filename"]
    return {
        "session_id": session_id,
        "preview_url": f"/api/session/{session_id}/preview",
        "file_name": original_filename,
        "original_path": session.get("original_path") or original_filename,
        "api_parameters": session["api_params"],
        "parameter_display": build_parameter_display(
            session["api_params"],
            file_name=original_filename,
        ),
        "local_meta_preview": {
            "file_name": original_filename,
            "meta_block_lines": (session.get("meta_block") or "").splitlines()[:12],
        },
    }


@app.post("/api/session/photo")
async def upload_photo(file: UploadFile = File(...)) -> JSONResponse:
    suffix = Path(file.filename or "photo.jpg").suffix or ".jpg"
    tmp_dir = Path(tempfile.gettempdir()) / "lumina_guided" / f"upload_{uuid.uuid4().hex}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dest = tmp_dir / f"upload{suffix}"
    data = await file.read()
    dest.write_bytes(data)

    original_filename = file.filename or dest.name
    session_id, session = _build_photo_session(
        dest,
        original_path=original_filename,
        original_filename=original_filename,
    )
    return JSONResponse(_photo_session_response(session_id, session))


@app.post("/api/session/photo-pick")
async def pick_photo() -> JSONResponse:
    """Mac 等のネイティブダイアログで写真を選び、オリジナルのフルパスを記録する。"""
    loop = asyncio.get_running_loop()
    initial = get_save_folder() or default_suggested_folder()
    picked = await loop.run_in_executor(
        _executor,
        lambda: pick_image_file(initial.parent if initial and initial.is_file() else initial),
    )
    if picked is None:
        raise HTTPException(status_code=400, detail="photo not selected")

    source = picked.expanduser().resolve()
    if not source.is_file():
        raise HTTPException(status_code=400, detail="photo not found")

    session_id, session = _build_photo_session(
        source,
        original_path=str(source),
        original_filename=source.name,
    )
    return JSONResponse(_photo_session_response(session_id, session))


@app.post("/api/session/{session_id}/critique")
async def start_critique(
    session_id: str,
    body: CritiqueStartBody,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")

    crit = sess.get("critique") or {}
    if crit.get("status") == "complete" and crit.get("lens") == body.lens:
        return JSONResponse(_critique_public(sess))

    sess["critique"] = {
        "status": "phase1_running",
        "lens": body.lens,
        "user_note": body.user_note,
        "error": None,
    }

    loop = asyncio.get_running_loop()
    try:
        phase1_text, phase1_parsed = await loop.run_in_executor(
            _executor,
            lambda: run_phase1(
                Path(sess["path"]),
                sess["metadata"],
                sess["dop_info"],
                lens=body.lens,
                user_note=body.user_note,
            ),
        )
    except Exception as e:
        sess["critique"] = {
            "status": "error",
            "error": str(e),
            "lens": body.lens,
        }
        return JSONResponse(_critique_public(sess), status_code=500)

    sess["critique"].update(
        {
            "status": "phase2_running",
            "phase1_raw": phase1_text,
            "phase1_parsed": phase1_parsed,
        }
    )
    background_tasks.add_task(
        _finish_phase2, session_id, body.lens, body.user_note, phase1_text
    )
    return JSONResponse(_critique_public(sess))


@app.get("/api/session/{session_id}/critique")
def get_critique_status(session_id: str) -> JSONResponse:
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    return JSONResponse(_critique_public(sess))


@app.get("/api/session/{session_id}/preview")
def session_preview(session_id: str) -> FileResponse:
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    path = Path(sess["preview_path"])
    if not path.is_file():
        path = Path(sess["path"])
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/reflect-items")
def reflect_items() -> JSONResponse:
    return JSONResponse(
        {
            "groups": [
                {
                    "id": g["id"],
                    "label": g["label"],
                    "items": [{"id": i["id"], "label": i["label"]} for i in g["items"]],
                }
                for g in REFLECTION_GROUPS
            ]
        }
    )


@app.get("/api/settings")
def get_settings() -> JSONResponse:
    folder = get_save_folder()
    suggested = default_suggested_folder()
    return JSONResponse(
        {
            "save_folder": str(folder) if folder else None,
            "suggested_folder": str(suggested),
        }
    )


@app.post("/api/settings/save-folder")
def save_folder_setting(body: SaveFolderBody) -> JSONResponse:
    path = Path(body.save_folder).expanduser()
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="folder not found")
    resolved = set_save_folder(path)
    return JSONResponse({"save_folder": str(resolved)})


@app.post("/api/settings/pick-folder")
async def pick_save_folder() -> JSONResponse:
    loop = asyncio.get_running_loop()
    initial = get_save_folder() or default_suggested_folder()
    picked = await loop.run_in_executor(_executor, lambda: pick_folder(initial))
    if picked is None:
        raise HTTPException(status_code=400, detail="folder not selected")
    resolved = set_save_folder(picked)
    return JSONResponse({"save_folder": str(resolved)})


@app.post("/api/session/{session_id}/card")
async def generate_card_preview(session_id: str, body: CardPreviewBody) -> JSONResponse:
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    crit = sess.get("critique") or {}
    if crit.get("status") not in {"complete", "phase2_running"} and not crit.get("phase1_raw"):
        raise HTTPException(status_code=400, detail="critique not ready")

    tmp_dir = Path(sess["path"]).parent
    card_path = tmp_dir / "card_preview.png"
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            _executor,
            lambda: render_card_preview(
                sess,
                card_path,
                card_theme=body.card_theme,
                user_stars=body.user_stars,
                user_note=body.user_note,
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    sess["card_preview_path"] = str(card_path)
    sess["card_preview_theme"] = body.card_theme
    return JSONResponse({"card_url": f"/api/session/{session_id}/card/image"})


@app.get("/api/session/{session_id}/card/image")
def session_card_image(session_id: str) -> FileResponse:
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    path = sess.get("card_preview_path")
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="card preview not found")
    return FileResponse(path, media_type="image/png")


@app.post("/api/session/{session_id}/export")
async def export_session(session_id: str, body: ExportBody) -> JSONResponse:
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")

    try:
        critique_text_for_session(sess)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    loop = asyncio.get_running_loop()
    initial = get_save_folder() or default_suggested_folder()
    save_root = await loop.run_in_executor(_executor, lambda: pick_folder(initial))
    if save_root is None:
        raise HTTPException(status_code=400, detail="保存先が選ばれませんでした")

    reflections = {
        key: item.model_dump() for key, item in body.reflections.items()
    }

    try:
        files = await loop.run_in_executor(
            _executor,
            lambda: export_guided_session(
                sess,
                save_dir=save_root,
                user_stars=body.user_stars,
                card_theme=body.card_theme,
                user_note=body.user_note,
                reflections=reflections,
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    set_save_folder(save_root)

    return JSONResponse(
        {
            "export_path": files["export_dir"],
            "files": files,
        }
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def main() -> None:
    import uvicorn

    uvicorn.run("guided_web.app:app", host="127.0.0.1", port=DEFAULT_PORT, reload=False)


if __name__ == "__main__":
    main()
