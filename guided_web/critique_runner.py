"""Guided Web 講評生成（抽象パラメータのみ API 送信）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from critique_lens import normalize_lens
from critique_parser import parse_critique_text

from guided_web.body_sections import split_critique_sections
from guided_web.guided_privacy import generate_guided_critique


def run_phase1(
    image_path: Path,
    api_params: dict[str, Any],
    *,
    lens: str = "self",
    user_note: str = "",
    session_id: str | None = None,
) -> tuple[str, dict]:
    lens_id = normalize_lens(lens)
    text = generate_guided_critique(
        image_path,
        api_params,
        user_note=user_note,
        mode="compact",
        lens=lens_id,
        session_id=session_id,
    )
    return text, parse_critique_text(text, lens=lens_id)


def run_phase2(
    image_path: Path,
    api_params: dict[str, Any],
    phase1_text: str,
    *,
    lens: str = "self",
    user_note: str = "",
    session_id: str | None = None,
) -> tuple[str, dict, list[dict]]:
    lens_id = normalize_lens(lens)
    full = generate_guided_critique(
        image_path,
        api_params,
        user_note=user_note,
        mode="full",
        lens=lens_id,
        phase1_override=phase1_text,
        session_id=session_id,
    )
    parsed = parse_critique_text(full, lens=lens_id)
    sections = split_critique_sections(parsed.get("body") or "")
    return full, parsed, sections
