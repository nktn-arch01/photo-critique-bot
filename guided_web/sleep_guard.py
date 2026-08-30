"""演算中だけ Mac のアイドルスリープを止める。待ち時間は止めない。

Finder から起動したアプリは、開いているだけではスリープを止めない。
講評・カード・書き出しなど CPU/API 作業のあいだだけ `caffeinate -i` を握る。
待ち（選ぶ画面、フォルダダイアログ）ではカウントが 0 なので Mac は眠ってよい。

クラッシュ時: `caffeinate -i -w <このプロセス>` なので、Python が死ねば caffeinate も終わる。
"""

from __future__ import annotations

import os
import platform
import subprocess
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

SpawnFn = Callable[[], subprocess.Popen | None]


def _default_enabled() -> bool:
    return platform.system() == "Darwin"


def spawn_caffeinate() -> subprocess.Popen | None:
    """アイドル時スリープだけ防ぐ。ディスプレイ消灯は許可する。"""
    try:
        return subprocess.Popen(
            ["caffeinate", "-i", "-w", str(os.getpid())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError):
        return None


class SleepGuard:
    """入れ子の busy を数え、0↔1 のときだけ caffeinate を開始/終了する。"""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        spawn: SpawnFn | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._count = 0
        self._proc: subprocess.Popen | None = None
        self.enabled = _default_enabled() if enabled is None else enabled
        self._spawn = spawn or spawn_caffeinate

    def hold(self) -> None:
        with self._lock:
            self._count += 1
            if self._count == 1:
                self._start_unlocked()

    def release(self) -> None:
        with self._lock:
            if self._count <= 0:
                self._count = 0
                return
            self._count -= 1
            if self._count == 0:
                self._stop_unlocked()

    def force_release(self) -> None:
        with self._lock:
            self._count = 0
            self._stop_unlocked()

    def is_held(self) -> bool:
        with self._lock:
            return self._count > 0

    def _start_unlocked(self) -> None:
        if not self.enabled:
            return
        if self._proc is not None and self._proc.poll() is None:
            return
        self._spawn_calls = getattr(self, "_spawn_calls", 0) + 1
        self._proc = self._spawn()

    def _stop_unlocked(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

    @contextmanager
    def busy(self) -> Iterator[None]:
        self.hold()
        try:
            yield
        finally:
            self.release()


_guard = SleepGuard()


def busy():
    return _guard.busy()


def force_release() -> None:
    _guard.force_release()


def is_held() -> bool:
    return _guard.is_held()


def reset_guard_for_tests(*, enabled: bool = False, spawn: SpawnFn | None = None) -> SleepGuard:
    """テスト用にグローバルを差し替える。本番コードから呼ばない。"""
    global _guard
    _guard.force_release()
    _guard = SleepGuard(enabled=enabled, spawn=spawn)
    return _guard
