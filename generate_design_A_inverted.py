import os
import platform
from PIL import Image, ImageDraw, ImageFont

def create_inverted_gallery_card(
    image_path: str = "test_input.jpg",
    analysis_data: dict = None,
    output_path: str = "sample_design_A_inverted.jpg"
):
    # 写真ファイルの存在確認（見つからない場合はフォールバック）
    if not os.path.exists(image_path):
        jpg_files = [f for f in os.listdir(".") if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        if jpg_files:
            image_path = jpg_files[0]
        else:
            print("⚠️ 写真ファイルが見つかりません。")
            return

    if analysis_data is None:
        analysis_data = {
            "title": "静寂の朝に咲く光",
            "summary": "強い直射光が引き出す、静けさとドラマ",
            "scores": {
                "構図": 4.5,
                "光・色彩": 5.0,
                "ストーリー": 4.0,
                "技術・露出": 4.0,
                "独自性": 4.5
            },
            "highlight": "影の落とし込みによって主体の輪郭が浮き立っています。"
        }

    CANVAS_W, CANVAS_H = 1080, 1350
    BG_COLOR = (18, 18, 20)         # シックなダークグレー/黒
    BORDER_COLOR = (63, 63, 70)     # 外枠線
    TEXT_WHITE = (255, 255, 255)
    TEXT_MUTED = (161, 161, 170)

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # フォント設定 (macOS用)
    font_path = None
    candidates = [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Hiragino Sans W6.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for path in candidates:
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

    # -------------------------------------------------------------
    # 1. 写真配置（スマホ縦横・正方形・4:3・3:2 全比率対応ロジック）
    # -------------------------------------------------------------
    MAX_PHOTO_W, MAX_PHOTO_H = 920, 620   # 写真表示の最大バウンディングボックス
    FRAME_TOP = 60                       # 上部余白

    orig = Image.open(image_path).convert("RGB")
    photo_copy = orig.copy()

    # アスペクト比を維持したまま、最大領域(920x620)の中に収める
    photo_copy.thumbnail((MAX_PHOTO_W, MAX_PHOTO_H), Image.Resampling.LANCZOS)
    
    actual_w, actual_h = photo_copy.size

    # 最大領域の中央（センタリング）に来る座標を計算
    photo_x = (CANVAS_W - actual_w) // 2
    photo_y = FRAME_TOP + (MAX_PHOTO_H - actual_h) // 2

    # 写真の周囲に極細の額縁ラインを描画
    draw.rectangle(
        [photo_x - 2, photo_y - 2, photo_x + actual_w + 1, photo_y + actual_h + 1],
        outline=BORDER_COLOR,
        width=1
    )
    
    # キャンバスに写真を貼り付け
    canvas.paste(photo_copy, (photo_x, photo_y))

    # -------------------------------------------------------------
    # 2. 下部テキスト ＆ スコア表示エリア (固定Y座標で崩れ防止)
    # -------------------------------------------------------------
    ty = 730  # 写真エリア（最大680px高さ）の直下から確実にスタート

    # タイトル
    draw.text((80, ty), analysis_data["title"], font=f_title, fill=TEXT_WHITE)
    ty += 50

    # サマリー
    draw.text((80, ty), analysis_data["summary"], font=f_sub, fill=TEXT_MUTED)
    ty += 45

    # 区切り線 1
    draw.line([(80, ty), (CANVAS_W - 80, ty)], fill=BORDER_COLOR, width=1)
    ty += 35

    # 5観点スコア (2列並列)
    col_w = 460
    for idx, (label, score) in enumerate(analysis_data["scores"].items()):
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
    draw.text((80, ty), "【Point】 " + analysis_data["highlight"], font=f_body, fill=(228, 228, 231))

    # ブランディングフッター
    draw.text((CANVAS_W - 240, CANVAS_H - 50), "Photo Critique AI", font=f_small, fill=(115, 115, 128))

    # 保存
    canvas.save(output_path, "JPEG", quality=95)
    print(f"✅ どんな比率にも対応した講評カードを保存しました: {output_path}")

    if platform.system() == "Darwin":
        os.system(f"open '{output_path}'")

if __name__ == "__main__":
    create_inverted_gallery_card()