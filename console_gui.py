"""Wave 3 公式 GUI モジュール名。実装は ``shortlist_gui``（互換再エクスポート）。

``python3 console_gui.py`` / ``LuminaNotesConsole.command`` から起動する。
"""

from __future__ import annotations

from shortlist_gui import *  # noqa: F403
from shortlist_gui import ShortlistApp, main  # noqa: F401

if __name__ == "__main__":
    main()
