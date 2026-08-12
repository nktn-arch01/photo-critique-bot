"""デスクトップ GUI 共通の UI スレッド安全ヘルパ（L1）.

ワーカーから ``root.after`` する前にウィンドウ生存を確認する。
閉じたあとの ``TclError`` を握りつぶし、処理スレッドは静かに終わる。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    from tkinter import TclError as _TclError
except ImportError:  # ヘッドレス CI 等（GUI 本体は別途 tk が必要）
    class _TclError(Exception):
        """tkinter 非導入時のスタブ。"""


def schedule_on_ui(root: Any, fn: Callable[[], None]) -> bool:
    """メインスレッドへ ``fn`` を予約する。ウィンドウが無ければ何もしない。

    Returns:
        True なら予約できた。False なら破棄済み／Tk エラー。
    """
    try:
        if root is None:
            return False
        if not bool(root.winfo_exists()):
            return False
        root.after(0, fn)
        return True
    except _TclError:
        return False


def open_in_file_manager(path: Any) -> None:
    """Finder / ファイルマネージャでフォルダ（または親）を開く。

    macOS は ``open``、その他は ``xdg-open``。失敗時は例外を投げる。
    """
    import subprocess
    from pathlib import Path

    target = Path(path).expanduser().resolve()
    if target.is_file():
        target = target.parent
    if not target.is_dir():
        raise NotADirectoryError(f"フォルダがありません: {target}")
    try:
        subprocess.run(["open", str(target)], check=False)
    except Exception:
        subprocess.run(["xdg-open", str(target)], check=False)
