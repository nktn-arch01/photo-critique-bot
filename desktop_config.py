"""デスクトップ GUI 共有設定（~/.photo_ai_config.json）.

講評 GUI（app_gui）と短絡 GUI（shortlist_gui）が同じファイルを使う。
保存時はディスク上の既存キーを消さない（merge 書き込み）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_FILE = Path.home() / ".photo_ai_config.json"


def default_config(desktop: str | None = None) -> dict[str, Any]:
    base_dir = desktop or str(Path.home() / "Desktop")
    return {
        "last_dir": base_dir,
        "shortlist_last_dir": base_dir,
        "works_last_dir": base_dir,
        "force_overwrite": False,
        "card_theme": "dark",
    }


def load_config(path: Path | None = None, *, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    """既存キーをすべて保持したまま読む。"""
    cfg_path = path or CONFIG_FILE
    base = default_config()
    if defaults:
        base.update(defaults)
    if not cfg_path.exists():
        return base
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            base.update(data)
    except Exception:
        pass
    if not base.get("last_dir"):
        base["last_dir"] = default_config()["last_dir"]
    if not base.get("shortlist_last_dir"):
        base["shortlist_last_dir"] = base.get("last_dir")
    if not base.get("works_last_dir"):
        base["works_last_dir"] = base.get("last_dir")
    return base


def save_config_merge(
    updates: dict[str, Any],
    path: Path | None = None,
    *,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """ディスク上の最新と merge して原子的に保存。他 GUI のキーを消さない。"""
    cfg_path = path or CONFIG_FILE
    on_disk: dict[str, Any] = {}
    if cfg_path.exists():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                on_disk = raw
        except Exception:
            on_disk = {}
    merged: dict[str, Any] = {**on_disk}
    if current:
        merged.update(current)
    merged.update(updates)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg_path.with_suffix(cfg_path.suffix + ".tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(cfg_path)
    return merged
