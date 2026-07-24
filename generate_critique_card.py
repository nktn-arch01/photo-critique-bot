import os
import re
import platform
from PIL import Image, ImageDraw, ImageFont

def parse_gpt_output(gpt_text: str) -> dict:
    """
    GPTのMarkdown出力から講評カードに必要な情報を自動抽出する
    """
    data = {
        "title": "無題",
        "summary": "",
        "scores": {
            "構図": 3.0,
            "光・色彩": 3.0,
            "ストーリー": 3.0,
            "技術・露出": 3.0,
            "独自性": 3.0
        },
        "highlight": "光と影のグラデーションが印象的な作品。"
    }

    # 1. タイトル抽出
    title_match = re.search(r'■TITLE\s*[:：]?\s*(.+)', gpt_text)
    if title_match:
        data["title"] = title_match.group(1).strip()

    # 2. サマリー抽出
    summary_match = re.search(r'■SUMMARY\s*[:：]?\s*(.+)', gpt_text)
    if summary_match:
        data["summary"] = summary_match.group(1).strip()

    # 3. スコア抽出 (★の数または数値に対応)
    score_keys = ["構図", "光・色彩", "ストーリー", "技術・露出", "独自性"]
    for key in score_keys:
        match = re.search(rf'{key}\s*[:：]?\s*([★☆\d\.]+)', gpt_text)
        if match:
            val_str = match.group(1)
            if '★' in val_str or '☆' in val_str:
                data["scores"][key] = float(val_str.count('★'))
            else:
                try:
                    data["scores"][key] = float(val_str)
                except ValueError:
                    pass

    # 4. ハイライト (【1.情景...】の最初の1文を抽出)
    highlight_match = re.search(r'【1\..*?】\s*(.+?)(?=\n|。)', gpt_text)
    if highlight_match:
        data["highlight"] = highlight_match.group(1).strip() + "。"

    return data


def create_critique_card(
    image_path: str,
    analysis_data: dict,
    output_path: str = None,
    font_path: str = None
):
    """
    スマホ縦横・一眼レフ(3:2, 4:3)・正方形など、全アスペクト比に対応した
    白黒反転ギャラリー風の講評カード画像を生成する
    """
    if output_path is None:
        base_name = os.path.splitext(image_path)[0]
        output_path = f"{base_name}_card.jpg"

    CANVAS_W, CANVAS_H = 1080, 1350
    BG_COLOR = (18, 18, 20)         # シックなダークグレー/黒
    BORDER_COLOR = (63, 63, 70)     # 額縁・区切り線
    TEXT_WHITE = (255, 255, 255)
    TEXT_MUTED = (161, 161, 170)

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # フォント設定 (macOS用)
    if not font_path:
        font_path_candidates = [
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/System/Library/Fonts/Supplemental/Hiragino Sans W6.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ]
        for path in font_path_candidates:
            if os.path.exists(path):
                font_path = path
                break

    try:
        f_title = ImageFont.truetype(font_path, 38)
        f_sub = ImageFont.truetype(font_path, 24)
        f_body = ImageFont.truetype(font_path, 20)
        f_small = ImageFont.truetype(font_path, 16)
    except Exception:
        f_title = f_sub = f_body = f_small = ImageFont.load_default()

    # --- 1. 写真配置 (全アスペクト比自動対応ロジック) ---
    MAX_PHOTO_W, MAX_PHOTO_H = 920, 620
    FRAME_TOP = 60

    orig = Image.open(image_path).convert("RGB")
    photo_copy = orig.copy()
    photo_copy.thumbnail((MAX_PHOTO_W, MAX_PHOTO_H), Image.Resampling.LANCZOS)
    
    actual_w, actual_h = photo_copy.size
    photo_x = (CANVAS_W - actual_w) // 2
    photo_y = FRAME_TOP + (MAX_PHOTO_H - actual_h) // 2

    # 額縁ライン描画
    draw.rectangle(
        [photo_x - 2, photo_y - 2, photo_x + actual_w + 1, photo_y + actual_h + 1],
        outline=BORDER_COLOR,
        width=1
    )
    canvas.paste(photo_copy, (photo_x, photo_y))

    # --- 2. 下部テキスト・スコアエリア (レイアウト崩れ防止のY固定) ---
    ty = 730

    # タイトル
    draw.text((80, ty), analysis_data.get("title", "無題"), font=f_title, fill=TEXT_WHITE)
    ty += 50

    # サマリー
    draw.text((80, ty), analysis_data.get("summary", ""), font=f_sub, fill=TEXT_MUTED)
    ty += 45

    # 区切り線 1
    draw.line([(80, ty), (CANVAS_W - 80, ty)], fill=BORDER_COLOR, width=1)
    ty += 35

    # 5観点スコア
    scores = analysis_data.get("scores", {})
    col_w = 460
    for idx, (label, score) in enumerate(scores.items()):
        col = idx % 2
        row = idx // 2
        x = 80 + (col * col_w)
        y = ty + (row * 42)

        draw.text((x, y), label, font=f_body, fill=TEXT_MUTED)
        
        dot_x = x + 130
        for i in range(5):
            fill_c = TEXT_WHITE if i < int(score) else BORDER_COLOR
            draw.ellipse([dot_x + (i * 22), y + 6, dot_x + (i * 22) + 12, y + 18], fill=fill_c)

        draw.text((dot_x + 125, y), f"{score:.1f}", font=f_body, fill=TEXT_WHITE)

    # 区切り線 2
    ty += 140
    draw.line([(80, ty), (CANVAS_W - 80, ty)], fill=BORDER_COLOR, width=1)
    ty += 25

    # ポイント講評
    highlight = analysis_data.get("highlight", "")
    draw.text((80, ty), "【Point】 " + highlight, font=f_body, fill=(228, 228, 231))

    # ブランディングフッター
    draw.text((CANVAS_W - 240, CANVAS_H - 50), "Photo Critique AI", font=f_small, fill=(115, 115, 128))

    # 保存
    canvas.save(output_path, "JPEG", quality=95)
    print(f"   ✅ 講評カード画像を保存しました: {output_path}")

    if platform.system() == "Darwin":
        os.system(f"open '{output_path}'")

    return output_path