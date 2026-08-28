"""ネイティブのフォルダ選択ダイアログ（Mac 優先）。"""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path


def pick_folder(initial: Path | None = None) -> Path | None:
    """ユーザーに保存先フォルダを選ばせる。キャンセル時は None。"""
    if platform.system() == "Darwin":
        picked = _pick_folder_mac(initial)
        if picked is not None:
            return picked
    return _pick_folder_tk(initial)


def _pick_folder_mac(initial: Path | None) -> Path | None:
    prompt = "Note の保存先フォルダを選択"
    if initial and initial.expanduser().is_dir():
        init = initial.expanduser().resolve()
        script = (
            f'POSIX path of (choose folder with prompt "{prompt}" '
            f'default location (POSIX file "{init}"))'
        )
    else:
        script = f'POSIX path of (choose folder with prompt "{prompt}")'
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    text = (proc.stdout or "").strip()
    if not text:
        return None
    return Path(text.rstrip("/"))


def _pick_folder_tk(initial: Path | None) -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    kwargs: dict = {"title": "Note の保存先フォルダを選択"}
    if initial and initial.expanduser().is_dir():
        kwargs["initialdir"] = str(initial.expanduser().resolve())
    selected = filedialog.askdirectory(**kwargs)
    root.destroy()
    if not selected:
        return None
    return Path(selected)
