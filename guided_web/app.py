"""Guided Web ローカル API。"""

from __future__ import annotations

import asyncio
import os
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

APP_ROOT = Path(__file__).resolve().parent
STATIC_DIR = APP_ROOT / "static"
DEFAULT_PORT = int(os.getenv("GUIDED_WEB_PORT", "8765"))

app = FastAPI(title="Lumina Notes Guided", version="0.2.0")
_sessions: dict[str, dict] = {}
_executor = ThreadPoolExecutor(max_workers=2)


class CritiqueStartBody(BaseModel):
    lens: str = "self"
    user_note: str = Field(default="", max_length=4000)


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


@app.post("/api/session/photo")
async def upload_photo(file: UploadFile = File(...)) -> JSONResponse:
    suffix = Path(file.filename or "photo.jpg").suffix or ".jpg"
    session_id = uuid.uuid4().hex
    tmp_dir = Path(tempfile.gettempdir()) / "lumina_guided" / session_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dest = tmp_dir / f"upload{suffix}"
    data = await file.read()
    dest.write_bytes(data)

    api_params, metadata, dop_info, meta_block = build_guided_api_parameters(
        dest, image_id=session_id, geocode=True
    )
    preview_path = tmp_dir / "preview.jpg"
    try:
        preview_bytes, _ = prepare_vision_image_bytes(dest)
        preview_path.write_bytes(preview_bytes)
    except Exception:
        preview_path = dest

    _sessions[session_id] = {
        "path": str(dest),
        "preview_path": str(preview_path),
        "metadata": metadata,
        "dop_info": dop_info,
        "meta_block": meta_block,
        "api_params": api_params.to_dict(),
        "critique": {"status": "idle"},
    }
    return JSONResponse(
        {
            "session_id": session_id,
            "preview_url": f"/api/session/{session_id}/preview",
            "api_parameters": api_params.to_dict(),
            "local_meta_preview": {
                "file_name": file.filename,
                "meta_block_lines": meta_block.splitlines()[:12],
            },
        }
    )


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
