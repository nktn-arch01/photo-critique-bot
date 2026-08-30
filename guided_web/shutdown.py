"""Cooperative shutdown for Guided Web.

POST /api/shutdown (画面の「終了」) sets this event.
desktop_window.wait_until_quit and the .command uvicorn watcher wait on it.

Must not os.kill — FastAPI TestClient shares the pytest process.
"""
from __future__ import annotations

import threading

_shutdown = threading.Event()


def request_shutdown() -> None:
    _shutdown.set()


def is_shutdown_requested() -> bool:
    return _shutdown.is_set()


def clear_shutdown() -> None:
    _shutdown.clear()
