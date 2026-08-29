"""ネイティブダイアログの結果。キャンセルと「使えない」を混ぜない。

Mac で osascript が動いたあとに Tk へ落とすと、ワーカースレッド上の
tk.Tk() がプロセスごと abort する（Python 3.14 / Tk 9）。
キャンセルは「選ばなかった」であり、フォールバック対象ではない。
"""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable


class DialogStatus(str, Enum):
    PICKED = "picked"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class DialogResult:
    status: DialogStatus
    path: Path | None = None

    @property
    def picked_path(self) -> Path | None:
        if self.status is DialogStatus.PICKED:
            return self.path
        return None


def interpret_osascript(
    proc: subprocess.CompletedProcess[str] | None = None,
    *,
    error: BaseException | None = None,
) -> DialogResult:
    """osascript の終了を picked / cancelled / unavailable に正規化する。"""
    if error is not None:
        if isinstance(error, FileNotFoundError):
            return DialogResult(DialogStatus.UNAVAILABLE)
        if isinstance(error, subprocess.TimeoutExpired):
            return DialogResult(DialogStatus.CANCELLED)
        if isinstance(error, OSError):
            return DialogResult(DialogStatus.UNAVAILABLE)
        return DialogResult(DialogStatus.UNAVAILABLE)
    if proc is None:
        return DialogResult(DialogStatus.UNAVAILABLE)
    if proc.returncode != 0:
        return DialogResult(DialogStatus.CANCELLED)
    text = (proc.stdout or "").strip().rstrip("/")
    if not text:
        return DialogResult(DialogStatus.CANCELLED)
    return DialogResult(DialogStatus.PICKED, Path(text))


def pick_mac_then_optional_tk(
    mac_pick: Callable[[Path | None], DialogResult],
    tk_pick: Callable[[Path | None], Path | None],
    initial: Path | None,
) -> Path | None:
    """Darwin では osascript が使えた（キャンセル含む）ら Tk に落ちない。"""
    if platform.system() == "Darwin":
        result = mac_pick(initial)
        if result.status is not DialogStatus.UNAVAILABLE:
            return result.picked_path
    return tk_pick(initial)
