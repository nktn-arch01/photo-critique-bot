import os
import shutil
import tempfile
import traceback
from pathlib import Path
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Header
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, ImageMessage, TextMessage, StickerMessage, TextSendMessage, ImageSendMessage,
    QuickReply, QuickReplyButton, MessageAction
)

from critique_engine import generate_critique_for_line
from generate_critique_card import create_critique_card
from line_messaging import push_messages_in_batches, split_full_critique_for_line, split_text_for_line
from supabase_client import SupabaseManager
from critique_parser import parse_critique_text
from ai_vision import sniff_image_mime
from privacy_utils import redact_line_user_id, storage_folder_for_user
from scanner import extract_file_metadata

app = FastAPI(title="Photo AI Critique LINE Bot")

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(LINE_CHANNEL_SECRET)
supabase_mgr = SupabaseManager()


@app.get("/health")
@app.head("/health")
def health_check():
    return {"status": "ok", "service": "Photo AI Critique Bot"}


@app.on_event("startup")
def log_startup_config():
    gemini = "set" if os.getenv("GEMINI_API_KEY") else "MISSING"
    openai_key = "set" if os.getenv("OPENAI_API_KEY") else "MISSING"
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash (default)")
    print(
        f"[Startup] LINE compact/full -> OpenAI (override: LINE_COMPACT_PROVIDER=gemini), "
        f"OPENAI_API_KEY={openai_key}, GEMINI_API_KEY={gemini}, GEMINI_MODEL={gemini_model}",
        flush=True,
    )


def reply_image_received(reply_token: str, line_user_id: str) -> None:
    """Webhook 内で即時返信（reply_token は約30秒で失効するためここでのみ使用）。"""
    mode = supabase_mgr.get_user_mode(line_user_id)
    mode_label = "詳細版" if mode == "full" else "簡易版"
    wait_hint = "30秒ほど" if mode == "full" else "15秒ほど"
    try:
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(
                text=(
                    f"📷 写真を受け取りました（{mode_label}）。\n"
                    f"AIが講評とカード画像を作成しています（{wait_hint}）。\n"
                    "完成次第、このトークに送信します。"
                )
            ),
        )
    except Exception as e:
        print(f"[LINE reply ack error] {e}", flush=True)


def process_image_and_reply(line_user_id: str, message_id: str):
    temp_dir = Path(tempfile.mkdtemp())
    img_path = temp_dir / "pending.jpg"
    card_path = temp_dir / f"{message_id}_card.png"

    try:
        message_content = line_bot_api.get_message_content(message_id)
        image_bytes = b"".join(message_content.iter_content())
        mime = sniff_image_mime(image_bytes)
        ext = ".png" if mime == "image/png" else ".jpg"
        img_path = temp_dir / f"{message_id}{ext}"
        img_path.write_bytes(image_bytes)

        user_mode = supabase_mgr.get_user_mode(line_user_id)
        print(
            f"[LINE] user={redact_line_user_id(line_user_id)} mode={user_mode} "
            f"image={mime} bytes={len(image_bytes)}",
            flush=True,
        )

        # ★ 画像からメタデータ（時間帯情報 time_zone_fact 等）を抽出
        exif_meta, dop_info, _ = extract_file_metadata(img_path)

        critique_text = generate_critique_for_line(
            img_path,
            metadata=exif_meta,
            dop_info=dop_info,
            mode=user_mode,
        )
        
        create_critique_card(img_path, critique_text, card_path)

        storage_path = f"{storage_folder_for_user(line_user_id)}/{message_id}_card.png"
        card_public_url = supabase_mgr.upload_card_image(
            card_path=card_path,
            storage_path=storage_path,
            bucket_name="critique-cards",
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
            for part in split_full_critique_for_line(critique_text):
                messages_to_send.append(TextSendMessage(text=part))
        else:
            parsed = parse_critique_text(critique_text)
            compact_msg = f"📷【{parsed['title']}】\n\n{parsed['point_text']}"
            for part in split_text_for_line(compact_msg):
                messages_to_send.append(TextSendMessage(text=part))

        push_messages_in_batches(line_bot_api, line_user_id, messages_to_send)

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
        supabase_mgr.set_user_mode(line_user_id, "compact")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="📷 講評出力モードを【簡易版】に変更しました。\n次回の写真送信から高速でカード画像と要約が送信されます。")
        )

    elif text in ["設定:詳細版", "詳細版"]:
        supabase_mgr.set_user_mode(line_user_id, "full")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="📝 講評出力モードを【詳細版】に変更しました。\n次回の写真送信からカード画像と全文講評テキストが送信されます。")
        )
    else:
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="写真を送信いただくと、AIが講評とカード画像を自動生成します📷\nモードの切り替えは「設定」と送信してください。")
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
                reply_image_received(reply_token, line_user_id)
                background_tasks.add_task(
                    process_image_and_reply,
                    line_user_id,
                    message_id,
                )
            elif isinstance(event.message, TextMessage):
                text_content = event.message.text.strip()
                handle_text_message(reply_token, line_user_id, text_content)
            elif isinstance(event.message, StickerMessage):
                line_bot_api.reply_message(
                    reply_token,
                    TextSendMessage(text="スタンプありがとうございます！講評したい写真をぜひ送信してみてください📷✨")
                )
            else:
                line_bot_api.reply_message(
                    reply_token,
                    TextSendMessage(text="申し訳ありません。動画や音声、非対応のファイル形式には対応しておりません。\n静止画（JPEGまたはPNG形式の写真）を送信してください📷✨")
                )

    return "OK"