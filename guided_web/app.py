"""Guided Web ローカル API（スパイク）。"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from guided_metadata import build_guided_api_parameters

APP_ROOT = Path(__file__).resolve().parent
STATIC_DIR = APP_ROOT / "static"
DEFAULT_PORT = int(os.getenv("GUIDED_WEB_PORT", "8765"))

app = FastAPI(title="Lumina Notes Guided", version="0.1.0")
_sessions: dict[str, dict] = {}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/session/photo")
async def upload_photo(file: UploadFile = File(...)) -> JSONResponse:
    """写真1枚を受け取り、抽象化パラメータを返す。"""
    suffix = Path(file.filename or "photo.jpg").suffix or ".jpg"
    session_id = uuid.uuid4().hex
    tmp_dir = Path(tempfile.gettempdir()) / "lumina_guided" / session_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dest = tmp_dir / f"upload{suffix}"
    data = await file.read()
    dest.write_bytes(data)

    api_params, metadata, dop_info, meta_block = build_guided_api_parameters(
        dest, image_id=session_id, geocode=False
    )
    _sessions[session_id] = {
        "path": str(dest),
        "metadata": metadata,
        "dop_info": dop_info,
        "meta_block": meta_block,
        "api_params": api_params.to_dict(),
    }
    return JSONResponse(
        {
            "session_id": session_id,
            "api_parameters": api_params.to_dict(),
            "local_meta_preview": {
                "file_name": file.filename,
                "meta_block_lines": meta_block.splitlines()[:12],
            },
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
