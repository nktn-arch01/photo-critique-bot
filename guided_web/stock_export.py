"""Guided Web のストック書き出し（カード・Note・session.json）。"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_vision import prepare_vision_image_bytes
from card_theme import normalize_card_theme
from guided_web.guided_card import create_guided_card
from log_manager import DesktopLogManager


def critique_text_for_session(session: dict) -> str:
    crit = session.get("critique") or {}
    if crit.get("full_raw"):
        return str(crit["full_raw"])
    if crit.get("phase1_raw"):
        return str(crit["phase1_raw"])
    raise ValueError("講評がまだありません")


def build_session_folder_name(file_name: str, when: datetime | None = None) -> str:
    when = when or datetime.now()
    stem = Path(file_name).stem or "photo"
    safe_stem = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in stem)[:80]
    return f"{when.strftime('%Y%m%d_%H%M%S')}_{safe_stem}"


def export_guided_session(
    session: dict,
    *,
    save_root: Path,
    user_stars: int,
    card_theme: str,
    user_note: str = "",
    reflections: dict[str, Any] | None = None,
) -> Path:
    """ユーザーが書き出し時に選んだフォルダ配下へ 1 セッション分を保存。"""
    if user_stars < 1 or user_stars > 5:
        raise ValueError("user_stars は 1〜5 で指定してください")

    critique_text = critique_text_for_session(session)
    file_name = session.get("original_filename") or f"{session.get('image_id', 'photo')}.jpg"
    theme = normalize_card_theme(card_theme)
    lens = (session.get("critique") or {}).get("lens") or "self"
    note = (user_note or "").strip()
    reflect = reflections or {}

    now = datetime.now()
    ym = now.strftime("%Y%m")
    session_dir = save_root / ym / build_session_folder_name(file_name, now)
    session_dir.mkdir(parents=True, exist_ok=True)

    image_src = Path(session["path"])
    photo_path = session_dir / "photo.jpg"
    try:
        photo_bytes, _ = prepare_vision_image_bytes(image_src)
        photo_path.write_bytes(photo_bytes)
    except Exception:
        shutil.copy2(image_src, photo_path)

    card_path = session_dir / "card.png"
    create_guided_card(
        photo_path,
        critique_text,
        card_path,
        theme=theme,
        user_note=note,
        user_stars=user_stars,
        file_name=file_name,
        lens=lens,
    )

    meta_block = session.get("meta_block") or ""
    note_path = session_dir / "note.md"
    note_path.write_text(
        _format_note_markdown(
            file_name=file_name,
            metadata_block=meta_block,
            critique_text=critique_text,
            user_stars=user_stars,
            user_note=note,
            reflections=reflect,
        ),
        encoding="utf-8",
    )

    session_json = {
        "image_id": session.get("api_params", {}).get("image", {}).get("image_id")
        or session.get("image_id"),
        "lens": lens,
        "user_stars": user_stars,
        "card_theme": theme,
        "user_note": note,
        "reflections": reflect,
        "exported_at": now.isoformat(timespec="seconds"),
        "api_parameters": session.get("api_params"),
        "original_filename": file_name,
    }
    (session_dir / "session.json").write_text(
        json.dumps(session_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return session_dir


def _format_note_markdown(
    *,
    file_name: str,
    metadata_block: str,
    critique_text: str,
    user_stars: int,
    user_note: str,
    reflections: dict[str, Any],
) -> str:
    """DesktopLogManager 互換の本文 + Guided 固有の思い・一言・振り返り。"""
    manager = DesktopLogManager(Path("/tmp"))
    body = manager._format_structured_content(file_name, metadata_block, critique_text)
    stars_line = f"★ 思い: {user_stars}/5"
    header = (
        "==================================================\n"
        f"📷 ファイル名: {file_name}\n"
        f"{stars_line}\n"
        "=================================================="
    )
    extra_parts: list[str] = []
    if user_note:
        extra_parts.append(f"一言: {user_note}")
    for key, item in reflections.items():
        if not isinstance(item, dict):
            continue
        if not item.get("checked") and not (item.get("text") or "").strip():
            continue
        label = item.get("label") or key
        text = (item.get("text") or "").strip() or "—"
        mark = "☑" if item.get("checked") else "☐"
        extra_parts.append(f"{mark} {label}: {text}")
    if extra_parts:
        return f"{header}\n{body}\n\n---\n\n" + "\n\n".join(extra_parts) + "\n"
    return f"{header}\n{body}\n"


def render_card_preview(
    session: dict,
    output_path: Path,
    *,
    card_theme: str,
    user_stars: int = 0,
    user_note: str = "",
) -> Path:
    """Guided カード PNG を生成して output_path に保存する。"""
    critique_text = critique_text_for_session(session)
    lens = (session.get("critique") or {}).get("lens") or "self"
    image_path = Path(session.get("preview_path") or session["path"])
    file_name = session.get("original_filename") or "photo.jpg"
    create_guided_card(
        image_path,
        critique_text,
        output_path,
        theme=normalize_card_theme(card_theme),
        user_note=user_note,
        user_stars=user_stars,
        file_name=file_name,
        lens=lens,
    )
    return output_path
