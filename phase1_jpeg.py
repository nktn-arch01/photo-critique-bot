"""JPEG Description 上の Phase1（TITLE/SUMMARY/SCORES/CRITIQUE_SUMMARY）橋渡し.

スクリーニング「カード」・Lumina Review・将来の共通コアが同じ形式で読み書きする。
"""

from __future__ import annotations

from pathlib import Path

from critique_parser import parse_critique_text
from iptc_rating_io import (
    has_complete_phase1_blocks,
    parse_phase1_blocks,
    read_screening_meta,
    write_phase1_blocks,
)


def format_scores_one_line(scores: dict) -> str:
    """パーサー scores dict → Description 用1行."""
    parts: list[str] = []
    for label, info in scores.items():
        stars = info.get("stars", "")
        val = info.get("val", "")
        parts.append(f"・{label}: {stars} ({val}/5)")
    return " ".join(parts)


def parsed_to_phase1_blocks(parsed: dict) -> dict[str, str]:
    return {
        "TITLE": str(parsed.get("title") or "").strip(),
        "SUMMARY": str(parsed.get("summary") or "").strip(),
        "SCORES": format_scores_one_line(parsed.get("scores") or {}),
        "CRITIQUE_SUMMARY": str(parsed.get("point_text") or "").strip(),
    }


def critique_text_to_phase1_blocks(critique_text: str, lens: str | None = None) -> dict[str, str]:
    parsed = parse_critique_text(critique_text, lens=lens)
    return parsed_to_phase1_blocks(parsed)


def phase1_blocks_to_critique_text(blocks: dict[str, str]) -> str:
    """埋め込み Phase1 → Phase1 講評テキスト（カード／Phase2 注入用）."""
    title = blocks.get("TITLE", "").strip()
    summary = blocks.get("SUMMARY", "").strip()
    scores = blocks.get("SCORES", "").strip()
    critique_summary = blocks.get("CRITIQUE_SUMMARY", "").strip()
    scores_block = scores
    if scores and not scores.startswith("・") and "\n" not in scores:
        # 既に1行。SCORES 見出し付きマルチ行へ
        scores_block = scores
    lines = [
        f"■TITLE: {title}",
        f"■SUMMARY: {summary}",
        "■SCORES:",
    ]
    if "・" in scores_block:
        # スペース区切りの ・項目 を改行に戻す
        items = [p for p in scores_block.split("・") if p.strip()]
        for item in items:
            lines.append(f"・{item.strip()}")
    elif scores_block:
        lines.append(scores_block)
    lines.append(f"■CRITIQUE_SUMMARY: {critique_summary}")
    return "\n".join(lines)


def read_phase1_critique_text(path: Path | str, lens: str | None = None) -> str | None:
    """JPEG に完全な Phase1 があれば講評テキストとして返す。無ければ None."""
    meta = read_screening_meta(path)
    if not has_complete_phase1_blocks(meta.description):
        return None
    blocks = parse_phase1_blocks(meta.description)
    text = phase1_blocks_to_critique_text(blocks)
    parsed = parse_critique_text(text, lens=lens)
    if not parsed.get("has_valid_phase1"):
        return None
    return text


def write_phase1_from_critique(
    path: Path | str,
    critique_text: str,
    *,
    lens: str | None = None,
) -> str:
    """講評テキストから Phase1 を抜き JPEG Description に upsert."""
    blocks = critique_text_to_phase1_blocks(critique_text, lens=lens)
    return write_phase1_blocks(path, blocks)


def jpeg_has_complete_phase1(path: Path | str) -> bool:
    meta = read_screening_meta(path)
    return has_complete_phase1_blocks(meta.description)
