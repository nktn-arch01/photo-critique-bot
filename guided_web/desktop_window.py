"""Guided を Mac の .app から起動する。

pywebview / Tk / 署名なしの描画ホスト / JXA applet は使わない。
`.command` と同じ python3 でサーバを立て、`/usr/bin/open` で選ぶ画面を開く。

寿命: 画面があるあいだだけサーバを動かす。
Finder の .app プロセスはサーバを待たない（待ると再起動が跳ね続ける）。
"""

from __future__ import annotations

import os
import platform
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from guided_web.local_server import DEFAULT_PORT, GuidedLocalServer
from guided_web.presence import is_gone as presence_is_gone
from guided_web.shutdown import is_shutdown_requested, request_shutdown


def show_alert(message: str, *, title: str = "Lumina Notes Guided") -> None:
    """Finder 起動でも読める短い案内。デバッグ手順は出さない。"""
    if platform.system() == "Darwin":
        script = (
            f'display dialog {message!r} buttons {{"OK"}} '
            f'default button 1 with title {title!r}'
        )
        try:
            subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
            return
        except OSError:
            pass
    print(message, file=sys.stderr)


def ensure_openai_key_from_home() -> None:
    """Finder 起動は .zshrc を読まない。~/.openai_api_key があれば環境へ載せる。"""
    if os.getenv("OPENAI_API_KEY"):
        return
    key_file = Path.home() / ".openai_api_key"
    if not key_file.is_file():
        return
    try:
        key = key_file.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if key:
        os.environ["OPENAI_API_KEY"] = key


def should_detach() -> bool:
    """Finder .app の PID をサーバ待ちに使わない。再ダブルクリックが新しい起動になる。"""
    if os.environ.get("GUIDED_DAEMON") == "1":
        return False
    if os.environ.get("GUIDED_KEEP_FOREGROUND") == "1":
        return False
    return platform.system() == "Darwin"


def detach_and_exit() -> None:
    """新しいセッションで本体を残し、このプロセスはすぐ終わる。"""
    log_path = Path.home() / ".lumina_notes" / "guided-app.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["GUIDED_DAEMON"] = "1"
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n=== detach {time.strftime('%Y-%m-%d %H:%M:%S')} exe={sys.executable} ===\n")
        log.flush()
        subprocess.Popen(
            [sys.executable, "-m", "guided_web.desktop_window"],
            env=env,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            close_fds=True,
        )
    raise SystemExit(0)


def open_guided_page(url: str) -> None:
    """`.command` と同じくシステム既定のブラウザで開く。描画ホストは自前で持たない。"""
    if platform.system() != "Darwin":
        return
    opener = os.environ.get("GUIDED_WEB_OPENER", "/usr/bin/open")
    stamp = str(int(time.time()))
    sep = "&" if "?" in url else "?"
    subprocess.run([opener, f"{url}{sep}v={stamp}"], check=False)


def wait_until_quit(server: GuidedLocalServer, *, poll_s: float = 0.4) -> None:
    """「終了」、画面の不在、SIGTERM、またはサーバ停止まで待つ。"""
    done = threading.Event()
    previous_int = signal.getsignal(signal.SIGINT)
    previous_term = signal.getsignal(signal.SIGTERM)

    def _stop(_signum=None, _frame=None) -> None:
        done.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    try:
        while not done.is_set():
            if presence_is_gone() and not is_shutdown_requested():
                request_shutdown()
            if is_shutdown_requested() or not server.is_running():
                break
            done.wait(poll_s)
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)


def main() -> int:
    ensure_openai_key_from_home()
    if should_detach():
        detach_and_exit()
    port = int(os.getenv("GUIDED_WEB_PORT", str(DEFAULT_PORT)))
    server = GuidedLocalServer(port)
    try:
        server.start(replace_existing=True)
        server.wait_healthy()
    except Exception as exc:
        show_alert(
            "Guided を起動できませんでした。\n"
            f"{exc}\n"
            "保険として LuminaNotesGuided.command をダブルクリックしてください。"
        )
        server.stop()
        return 1
    try:
        open_guided_page(server.url)
        wait_until_quit(server)
        return 0
    finally:
        server.stop()


if __name__ == "__main__":
    raise SystemExit(main())
