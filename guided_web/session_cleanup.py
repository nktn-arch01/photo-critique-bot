"""Guided Web セッションの一時ファイル削除。"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any


def guided_temp_root() -> Path:
    return Path(tempfile.gettempdir()) / "lumina_guided"


def remove_tree(path: Path | str | None) -> None:
    if not path:
        return
    target = Path(path)
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)


def destroy_session_data(session_id: str, session: dict[str, Any]) -> None:
    """セッションに紐づく一時ディレクトリを削除する。"""
    temp_dir = session.get("temp_dir")
    if temp_dir:
        remove_tree(temp_dir)
        return
    for key in ("path", "preview_path", "card_preview_path"):
        value = session.get(key)
        if not value:
            continue
        parent = Path(value).parent
        if parent.is_dir() and parent.name == session_id:
            remove_tree(parent)
            return


def pop_session(sessions: dict[str, dict[str, Any]], session_id: str) -> dict[str, Any] | None:
    """メモリ上のセッションを取り除き、ディスク上の一時ファイルも削除する。"""
    session = sessions.pop(session_id, None)
    if session is not None:
        destroy_session_data(session_id, session)
    return session
