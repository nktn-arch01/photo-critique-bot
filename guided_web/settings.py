"""Guided Web ローカル設定（保存先フォルダなど）。"""

from __future__ import annotations

import json
from pathlib import Path

_SETTINGS_PATH = Path.home() / ".lumina_notes" / "guided_settings.json"
_DEFAULT_SUGGESTED = Path.home() / "Pictures" / "LuminaNotes" / "Guided"


def default_suggested_folder() -> Path:
    return _DEFAULT_SUGGESTED


def load_settings() -> dict:
    if not _SETTINGS_PATH.is_file():
        return {}
    try:
        return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_save_folder() -> Path | None:
    raw = load_settings().get("save_folder")
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    return path if path.is_dir() else None


def set_save_folder(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    data = load_settings()
    data["save_folder"] = str(resolved)
    save_settings(data)
    return resolved
