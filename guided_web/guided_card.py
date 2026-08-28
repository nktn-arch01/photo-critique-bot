"""Guided Web 専用カード（Compact + 思い・一言・ファイル名）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from card_theme import get_card_palette, normalize_card_theme
from critique_lens import DEFAULT_LENS, get_lens
from critique_parser import parse_critique_text
from generate_critique_card import (
    BODY_LINE_HEIGHT,
    BODY_LINES,
    CARD_HEIGHT,
    CARD_MARGIN,
    CARD_WIDTH,
    GAP_IMAGE_TEXT,
    LINE_GAP_AFTER,
    LINE_THICKNESS,
    SUMMARY_BLOCK_H,
    SUMMARY_FONT_SIZE,
    TITLE_BLOCK_H,
    TITLE_NUDGE_UP_PX,
    _fit_contain,
    _wrap_to_pixel_width,
    load_japanese_font,
)


def _stars_text(count: int) -> str:
    n = max(0, min(5, int(count)))
    return "★" * n + "☆" * (5 - n)


def create_guided_card(
    image_path: Path,
    critique_text: str,
    output_path: Path,
    *,
    theme: str = "dark",
    user_note: str = "",
    user_stars: int = 0,
    file_name: str = "",
    lens: str = DEFAULT_LENS,
) -> str:
    """Guided 用カード PNG。Compact 線の下: 思い → 一言（ラベルなし）→ 空行 → ファイル名。"""
    palette = get_card_palette(theme)
    lens_def = get_lens(lens)
    parsed = parse_critique_text(critique_text, lens=lens_def.id)

    content_left = CARD_MARGIN
    content_right = CARD_WIDTH - CARD_MARGIN
    content_top = CARD_MARGIN
    content_bottom = CARD_HEIGHT - CARD_MARGIN
    content_width = content_right - content_left

    footer_line_h = 30
    footer_block_h = footer_line_h * 4 + LINE_THICKNESS + LINE_GAP_AFTER

    text_height = (
        LINE_THICKNESS
        + LINE_GAP_AFTER
        + TITLE_BLOCK_H
        + SUMMARY_BLOCK_H
        + 4
        + LINE_THICKNESS
        + LINE_GAP_AFTER
        + BODY_LINES * BODY_LINE_HEIGHT
        + 8
        + footer_block_h
    )
    text_top = content_bottom - text_height
    img_area_bottom = text_top - GAP_IMAGE_TEXT

    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=palette["bg"])
    draw = ImageDraw.Draw(card)

    font_title = load_japanese_font(42)
    font_text = load_japanese_font(SUMMARY_FONT_SIZE)
    font_body = load_japanese_font(28)
    font_meta = load_japanese_font(22)

    y = text_top
    title_line_y = y
    y += LINE_THICKNESS + LINE_GAP_AFTER
    title_y = y - TITLE_NUDGE_UP_PX
    y += TITLE_BLOCK_H
    summary_y = y
    y += SUMMARY_BLOCK_H + 4

    critique_line_y = y
    y += LINE_THICKNESS + LINE_GAP_AFTER
    critique_y = y
    y += BODY_LINES * BODY_LINE_HEIGHT + 8

    footer_line_y = y
    y += LINE_THICKNESS + LINE_GAP_AFTER
    footer_y = y

    draw.line(
        [(content_left, title_line_y), (content_right, title_line_y)],
        fill=palette["line"],
        width=LINE_THICKNESS,
    )
    draw.text((content_left, title_y), parsed["title"], font=font_title, fill=palette["title"])
    draw.text((content_left, summary_y), parsed["summary"], font=font_text, fill=palette["summary"])

    draw.line(
        [(content_left, critique_line_y), (content_right, critique_line_y)],
        fill=palette["line"],
        width=LINE_THICKNESS,
    )
    body_lines = _wrap_to_pixel_width(parsed["point_text"], font_body, content_width)[:BODY_LINES]
    for i, line in enumerate(body_lines):
        if line:
            draw.text(
                (content_left, critique_y + i * BODY_LINE_HEIGHT),
                line,
                font=font_body,
                fill=palette["body"],
            )

    draw.line(
        [(content_left, footer_line_y), (content_right, footer_line_y)],
        fill=palette["line"],
        width=LINE_THICKNESS,
    )

    stars = _stars_text(user_stars) if user_stars > 0 else "☆☆☆☆☆"
    note = (user_note or "").strip()
    fname = (file_name or "").strip() or "—"

    footer_rows: list[str] = [
        f"この写真に対する思い: {stars}",
        note,
        "",
        fname,
    ]
    for i, line in enumerate(footer_rows):
        if not line:
            continue
        draw.text(
            (content_left, footer_y + i * footer_line_h),
            line,
            font=font_meta,
            fill=palette["summary"],
        )

    img_max_w = content_width
    img_max_h = max(1, img_area_bottom - content_top)
    if img_max_w > 0 and img_max_h > 0:
        try:
            with Image.open(image_path) as raw_img:
                img = ImageOps.exif_transpose(raw_img)
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")
                new_w, new_h = _fit_contain(img.width, img.height, img_max_w, img_max_h)
                if new_w > 0 and new_h > 0:
                    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    paste_x = content_left + (img_max_w - new_w) // 2
                    paste_y = content_top
                    card.paste(resized, (paste_x, paste_y))
        except Exception as e:
            print(f"[Guided Card Image Error] {e}", flush=True)

    card.save(output_path, "PNG")
    return normalize_card_theme(theme)
