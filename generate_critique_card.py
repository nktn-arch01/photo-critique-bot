import textwrap
from dataclasses import dataclass
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from critique_lens import DEFAULT_LENS, get_lens
from critique_parser import parse_critique_text
from card_theme import DEFAULT_CARD_THEME, get_card_palette, normalize_card_theme

# カード共通レイアウト定数（テストからも参照）
CARD_WIDTH = 1080
CARD_HEIGHT = 1350
CARD_MARGIN = 50
# 後方互換: 従来のダーク背景色
CARD_BG = get_card_palette(DEFAULT_CARD_THEME)["bg"]
GAP_IMAGE_TEXT = 28  # 写真下端と文字エリア上端の間隔
LOGO_SIZE = 128
LOGO_TEXT_GAP = 20  # スコア行とロゴの最小隙間
BODY_LINES = 3
BODY_LINE_HEIGHT = 38
SCORE_ROW_HEIGHT = 26
# self レンズ既定は5。描画はレンズ軸数を優先（将来の可変軸に備える）
SCORE_ROW_COUNT = len(get_lens(DEFAULT_LENS).score_axes)
DISCLAIMER_LINE_HEIGHT = 28  # 後方互換定数（N-01 以降、免責非表示なら高さに含めない）
LINE_THICKNESS = 1
LINE_GAP_AFTER = 18
# N-02: タイトルを分割線側へ 5px。CRITIQUE の下方向 nudge は Phase 2 で
# 要約が下端から離れたため描画には使わない（定数は互換のため残す）。
TITLE_NUDGE_UP_PX = 5
CRITIQUE_NUDGE_DOWN_PX = 0
TITLE_BLOCK_H = 50
SUMMARY_BLOCK_H = 38
AFTER_SUMMARY_GAP = 4
AFTER_CRITIQUE_GAP = 8
# P2-2 Phase 2（U1/Q1）: 言葉（TITLE/SUMMARY/CRITIQUE_SUMMARY）が★より大きい
SUMMARY_FONT_SIZE = 26
CRITIQUE_FONT_SIZE = 28
SCORE_FONT_SIZE = 20  # 二次。SUMMARY / CRITIQUE より小さく保つ
# N-04: 日英併記（日本語4字揃え）。カードは★のみ（数字はログ側）。
SCORE_LABEL_X = 10
SCORE_STARS_X = 520


@dataclass(frozen=True)
class CardTextLayout:
    """1080×1350 カードの文字帯位置。描画とテストの単一ソース。"""

    content_left: int
    content_right: int
    content_top: int
    content_bottom: int
    content_width: int
    text_top: int
    text_height: int
    title_line_y: int
    title_y: int
    summary_y: int
    critique_line_y: int
    critique_y: int
    scores_line_y: int
    scores_y: int
    logo_left: int
    logo_top: int
    critique_max_w: int
    score_text_max_w: int
    img_area_bottom: int
    img_max_w: int
    img_max_h: int


