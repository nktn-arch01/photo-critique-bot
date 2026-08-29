"""Guided Web ローカル設定（保存先フォルダなど）。"""

from __future__ import annotations

import json
from pathlib import Path

_SETTINGS_PATH = Path.home() / ".lumina_notes" / "guided_settings.json"
_DEFAULT_EXPORT = Path.home() / "Pictures" / "LuminaNotes" / "Guided"
SAVE_FOLDER_KEY = "save_folder"
PHOTO_FOLDER_KEY = "photo_folder"


def default_suggested_folder() -> Path:
    """Note 書き出しの初期候補。写真選択とは別。"""
    return _DEFAULT_EXPORT


def default_photo_folder() -> Path:
    """写真選択の初期候補。書き出し先とは別。"""
    pictures = Path.home() / "Pictures"
    return pictures if pictures.is_dir() else Path.home()


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


def _get_folder(key: str) -> Path | None:
    raw = load_settings().get(key)
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    return path if path.is_dir() else None


def _set_folder(key: str, path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError("フォルダが存在しません")
    data = load_settings()
    data[key] = str(resolved)
    save_settings(data)
    return resolved


def get_save_folder() -> Path | None:
    return _get_folder(SAVE_FOLDER_KEY)


def set_save_folder(path: Path) -> Path:
    """最後に使った Note 書き出し先を記憶する（フォルダ自体は作らない）。"""
    return _set_folder(SAVE_FOLDER_KEY, path)


def get_photo_folder() -> Path | None:
    return _get_folder(PHOTO_FOLDER_KEY)


def set_photo_folder(path: Path) -> Path:
    """最後に写真を選んだフォルダを記憶する。書き出し先とは独立。"""
    return _set_folder(PHOTO_FOLDER_KEY, path)


def remember_photo_source(path: Path) -> Path | None:
    """ネイティブ選択した写真の親フォルダを記憶。一時ディレクトリは除外。"""
    target = path.expanduser()
    folder = target if target.is_dir() else target.parent
    if not folder.is_dir():
        return None
    if "lumina_guided" in folder.parts:
        return None
    return set_photo_folder(folder)
