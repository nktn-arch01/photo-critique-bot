import re
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps


def parse_critique_text(critique_text: str) -> dict:
    data = {
        "title": "写真分析講評",
        "summary": "分析完了",
        "scores": {},
        "point_text": "光と質感が織りなす印象的な情景。"
    }
    
    title_m = re.search(r'■TITLE:\s*(.+)', critique_text)
    if title_m: data["title"] = title_m.group(1).strip()

    summary_m = re.search(r'■SUMMARY:\s*(.+)', critique_text)
    if summary_m: data["summary"] = summary_m.group(1).strip()

    score_pattern = re.compile(r'・([^:\s]+)\s*:\s*([★☆]+)\s*\(([\d\.]+)/5\)')
    for m in score_pattern.finditer(critique_text):
        label, stars, val = m.group(1), m.group(2), m.group(3)
        data["scores"][label] = (stars, val)

    crit_sum_m = re.search(r'■CRITIQUE_SUMMARY:\s*(.+)', critique_text)
    if crit_sum_m:
        data["point_text"] = crit_sum_m.group(1).strip()

    return data


def load_japanese_font(size: int) -> ImageFont.FreeTypeFont:
    font_candidates = [
        Path(__file__).parent / "fonts" / "NotoSansJP-Regular.ttf",
        Path(__file__).parent / "fonts" / "NotoSansJP-Medium.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/CJK/PingFang.ttc",
        "/System/Library/Fonts/Helvetica.ttc"
    ]

    for fp in font_candidates:
        p = Path(fp)
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue

    return ImageFont.load_default()


def create_critique_card(image_path: Path, critique_text: str, output_card_path: Path):
    parsed = parse_critique_text(critique_text)
    
    W, H = 1080, 1350
    card = Image.new("RGB", (W, H), color=(24, 25, 28))
    draw = ImageDraw.Draw(card)

    font_title = load_japanese_font(42)
    font_text = load_japanese_font(26)
    font_score = load_japanese_font(28)
    font_body = load_japanese_font(22)

    try:
        with Image.open(image_path) as raw_img:
            img = ImageOps.exif_transpose(raw_img)
            img_ratio = img.width / img.height
            target_w, target_h = 1000, 460
            if img_ratio > (target_w / target_h):
                new_w = target_w
                new_h = int(target_w / img_ratio)
            else:
                new_h = target_h
                new_w = int(target_h * img_ratio)
            
            resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            paste_x = (W - new_w) // 2
            paste_y = 30 + (target_h - new_h) // 2
            card.paste(resized_img, (paste_x, paste_y))
    except Exception: pass

    y_offset = 520
    draw.line([(40, y_offset), (1040, y_offset)], fill=(60, 64, 72), width=2)
    y_offset += 25

    draw.text((40, y_offset), parsed["title"], font=font_title, fill=(255, 255, 255))
    y_offset += 50
    draw.text((40, y_offset), parsed["summary"], font=font_text, fill=(180, 185, 195))
    y_offset += 38

    draw.line([(40, y_offset), (1040, y_offset)], fill=(60, 64, 72), width=1)
    y_offset += 20

    for label, (stars, val) in parsed["scores"].items():
        draw.text((50, y_offset), f"{label}", font=font_score, fill=(200, 205, 215))
        draw.text((380, y_offset), f"{stars}", font=font_score, fill=(255, 190, 0))
        draw.text((680, y_offset), f"({val}/5)", font=font_score, fill=(160, 165, 175))
        y_offset += 36

    y_offset += 15
    draw.line([(40, y_offset), (1040, y_offset)], fill=(60, 64, 72), width=1)
    y_offset += 20

    # 要約フック文の描画（【Point】の固定ラベルを排出）
    wrapped_lines = textwrap.wrap(parsed["point_text"], width=46)
    for line in wrapped_lines[:3]:
        draw.text((40, y_offset), line, font=font_body, fill=(220, 225, 235))
        y_offset += 30

    card.save(output_card_path, "PNG")
