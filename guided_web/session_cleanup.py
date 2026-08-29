"""Guided Web セッションの一時ファイル削除とライフサイクル。

一時ディレクトリ・メモリ上のセッション・講評世代（epoch）を一箇所で扱う。
対症療法の分岐を増やさず、起動・終了・タブ閉じ・DELETE が同じ primitive を使う。
"""

from __future__ import annotations

import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

CRITIQUE_RUNNING = frozenset({"phase1_running", "phase2_running"})


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


def live_temp_dirs(
    sessions: dict[str, dict[str, Any]],
    *,
    root: Path | None = None,
) -> set[Path]:
    """現在のセッションが所有する一時ディレクトリ。"""
    base = (root or guided_temp_root()).resolve()
    live: set[Path] = set()
    for session_id, session in sessions.items():
        live.add((base / session_id).resolve())
        temp_dir = session.get("temp_dir")
        if temp_dir:
            live.add(Path(temp_dir).resolve())
    return live


def purge_orphan_temp(
    sessions: dict[str, dict[str, Any]] | None = None,
    *,
    root: Path | None = None,
) -> list[str]:
    """追跡されていない lumina_guided 配下ディレクトリを削除する。

    起動時（セッション空）はクラッシュ残骸ごと消す。
    実行中は live セッションのディレクトリだけ残す。
    """
    base = root or guided_temp_root()
    if not base.is_dir():
        return []
    live = live_temp_dirs(sessions or {}, root=base)
    removed: list[str] = []
    for child in list(base.iterdir()):
        if not child.is_dir():
            continue
        if child.resolve() in live:
            continue
        remove_tree(child)
        removed.append(child.name)
    return removed


def purge_all_sessions(sessions: dict[str, dict[str, Any]]) -> int:
    """全セッションを pop する。戻り値は削除した件数。"""
    ids = list(sessions)
    for session_id in ids:
        pop_session(sessions, session_id)
    return len(ids)


def shutdown_sessions(
    sessions: dict[str, dict[str, Any]],
    *,
    root: Path | None = None,
) -> dict[str, int | list[str]]:
    """Ctrl+C / プロセス終了時: セッション解放のあと孤児ディレクトリも掃く。"""
    dropped = purge_all_sessions(sessions)
    orphans = purge_orphan_temp(sessions, root=root)
    return {"dropped": dropped, "orphans": orphans}


def ensure_session_lock(session: dict[str, Any]) -> threading.Lock:
    lock = session.get("_lock")
    if lock is None:
        lock = threading.Lock()
        session["_lock"] = lock
    return lock


def bump_epoch(session: dict[str, Any]) -> int:
    epoch = int(session.get("epoch") or 0) + 1
    session["epoch"] = epoch
    return epoch


def is_current_epoch(session: dict[str, Any], epoch: int) -> bool:
    return int(session.get("epoch") or 0) == int(epoch)


def critique_is_running(session: dict[str, Any]) -> bool:
    crit = session.get("critique") or {}
    return crit.get("status") in CRITIQUE_RUNNING
