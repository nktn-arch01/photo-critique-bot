"""ネイティブの画像ファイル選択ダイアログ（Mac 優先）。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from guided_web.native_dialog import DialogResult, DialogStatus, interpret_osascript, pick_mac_then_optional_tk

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
    return pick_mac_then_optional_tk(_pick_image_mac, _pick_image_tk, initial)


def _pick_image_mac(initial: Path | None) -> DialogResult:
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
    except (OSError, subprocess.TimeoutExpired) as err:
        return interpret_osascript(error=err)
    result = interpret_osascript(proc)
    if result.status is DialogStatus.PICKED and result.path is not None:
        if not result.path.is_file():
            return DialogResult(DialogStatus.CANCELLED)
    return result


def _pick_image_tk(initial: Path | None = None) -> Path | None:
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
