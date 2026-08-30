"""Guided 画面がまだあるか。

ブラウザは見るだけ。Python サーバがアプリ本体。
画面があるあいだだけサーバを動かしてよい、が単一の規則。

- ping: 画面がある（定期ハートビート）
- mark_unload: 画面が閉じようとしている（タブ閉じ／更新）。短い猶予のあと不在
- idle: ハートビートが途絶（ブラウザ終了など）

明示の「終了」は shutdown.request_shutdown。こちらは「画面が消えた」。
TestClient では待受ループを回さない（pytest を止めない）。
"""
from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable

_DEFAULT_UNLOAD_S = 8.0
_DEFAULT_IDLE_S = 90.0


def _unload_grace_s() -> float:
    raw = os.getenv("GUIDED_UNLOAD_GRACE_S")
    if raw:
        return float(raw)
    return _DEFAULT_UNLOAD_S


def _idle_grace_s() -> float:
    raw = os.getenv("GUIDED_IDLE_GRACE_S")
    if raw:
        return float(raw)
    return _DEFAULT_IDLE_S


class Presence:
    def __init__(
        self,
        *,
        now: Callable[[], float] | None = None,
        unload_grace_s: float | None = None,
        idle_grace_s: float | None = None,
    ) -> None:
        self._now = now or time.monotonic
        self._unload_grace_s = unload_grace_s
        self._idle_grace_s = idle_grace_s
        self._lock = threading.Lock()
        self._last_ping = self._now()
        self._unload_at: float | None = None

    def reset(self) -> None:
        with self._lock:
            self._last_ping = self._now()
            self._unload_at = None

    def ping(self) -> None:
        with self._lock:
            self._last_ping = self._now()
            self._unload_at = None

    def mark_unload(self) -> None:
        grace = self._unload_grace_s if self._unload_grace_s is not None else _unload_grace_s()
        with self._lock:
            self._unload_at = self._now() + grace

    def is_gone(self) -> bool:
        now = self._now()
        idle = self._idle_grace_s if self._idle_grace_s is not None else _idle_grace_s()
        with self._lock:
            if self._unload_at is not None and now >= self._unload_at:
                return True
            return (now - self._last_ping) >= idle


_presence = Presence()


def reset() -> None:
    _presence.reset()


def ping() -> None:
    _presence.ping()


def mark_unload() -> None:
    _presence.mark_unload()


def is_gone() -> bool:
    return _presence.is_gone()
