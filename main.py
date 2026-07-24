import os
import io
import re
import asyncio
import base64
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    PushMessageRequest,
    TextMessage,
    ImageMessage
)
from linebot.v3.webhooks import MessageEvent, ImageMessageContent
from openai import OpenAI
from supabase import create_client, Client
from PIL import Image, ImageDraw, ImageFont

# -------------------------------------------------------------
# 1. 環境変数の取得
# -------------------------------------------------------------
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
openai_client = OpenAI(api_key=OPENAI_API_KEY)
supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

app = FastAPI()

# -------------------------------------------------------------
# 2. カード画像生成関数
# -------------------------------------------------------------
def parse_gpt_output(gpt_text: str) -> dict:
    data = {
        "title": "無題",
        "summary": "",
        "scores": {"構図": 3.0, "光・色彩": 3.0, "ストーリー": 3.0, "技術・露出": 3.0, "独自性": 3.0},
        "highlight": "光と影のグラデーションが印象的な作品。"
    }
    title_match = re.search(r'■TITLE\s*[:：]?\s*(.+)', gpt_text)
    if title_match:
        data["title"] = title_match.group(1).strip()

    summary_match = re.search(r'■SUMMARY\s*[:：]?\s*(.+)', gpt_text)
    if summary_match:
        data["summary"] = summary_match.group(1).strip()

    for key in data["scores"].keys():
        match = re.search(rf'{key}\s*[:：]?\s*([★☆\d\.]+)', gpt_text)
        if match:
            val_str = match.group(1)
            if '★' in val_str or '☆' in val_str:
                data["scores"][key] = float(val_str.count('★'))
            else:
                try: data["scores"][key] = float(val_str)
                except ValueError: pass

    highlight_match = re.search(r'【1\..*?】\s*(.+?)(?=\n|。)', gpt_text)
    if highlight_match:
        data["highlight"] = highlight_match.group(1).strip() + "。"

    return data

def generate_card_image(image_bytes: bytes, gpt_text: str) -> bytes:
    analysis_data = parse_gpt_output(gpt_text)
    CANVAS_W, CANVAS_H = 1080, 1350
    BG_COLOR = (18, 18, 20)
    BORDER_COLOR = (63, 63, 70)
    TEXT_WHITE = (255, 255, 255)
    TEXT_MUTED = (161, 161, 170)

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    f_title = f_sub = f_body = f_small = ImageFont.load_default()

    MAX_PHOTO_W, MAX_PHOTO_H = 920, 620
    FRAME_TOP = 60

    orig = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    photo_copy = orig.copy()
    photo_copy.thumbnail((MAX_PHOTO_W, MAX_PHOTO_H), Image.Resampling.LANCZOS)
    
    actual_w, actual_h = photo_copy.size
    photo_x = (CANVAS_W - actual_w) // 2
    photo_y = FRAME_TOP + (MAX_PHOTO_H - actual_h) // 2

    draw.rectangle([photo_x - 2, photo_y - 2, photo_x + actual_w + 1, photo_y + actual_h + 1], outline=BORDER_COLOR, width=1)
    canvas.paste(photo_copy, (photo_x, photo_y))

    ty = 730
    draw.text((80, ty), analysis_data.get("title", "無題"), font=f_title, fill=TEXT_WHITE)
    ty += 50
    draw.text((80, ty), analysis_data.get("summary", ""), font=f_sub, fill=TEXT_MUTED)
    ty += 45
    draw.line([(80, ty), (CANVAS_W - 80, ty)], fill=BORDER_COLOR, width=1)
    ty += 35

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

    ty += 140
    draw.line([(80, ty), (CANVAS_W - 80, ty)], fill=BORDER_COLOR, width=1)
    ty += 25
    draw.text((80, ty), "【Point】 " + analysis_data.get("highlight", ""), font=f_body, fill=(228, 228, 231))
    draw.text((CANVAS_W - 240, CANVAS_H - 50), "Photo Critique AI", font=f_small, fill=(115, 115, 128))

    output_buffer = io.BytesIO()
    canvas.save(output_buffer, format="JPEG", quality=90)
    return output_buffer.getvalue()

# -------------------------------------------------------------
# 3. 非同期（バックグラウンド）解析処理
# -------------------------------------------------------------
async def process_image_and_reply(message_id: str, user_id: str):
    try:
        # A. LINEから画像バイナリを取得
        with ApiClient(configuration) as api_client:
            messaging_api_blob = MessagingApiBlob(api_client)
            image_bytes = messaging_api_blob.get_message_content(message_id)

        # B. GPT-4o-miniで解析
        base64_img = base64.b64encode(image_bytes).decode('utf-8')
        prompt = """写真の美と物語を評価する写真評論家として講評を作成してください。

■TITLE: 15文字以内のタイトル
■SUMMARY: 25文字以内のキャッチコピー
■SCORES:
・構図・構成 : ★★★★☆ (4/5)
・光・色彩   : ★★★★★ (5/5)
・ストーリー : ★★★★☆ (4/5)
・技術・露出 : ★★★★☆ (4/5)
・独自・世界観: ★★★★☆ (4/5)

## 【1. 情景とストーリー】
## 【2. 視線誘導と構成】
## 【3. 光と色彩】
## 【4. アドバイス】
"""
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}", "detail": "high"}}
                ]}
            ],
            max_tokens=1500
        )
        gpt_text = response.choices[0].message.content

        # C. 講評カード画像生成
        card_bytes = generate_card_image(image_bytes, gpt_text)

        # D. Supabase Storage へアップロード
        file_path = f"{message_id}.jpg"
        supabase_client.storage.from_("cards").upload(
            file_path,
            card_bytes,
            file_options={"content-type": "image/jpeg", "x-upsert": "true"}
        )
        public_url = supabase_client.storage.from_("cards").get_public_url(file_path)

        # E. LINEへPushメッセージで返信（テキスト講評＋カード画像）
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            push_request = PushMessageRequest(
                to=user_id,
                messages=[
                    TextMessage(text=gpt_text),
                    ImageMessage(original_content_url=public_url, preview_image_url=public_url)
                ]
            )
            line_api.push_message(push_request)

    except Exception as e:
        import traceback
        print(f"❌ エラー発生の詳細:")
        traceback.print_exc()
        try:
            with ApiClient(configuration) as api_client:
                line_api = MessagingApi(api_client)
                line_api.push_message(PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text="申し訳ありません。画像の解析中にエラーが発生しました。")]
                ))
        except Exception: pass

# -------------------------------------------------------------
# 4. Webhook エンドポイント（LINEからの受信用）
# -------------------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_str = body.decode("utf-8")

    try:
        events = handler.parser.parse(body_str, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, ImageMessageContent):
            background_tasks.add_task(
                process_image_and_reply,
                event.message.id,
                event.source.user_id
            )

    return "OK"