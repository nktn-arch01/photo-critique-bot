import os
import shutil
import tempfile
import traceback
from pathlib import Path
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Header
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, ImageMessage, TextMessage, TextSendMessage, ImageSendMessage,
    QuickReply, QuickReplyButton, MessageAction
)

from critique_engine import generate_critique
from generate_critique_card import create_critique_card
from supabase_client import SupabaseManager

app = FastAPI(title="Photo AI Critique LINE Bot")

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(LINE_CHANNEL_SECRET)
supabase_mgr = SupabaseManager()


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Photo AI Critique Bot"}


def process_image_and_reply(reply_token: str, line_user_id: str, message_id: str):
    temp_dir = Path(tempfile.mkdtemp())
    img_path = temp_dir / f"{message_id}.jpg"
    card_path = temp_dir / f"{message_id}_card.png"

    try:
        message_content = line_bot_api.get_message_content(message_id)
        with open(img_path, "wb") as f:
            for chunk in message_content.iter_content():
                f.write(chunk)

        user_mode = supabase_mgr.get_user_mode(line_user_id)
        critique_text = generate_critique(img_path, mode=user_mode)
        create_critique_card(img_path, critique_text, card_path)

        card_public_url = supabase_mgr.upload_card_image(
            card_path=card_path,
            file_name=f"{message_id}_card.png",
            bucket_name="critique-cards"
        )

        supabase_mgr.save_critique_log(
            line_user_id=line_user_id,
            image_url="",
            critique_text=critique_text,
            card_image_url=card_public_url
        )

        messages_to_send = []

        if card_public_url:
            messages_to_send.append(
                ImageSendMessage(
                    original_content_url=card_public_url,
                    preview_image_url=card_public_url
                )
            )

        if user_mode == "full":
            messages_to_send.append(TextSendMessage(text=critique_text))
        else:
            import re
            title_m = re.search(r'■TITLE:\s*(.+)', critique_text)
            crit_sum_m = re.search(r'■CRITIQUE_SUMMARY:\s*(.+)', critique_text)
            
            title_str = title_m.group(1).strip() if title_m else "写真分析講評"
            crit_sum_str = crit_sum_m.group(1).strip() if crit_sum_m else "分析が完了しました。"
            
            compact_msg = f"📷【{title_str}】\n\n{crit_sum_str}"
            messages_to_send.append(TextSendMessage(text=compact_msg))

        line_bot_api.push_message(line_user_id, messages_to_send)

    except Exception as e:
        print(f"[Processing Error] {e}", flush=True)
        traceback.print_exc()
        try:
            line_bot_api.push_message(
                line_user_id,
                TextSendMessage(text="申し訳ありません。写真の解析中にエラーが発生しました。もう一度お試しください。")
            )
        except Exception:
            pass
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def handle_text_message(reply_token: str, line_user_id: str, text: str):
    if text in ["設定", "せってい", "モード設定"]:
        current_mode = supabase_mgr.get_user_mode(line_user_id)
        mode_label = "詳細版" if current_mode == "full" else "簡易版"
        
        msg_text = f"⚙️【講評出力モード設定】\n\n現在の設定：【{mode_label}】\n\n変更したいモードを下のボタンから選択してください。"
        
        quick_reply = QuickReply(
            items=[
                QuickReplyButton(action=MessageAction(label="📷 簡易版にする", text="設定:簡易版")),
                QuickReplyButton(action=MessageAction(label="📝 詳細版にする", text="設定:詳細版"))
            ]
        )
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=msg_text, quick_reply=quick_reply)
        )

    elif text in ["設定:簡易版", "簡易版"]:
        supabase_mgr.set_user_mode(line_user_id, "simple")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="📷 講評出力モードを【簡易版】に変更しました。\n次回の写真送信から高速（約3〜5秒）でカード画像と要約が送信されます。")
        )

    elif text in ["設定:詳細版", "詳細版"]:
        supabase_mgr.set_user_mode(line_user_id, "full")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="📝 講評出力モードを【詳細版】に変更しました。\n次回の写真送信からカード画像と全文講評テキストが送信されます。")
        )


@app.post("/webhook")
async def callback(request: Request, background_tasks: BackgroundTasks, x_line_signature: str = Header(None)):
    if not x_line_signature:
        raise HTTPException(status_code=400, detail="Missing signature")

    body = (await request.body()).decode("utf-8")

    try:
        events = parser.parse(body, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if isinstance(event, MessageEvent):
            line_user_id = event.source.user_id
            reply_token = event.reply_token

            if isinstance(event.message, ImageMessage):
                message_id = event.message.id
                background_tasks.add_task(
                    process_image_and_reply,
                    reply_token,
                    line_user_id,
                    message_id
                )
            elif isinstance(event.message, TextMessage):
                text_content = event.message.text.strip()
                handle_text_message(reply_token, line_user_id, text_content)

    return "OK"
