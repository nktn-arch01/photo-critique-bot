"""Guided Web ローカル API。"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError

from ai_vision import prepare_vision_image_bytes
from guided_metadata import build_guided_api_parameters
from guided_web.critique_runner import run_phase1, run_phase2
from guided_web.file_picker import pick_image_file
from guided_web.folder_picker import pick_folder
from guided_web.parameter_display import build_parameter_display
from guided_web.reflect_prompts import REFLECTION_GROUPS
from guided_web.settings import (
    default_photo_folder,
    default_suggested_folder,
    get_photo_folder,
    get_save_folder,
    remember_photo_source,
    set_save_folder,
)
from guided_web.stock_export import export_guided_session, render_card_preview, critique_text_for_session
from guided_web.session_cleanup import (
    bump_epoch,
    cancel_critique,
    critique_is_running,
    ensure_session_lock,
    is_current_epoch,
    pop_session,
    purge_orphan_temp,
    remove_tree,
    shutdown_sessions,
)

APP_ROOT = Path(__file__).resolve().parent
STATIC_DIR = APP_ROOT / "static"
DEFAULT_PORT = int(os.getenv("GUIDED_WEB_PORT", "8765"))

_sessions: dict[str, dict] = {}
_critique_executor: ThreadPoolExecutor | None = None
_ui_executor: ThreadPoolExecutor | None = None


def _make_pool(name: str) -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix=name)


def _get_critique_executor() -> ThreadPoolExecutor:
    """Vision / 講評 / カード。ピッカーと共有しない。"""
    global _critique_executor
    if _critique_executor is None or getattr(_critique_executor, "_shutdown", False):
        _critique_executor = _make_pool("guided-ai")
    return _critique_executor


def _get_ui_executor() -> ThreadPoolExecutor:
    """写真・フォルダ選択。AI 待ちで UI が止まらない。"""
    global _ui_executor
    if _ui_executor is None or getattr(_ui_executor, "_shutdown", False):
        _ui_executor = _make_pool("guided-ui")
    return _ui_executor


def _shutdown_executors() -> None:
    global _critique_executor, _ui_executor
    for pool in (_critique_executor, _ui_executor):
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
    _critique_executor = None
    _ui_executor = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """起動時に孤児 temp を掃き、終了時（Ctrl+C）に全セッションを解放する。"""
    purge_orphan_temp(_sessions)
    try:
        yield
    finally:
        shutdown_sessions(_sessions)
        _shutdown_executors()


app = FastAPI(title="Lumina Notes Guided", version="0.3.0", lifespan=lifespan)


class CritiqueStartBody(BaseModel):
    lens: str = "self"
    user_note: str = Field(default="", max_length=4000)
    force_restart: bool = False


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
        "epoch": int(sess.get("epoch") or 0),
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


async def _run_phase1_then_phase2(
    session_id: str,
    lens: str,
    user_note: str,
    epoch: int,
) -> None:
    """Phase 1 を裏で走らせ、成功したら Phase 2 へ。HTTP 応答は待たない。"""
    sess = _sessions.get(session_id)
    if not sess or not is_current_epoch(sess, epoch):
        return
    loop = asyncio.get_running_loop()
    try:
        phase1_text, phase1_parsed = await loop.run_in_executor(
            _get_critique_executor(),
            lambda: run_phase1(
                Path(sess["path"]),
                sess["api_params"],
                lens=lens,
                user_note=user_note,
                session_id=session_id,
            ),
        )
    except Exception as e:
        with ensure_session_lock(sess):
            if is_current_epoch(sess, epoch) and session_id in _sessions:
                sess["critique"] = {
                    "status": "error",
                    "error": str(e),
                    "lens": lens,
                }
        return
    with ensure_session_lock(sess):
        if session_id not in _sessions or not is_current_epoch(sess, epoch):
            return
        sess["critique"].update(
            {
                "status": "phase2_running",
                "phase1_raw": phase1_text,
                "phase1_parsed": phase1_parsed,
            }
        )
    await _finish_phase2(session_id, lens, user_note, phase1_text, epoch)


async def _finish_phase2(
    session_id: str,
    lens: str,
    user_note: str,
    phase1_text: str,
    epoch: int,
) -> None:
    sess = _sessions.get(session_id)
    if not sess or not is_current_epoch(sess, epoch):
        return
    loop = asyncio.get_running_loop()
    try:
        full, parsed, sections = await loop.run_in_executor(
            _get_critique_executor(),
            lambda: run_phase2(
                Path(sess["path"]),
                sess["api_params"],
                phase1_text,
                lens=lens,
                user_note=user_note,
                session_id=session_id,
            ),
        )
        with ensure_session_lock(sess):
            if not is_current_epoch(sess, epoch):
                return
            sess["critique"].update(
                {
                    "status": "complete",
                    "full_raw": full,
                    "full_parsed": parsed,
                    "sections": sections,
                }
            )
    except Exception as e:
        with ensure_session_lock(sess):
            if not is_current_epoch(sess, epoch):
                return
            sess["critique"]["status"] = "error"
            sess["critique"]["error"] = str(e)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _assert_readable_image(path: Path) -> None:
    """読めないファイルをセッションにしない（トーストの失敗通知と対）。"""
    try:
        with Image.open(path) as image:
            image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="unreadable image") from exc


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
    try:
        if source_path.resolve() != dest.resolve():
            shutil.copy2(source_path, dest)
        else:
            dest = source_path
        _assert_readable_image(dest)

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
            "temp_dir": str(tmp_dir),
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
    except Exception:
        remove_tree(tmp_dir)
        raise


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
    staging_dir = Path(tempfile.gettempdir()) / "lumina_guided" / f"upload_{uuid.uuid4().hex}"
    staging_dir.mkdir(parents=True, exist_ok=True)
    dest = staging_dir / f"upload{suffix}"
    try:
        data = await file.read()
        dest.write_bytes(data)
        original_filename = file.filename or dest.name
        session_id, session = _build_photo_session(
            dest,
            original_path=original_filename,
            original_filename=original_filename,
        )
        return JSONResponse(_photo_session_response(session_id, session))
    finally:
        remove_tree(staging_dir)


@app.post("/api/session/photo-pick")
async def pick_photo() -> JSONResponse:
    """Mac 等のネイティブダイアログで写真を選び、オリジナルのフルパスを記録する。"""
    loop = asyncio.get_running_loop()
    initial = get_photo_folder() or default_photo_folder()
    picked = await loop.run_in_executor(
        _get_ui_executor(),
        lambda: pick_image_file(initial),
    )
    if picked is None:
        raise HTTPException(status_code=400, detail="photo not selected")

    source = picked.expanduser().resolve()
    if not source.is_file():
        raise HTTPException(status_code=400, detail="photo not found")

    remember_photo_source(source)
    session_id, session = _build_photo_session(
        source,
        original_path=str(source),
        original_filename=source.name,
    )
    return JSONResponse(_photo_session_response(session_id, session))


def _release_session(session_id: str) -> JSONResponse:
    """セッション解放。未存在でも 200（タブ閉じ・二重呼び出しに耐える）。"""
    pop_session(_sessions, session_id)
    return JSONResponse({"ok": True})


@app.delete("/api/session/{session_id}")
def delete_session(session_id: str) -> JSONResponse:
    return _release_session(session_id)


@app.post("/api/session/{session_id}/release")
def release_session(session_id: str) -> JSONResponse:
    """sendBeacon / keepalive 用。DELETE と同じ解放。"""
    return _release_session(session_id)


@app.post("/api/session/{session_id}/critique")
async def start_critique(
    session_id: str,
    body: CritiqueStartBody,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")

    lock = ensure_session_lock(sess)
    with lock:
        crit = sess.get("critique") or {}
        if (
            not body.force_restart
            and crit.get("status") == "complete"
            and crit.get("lens") == body.lens
        ):
            return JSONResponse(_critique_public(sess))
        if critique_is_running(sess) and not body.force_restart:
            return JSONResponse(_critique_public(sess), status_code=409)
        epoch = bump_epoch(sess)
        sess["critique"] = {
            "status": "phase1_running",
            "lens": body.lens,
            "user_note": body.user_note,
            "error": None,
        }

    background_tasks.add_task(
        _run_phase1_then_phase2, session_id, body.lens, body.user_note, epoch
    )
    return JSONResponse(_critique_public(sess))


@app.post("/api/session/{session_id}/critique/cancel")
def cancel_session_critique(
    session_id: str,
    epoch: int | None = Query(default=None),
) -> JSONResponse:
    """もう一度／タブ離脱。写真は残し、進行中の講評だけ無効化する。"""
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    cancel_critique(sess, epoch=epoch)
    return JSONResponse(_critique_public(sess))


@app.post("/api/session/{session_id}/critique/phase2/retry")
async def retry_phase2(session_id: str, background_tasks: BackgroundTasks) -> JSONResponse:
    """Phase1 を維持したまま Phase2 のみ再実行する（タイムアウト・失敗時の復帰）。"""
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")

    lock = ensure_session_lock(sess)
    with lock:
        crit = sess.get("critique") or {}
        if crit.get("status") == "complete":
            return JSONResponse(_critique_public(sess))
        if crit.get("status") == "phase2_running":
            return JSONResponse(_critique_public(sess))
        phase1_text = crit.get("phase1_raw")
        if not phase1_text:
            raise HTTPException(status_code=400, detail="phase1 not available")
        lens = crit.get("lens") or "self"
        user_note = crit.get("user_note") or ""
        epoch = bump_epoch(sess)
        sess["critique"]["status"] = "phase2_running"
        sess["critique"]["error"] = None
    background_tasks.add_task(_finish_phase2, session_id, lens, user_note, phase1_text, epoch)
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
                    "column": g.get("column", "left"),
                    "items": [{"id": i["id"], "label": i["label"]} for i in g["items"]],
                }
                for g in REFLECTION_GROUPS
            ]
        }
    )


@app.get("/api/settings")
def get_settings() -> JSONResponse:
    folder = get_save_folder()
    photo = get_photo_folder()
    return JSONResponse(
        {
            "save_folder": str(folder) if folder else None,
            "photo_folder": str(photo) if photo else None,
            "suggested_folder": str(default_suggested_folder()),
            "suggested_photo_folder": str(default_photo_folder()),
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
    picked = await loop.run_in_executor(_get_ui_executor(), lambda: pick_folder(initial))
    if picked is None:
        return JSONResponse({"ok": False, "cancelled": True})
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
            _get_critique_executor(),
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
    save_root = await loop.run_in_executor(_get_ui_executor(), lambda: pick_folder(initial))
    if save_root is None:
        return JSONResponse({"ok": False, "cancelled": True})

    reflections = {
        key: item.model_dump() for key, item in body.reflections.items()
    }

    try:
        files = await loop.run_in_executor(
            _get_critique_executor(),
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
