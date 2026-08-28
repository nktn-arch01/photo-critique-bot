"""Guided Web 講評生成（critique_engine ラッパ）。"""

from __future__ import annotations

from pathlib import Path

from critique_engine import generate_critique
from critique_lens import normalize_lens
from critique_parser import parse_critique_text

from guided_web.body_sections import split_critique_sections


def _metadata_with_note(metadata: dict, user_note: str) -> dict:
    meta = dict(metadata or {})
    note = (user_note or "").strip()
    if note:
        meta["user_intent"] = note
    return meta


def run_phase1(
    image_path: Path,
    metadata: dict,
    dop_info: dict,
    *,
    lens: str = "self",
    user_note: str = "",
) -> tuple[str, dict]:
    lens_id = normalize_lens(lens)
    text = generate_critique(
        image_path,
        metadata=_metadata_with_note(metadata, user_note),
        dop_info=dop_info,
        mode="compact",
        lens=lens_id,
    )
    return text, parse_critique_text(text, lens=lens_id)


def run_phase2(
    image_path: Path,
    metadata: dict,
    dop_info: dict,
    phase1_text: str,
    *,
    lens: str = "self",
    user_note: str = "",
) -> tuple[str, dict, list[dict]]:
    lens_id = normalize_lens(lens)
    full = generate_critique(
        image_path,
        metadata=_metadata_with_note(metadata, user_note),
        dop_info=dop_info,
        mode="full",
        lens=lens_id,
        phase1_override=phase1_text,
    )
    parsed = parse_critique_text(full, lens=lens_id)
    sections = split_critique_sections(parsed.get("body") or "")
    return full, parsed, sections
