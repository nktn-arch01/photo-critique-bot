"""Guided のローカル HTTP サーバ（.app 起動とテストで共用）。

127.0.0.1 のみ。終了時のセッション掃除は FastAPI lifespan に任せる。
"""

from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from guided_web.presence import reset as reset_presence
from guided_web.shutdown import clear_shutdown
from guided_web.sleep_guard import force_release

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = int(os.getenv("GUIDED_WEB_PORT", "8765"))


def listening_pids(port: int) -> list[int]:
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    pids: list[int] = []
    for line in out.split():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def stop_listeners(port: int, *, timeout_s: float = 2.0) -> None:
    pids = listening_pids(port)
    if not pids:
        return
    for pid in pids:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not listening_pids(port):
            return
        time.sleep(0.1)
    for pid in listening_pids(port):
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((DEFAULT_HOST, 0))
        return int(sock.getsockname()[1])


class GuidedLocalServer:
    """uvicorn をバックグラウンドスレッドで動かす。"""

    def __init__(self, port: int | None = None) -> None:
        self.port = DEFAULT_PORT if port is None else int(port)
        self.host = DEFAULT_HOST
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, *, replace_existing: bool = True) -> None:
        clear_shutdown()
        reset_presence()
        if replace_existing:
            stop_listeners(self.port)
        config = uvicorn.Config(
            "guided_web.app:app",
            host=self.host,
            port=self.port,
            log_level="info",
            lifespan="on",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run,
            name="guided-uvicorn",
            daemon=True,
        )
        self._thread.start()

    def wait_healthy(self, *, timeout_s: float = 10.0) -> None:
        deadline = time.time() + timeout_s
        health = self.url + "api/health"
        last_error = "timeout"
        while time.time() < deadline:
            try:
                with urlopen(health, timeout=0.4) as resp:
                    if resp.status == 200:
                        return
            except (URLError, OSError, TimeoutError) as exc:
                last_error = str(exc)
            if self._thread is not None and not self._thread.is_alive():
                raise RuntimeError("Guided サーバが起動直後に停止しました。")
            time.sleep(0.15)
        raise RuntimeError(f"Guided サーバが応答しません: {last_error}")

    def stop(self) -> None:
        force_release()
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=8)
        force_release()