def load_japanese_font(size: int) -> ImageFont.FreeTypeFont:
    base_dir = Path(__file__).parent
    font_candidates = [
        base_dir / "fonts" / "Noto_Sans_JP" / "static" / "NotoSansJP-Regular.ttf",
        base_dir / "fonts" / "NotoSansJP-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]

    for fp in font_candidates:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(str(fp), size)
            except Exception:
                continue

    return ImageFont.load_default()


def _fit_contain(src_w: int, src_h: int, max_w: int, max_h: int) -> tuple[int, int]:
    """縦横比を維持したまま max_w×max_h に収まる最大サイズを返す。"""
    if src_w <= 0 or src_h <= 0 or max_w <= 0 or max_h <= 0:
        return 0, 0
    ratio = src_w / src_h
    box_ratio = max_w / max_h
    if ratio > box_ratio:
        new_w = max_w
        new_h = max(1, int(max_w / ratio))
    else:
        new_h = max_h
        new_w = max(1, int(max_h * ratio))
    return new_w, new_h


def _text_width(font: ImageFont.ImageFont, text: str) -> int:
    if hasattr(font, "getlength"):
        return int(font.getlength(text))
    bbox = font.getbbox(text)
    return int(bbox[2] - bbox[0])


def _wrap_to_pixel_width(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    """ピクセル幅で折り返し。空でも最低1要素を返す。"""
    text = (text or "").strip()
    if not text:
        return [""]
    approx_chars = max(8, max_width // max(1, _text_width(font, "あ")))
    lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        for chunk in textwrap.wrap(paragraph, width=approx_chars) or [""]:
            if _text_width(font, chunk) <= max_width:
                lines.append(chunk)
                continue
            buf = ""
            for ch in chunk:
                trial = buf + ch
                if buf and _text_width(font, trial) > max_width:
                    lines.append(buf)
                    buf = ch
                else:
                    buf = trial
            if buf:
                lines.append(buf)
    return lines or [""]


def _score_row_count(lens: str | None = None) -> int:
    return max(1, len(get_lens(lens).score_axes))


def _fixed_text_block_height(lens: str | None = None) -> int:
    """文字エリア全体の固定高さ（スコア行・要約3行・ロゴ128を含む）。

    読み順（P2-2 Phase 2）: TITLE → SUMMARY → CRITIQUE_SUMMARY → SCORES。
    写真領域を増やすため ★ 行はロゴ帯に収め、要約は全幅。
    N-01: 免責文なし。CRITIQUE の下余白はみ出し nudge は使わない。
    """
    rows = _score_row_count(lens)
    show_disclaimer = bool((get_lens(lens).score_disclaimer or "").strip())
    h = 0
    h += LINE_THICKNESS + LINE_GAP_AFTER  # タイトル上の分割線
    h += TITLE_BLOCK_H
    h += SUMMARY_BLOCK_H
    h += AFTER_SUMMARY_GAP
    h += LINE_THICKNESS + LINE_GAP_AFTER  # 要約上
    h += BODY_LINES * BODY_LINE_HEIGHT
    h += AFTER_CRITIQUE_GAP
    h += LINE_THICKNESS + LINE_GAP_AFTER  # スコア上
    if show_disclaimer:
        h += DISCLAIMER_LINE_HEIGHT
    h += max(LOGO_SIZE, rows * SCORE_ROW_HEIGHT)
    return h


def plan_card_layout(lens: str | None = None) -> CardTextLayout:
    """文字帯・写真領域の座標を返す。create_critique_card とテストが共有する。"""
    content_left = CARD_MARGIN
    content_right = CARD_WIDTH - CARD_MARGIN
    content_top = CARD_MARGIN
    content_bottom = CARD_HEIGHT - CARD_MARGIN
    content_width = content_right - content_left
    text_height = _fixed_text_block_height(lens)
    text_top = content_bottom - text_height

    y = text_top
    title_line_y = y
    y += LINE_THICKNESS + LINE_GAP_AFTER
    title_y = y - TITLE_NUDGE_UP_PX
    y += TITLE_BLOCK_H
    summary_y = y
    y += SUMMARY_BLOCK_H
    y += AFTER_SUMMARY_GAP

    critique_line_y = y
    y += LINE_THICKNESS + LINE_GAP_AFTER
    critique_y = y
    y += BODY_LINES * BODY_LINE_HEIGHT
    y += AFTER_CRITIQUE_GAP

    scores_line_y = y
    y += LINE_THICKNESS + LINE_GAP_AFTER
    scores_y = y

    logo_left = content_right - LOGO_SIZE
    logo_top = content_bottom - LOGO_SIZE
    img_area_bottom = text_top - GAP_IMAGE_TEXT
    return CardTextLayout(
        content_left=content_left,
        content_right=content_right,
        content_top=content_top,
        content_bottom=content_bottom,
        content_width=content_width,
        text_top=text_top,
        text_height=text_height,
        title_line_y=title_line_y,
        title_y=title_y,
        summary_y=summary_y,
        critique_line_y=critique_line_y,
        critique_y=critique_y,
        scores_line_y=scores_line_y,
        scores_y=scores_y,
        logo_left=logo_left,
        logo_top=logo_top,
        critique_max_w=content_width,
        score_text_max_w=max(1, logo_left - LOGO_TEXT_GAP - content_left),
        img_area_bottom=img_area_bottom,
        img_max_w=content_width,
        img_max_h=img_area_bottom - content_top,
    )


def _load_optional_logo() -> Image.Image | None:
    base_dir = Path(__file__).parent
    for candidate in (
        base_dir / "logo.png",
        base_dir / "assets" / "logo.png",
        base_dir / "fonts" / "logo.png",
    ):
        if candidate.exists():
            try:
                with Image.open(candidate) as im:
                    logo = ImageOps.exif_transpose(im).copy()
                if logo.mode not in ("RGB", "RGBA"):
                    logo = logo.convert("RGBA")
                return logo.resize((LOGO_SIZE, LOGO_SIZE), Image.Resampling.LANCZOS)
            except Exception as e:
                print(f"[Card Logo Error] {e}", flush=True)
    return None


def create_critique_card(
    image_path: Path,
    critique_text: str,
    output_card_path: Path,
    theme: str = DEFAULT_CARD_THEME,
    lens: str = DEFAULT_LENS,
):
    """1080×1350 講評カードを生成する。

    theme: "dark"（既定）または "light"
    lens: 対話レンズ（スコア軸。v1 は self）。Desktop / LINE 共通。
    """
    palette = get_card_palette(theme)
    lens_def = get_lens(lens)
    parsed = parse_critique_text(critique_text, lens=lens_def.id)
    layout = plan_card_layout(lens_def.id)
    score_rows = _score_row_count(lens_def.id)

    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=palette["bg"])
    draw = ImageDraw.Draw(card)

    font_title = load_japanese_font(42)
    font_text = load_japanese_font(SUMMARY_FONT_SIZE)
    font_score = load_japanese_font(SCORE_FONT_SIZE)
    font_body = load_japanese_font(CRITIQUE_FONT_SIZE)
    font_disclaimer = load_japanese_font(18)

    line_color = palette["line"]
    left = layout.content_left
    right = layout.content_right

    draw.line(
        [(left, layout.title_line_y), (right, layout.title_line_y)],
        fill=line_color,
        width=LINE_THICKNESS,
    )
    draw.text(
        (left, layout.title_y),
        parsed["title"],
        font=font_title,
        fill=palette["title"],
    )
    draw.text(
        (left, layout.summary_y),
        parsed["summary"],
        font=font_text,
        fill=palette["summary"],
    )

    draw.line(
        [(left, layout.critique_line_y), (right, layout.critique_line_y)],
        fill=line_color,
        width=LINE_THICKNESS,
    )
    body_lines = _wrap_to_pixel_width(
        parsed["point_text"], font_body, layout.critique_max_w
    )[:BODY_LINES]
    while len(body_lines) < BODY_LINES:
        body_lines.append("")
    for i, line in enumerate(body_lines):
        if line:
            draw.text(
                (left, layout.critique_y + i * BODY_LINE_HEIGHT),
                line,
                font=font_body,
                fill=palette["body"],
            )

    draw.line(
        [(left, layout.scores_line_y), (right, layout.scores_line_y)],
        fill=line_color,
        width=LINE_THICKNESS,
    )

    y = layout.scores_y
    disclaimer = (parsed.get("score_disclaimer") or lens_def.score_disclaimer or "").strip()
    if disclaimer:
        draw.text(
            (left + 10, y),
            disclaimer,
            font=font_disclaimer,
            fill=palette["summary"],
        )
        y += DISCLAIMER_LINE_HEIGHT

    score_items = list(parsed["scores"].items())[:score_rows]
    for i in range(score_rows):
        if i < len(score_items):
            label, score_info = score_items[i]
            stars = score_info["stars"]
            # カード: 星のみ。数値 (n/5) は log_manager 等のテキストログに残す。
            draw.text(
                (left + SCORE_LABEL_X, y),
                f"{label}",
                font=font_score,
                fill=palette["score_label"],
            )
            draw.text(
                (left + SCORE_STARS_X, y),
                f"{stars}",
                font=font_score,
                fill=palette["stars"],
            )
        y += SCORE_ROW_HEIGHT

    logo = _load_optional_logo()
    if logo is not None:
        if logo.mode == "RGBA":
            card.paste(logo, (layout.logo_left, layout.logo_top), logo)
        else:
            card.paste(logo, (layout.logo_left, layout.logo_top))
    else:
        draw.rectangle(
            [
                layout.logo_left,
                layout.logo_top,
                layout.logo_left + LOGO_SIZE - 1,
                layout.logo_top + LOGO_SIZE - 1,
            ],
            outline=palette["logo_outline"],
            width=2,
        )

    if layout.img_max_w > 0 and layout.img_max_h > 0:
        try:
            with Image.open(image_path) as raw_img:
                img = ImageOps.exif_transpose(raw_img)
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")
                new_w, new_h = _fit_contain(
                    img.width, img.height, layout.img_max_w, layout.img_max_h
                )
                if new_w > 0 and new_h > 0:
                    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    paste_x = left + (layout.img_max_w - new_w) // 2
                    paste_y = layout.content_top
                    if resized.mode == "RGBA":
                        card.paste(resized, (paste_x, paste_y), resized)
                    else:
                        card.paste(resized, (paste_x, paste_y))
        except Exception as e:
            print(f"[Card Image Error] {e}", flush=True)

    card.save(output_card_path, "PNG")
    return normalize_card_theme(theme)
