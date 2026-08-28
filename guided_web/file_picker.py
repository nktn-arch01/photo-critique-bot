"""ネイティブの画像ファイル選択ダイアログ（Mac 優先）。"""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path

_IMAGE_TYPES_MAC = (
    "public.image",
    "JPEG",
    "PNG",
    "HEIC",
    "TIFF",
    "GIF",
    "WEBP",
    "jpg",
    "jpeg",
    "png",
    "heic",
    "tif",
    "tiff",
    "gif",
    "webp",
)


def pick_image_file(initial: Path | None = None) -> Path | None:
    """ユーザーにオリジナル画像を選ばせる。キャンセル時は None。"""
    if platform.system() == "Darwin":
        picked = _pick_image_mac(initial)
        if picked is not None:
            return picked
    return _pick_image_tk(initial)


def _pick_image_mac(initial: Path | None) -> Path | None:
    prompt = "写真を選択"
    type_list = ", ".join(f'"{t}"' for t in _IMAGE_TYPES_MAC)
    if initial and initial.expanduser().is_dir():
        init = initial.expanduser().resolve()
        script = (
            f'POSIX path of (choose file with prompt "{prompt}" '
            f'of type {{{type_list}}} '
            f'default location (POSIX file "{init}"))'
        )
    else:
        script = (
            f'POSIX path of (choose file with prompt "{prompt}" '
            f"of type {{{type_list}}})"
        )
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
    path = Path(text)
    return path if path.is_file() else None


def _pick_image_tk(initial: Path | None) -> Path | None:
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
    kwargs: dict = {
        "title": "写真を選択",
        "filetypes": [
            ("画像", "*.jpg *.jpeg *.png *.heic *.tif *.tiff *.gif *.webp"),
            ("すべて", "*.*"),
        ],
    }
    if initial and initial.expanduser().is_dir():
        kwargs["initialdir"] = str(initial.expanduser().resolve())
    selected = filedialog.askopenfilename(**kwargs)
    root.destroy()
    if not selected:
        return None
    path = Path(selected)
    return path if path.is_file() else None
