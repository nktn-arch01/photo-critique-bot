"""Guided Web のストック書き出し（カード PNG + ログ MD）。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from guided_web.guided_card import create_guided_card
from guided_web.reflect_prompts import format_reflections_block, selected_reflection_labels
from log_manager import DesktopLogManager


def critique_text_for_session(session: dict) -> str:
    crit = session.get("critique") or {}
    if crit.get("full_raw"):
        return str(crit["full_raw"])
    if crit.get("phase1_raw"):
        return str(crit["phase1_raw"])
    raise ValueError("講評がまだありません")


def export_output_names(file_name: str) -> tuple[str, str]:
    stem = Path(file_name).stem or "photo"
    return f"{stem}_LN.png", f"{stem}_LN.md"


def export_guided_session(
    session: dict,
    *,
    save_dir: Path,
    user_stars: int,
    card_theme: str,
    user_note: str = "",
    reflections: dict[str, Any] | None = None,
) -> dict[str, str]:
    """ユーザーが選んだ既存フォルダへ {stem}_LN.png / {stem}_LN.md を書き出す（サブフォルダは作らない）。"""
    if user_stars < 1 or user_stars > 5:
        raise ValueError("user_stars は 1〜5 で指定してください")

    target = save_dir.expanduser().resolve()
    if not target.is_dir():
        raise ValueError("保存先フォルダが存在しません")

    critique_text = critique_text_for_session(session)
    file_name = session.get("original_filename") or "photo.jpg"
    original_path = session.get("original_path") or file_name
    lens = (session.get("critique") or {}).get("lens") or "self"
    note = (user_note or "").strip()
    reflect = reflections or {}

    card_name, note_name = export_output_names(file_name)
    card_path = target / card_name
    note_path = target / note_name

    image_path = Path(session.get("preview_path") or session["path"])
    create_guided_card(
        image_path,
        critique_text,
        card_path,
        theme=card_theme,
        user_note=note,
        user_stars=user_stars,
        file_name=file_name,
        lens=lens,
    )

    meta_block = session.get("meta_block") or ""
    note_path.write_text(
        _format_note_markdown(
            file_name=file_name,
            original_path=original_path,
            metadata_block=meta_block,
            critique_text=critique_text,
            user_stars=user_stars,
            user_note=note,
            reflections=reflect,
        ),
        encoding="utf-8",
    )

    return {
        "export_dir": str(target),
        "card": str(card_path),
        "note": str(note_path),
    }


def _format_note_markdown(
    *,
    file_name: str,
    original_path: str,
    metadata_block: str,
    critique_text: str,
    user_stars: int,
    user_note: str,
    reflections: dict[str, Any],
) -> str:
    manager = DesktopLogManager(Path("/tmp"))
    critique_body = manager._format_structured_content(file_name, "", critique_text)
    reflection_block = format_reflections_block(reflections)
    reflection_csv = ", ".join(selected_reflection_labels(reflections))

    header_lines = [
        "=== 振り返り ===",
        f"オリジナルファイルのパス: {original_path}",
        f"★ 思い: {user_stars}/5",
        f"一言: {user_note or '—'}",
        reflection_block,
        f"振り返りメモ: {reflection_csv or '—'}",
        f"書き出し日時: {datetime.now().isoformat(timespec='seconds')}",
    ]
    header = "\n".join(header_lines) + "\n"

    parts = [header, critique_body.strip()]
    meta = (metadata_block or "").strip()
    if meta:
        parts.append(meta)
    return "\n\n---\n\n".join(parts) + "\n"


def render_card_preview(
    session: dict,
    output_path: Path,
    *,
    card_theme: str,
    user_stars: int = 0,
    user_note: str = "",
) -> Path:
    critique_text = critique_text_for_session(session)
    lens = (session.get("critique") or {}).get("lens") or "self"
    image_path = Path(session.get("preview_path") or session["path"])
    file_name = session.get("original_filename") or "photo.jpg"
    create_guided_card(
        image_path,
        critique_text,
        output_path,
        theme=card_theme,
        user_note=user_note,
        user_stars=user_stars,
        file_name=file_name,
        lens=lens,
    )
    return output_path
