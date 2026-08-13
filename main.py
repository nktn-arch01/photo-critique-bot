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
from card_theme import CARD_THEME_DARK, CARD_THEME_LIGHT, card_theme_label
from line_messaging import push_messages_in_batches, split_full_critique_for_line
from line_reactions import (
    parse_reaction_label,
    reaction_ack_message,
    reaction_quick_reply_items,
)
from supabase_client import SupabaseManager
from ai_vision import sniff_image_mime
from privacy_utils import redact_line_user_id, storage_folder_for_user
from scanner import extract_file_metadata


def _reaction_quick_reply() -> QuickReply:
    items = [
        QuickReplyButton(action=MessageAction(label=label[:20], text=text))
        for label, text in reaction_quick_reply_items()
    ]
    return QuickReply(items=items)

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
    try:
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(
                text=(
                    "📷 写真を受け取りました（カード＋対話）。\n"
                    "まずカードを送り、続けて対話【1】〜【3】を送ります（1分ほど）。"
                )
            ),
        )
    except Exception as e:
        print(f"[LINE reply ack error] {e}", flush=True)


def process_image_and_reply(line_user_id: str, message_id: str):
    """Wave C 案2: Compact→カード即時 → Phase1 短命保持 → Full【1-3】追従 → 消去。"""
    temp_dir = Path(tempfile.mkdtemp())
    img_path = temp_dir / "pending.jpg"
    card_path = temp_dir / f"{message_id}_card.png"
    phase1_cache: str | None = None

    try:
        message_content = line_bot_api.get_message_content(message_id)
        image_bytes = b"".join(message_content.iter_content())
        mime = sniff_image_mime(image_bytes)
        ext = ".png" if mime == "image/png" else ".jpg"
        img_path = temp_dir / f"{message_id}{ext}"
        img_path.write_bytes(image_bytes)

        user_theme = supabase_mgr.get_user_card_theme(line_user_id)
        print(
            f"[LINE] user={redact_line_user_id(line_user_id)} flow=card+dialogue "
            f"theme={user_theme} image={mime} bytes={len(image_bytes)}",
            flush=True,
        )

        exif_meta, dop_info, _ = extract_file_metadata(img_path)

        # 1) Compact → カード即時
        phase1_cache = generate_critique_for_line(
            img_path,
            metadata=exif_meta,
            dop_info=dop_info,
            mode="compact",
        )
        create_critique_card(img_path, phase1_cache, card_path, theme=user_theme)

        storage_path = f"{storage_folder_for_user(line_user_id)}/{message_id}_card.png"
        card_public_url = supabase_mgr.upload_card_image(
            card_path=card_path,
            storage_path=storage_path,
            bucket_name="critique-cards",
        )

        if card_public_url:
            push_messages_in_batches(
                line_bot_api,
                line_user_id,
                [
                    ImageSendMessage(
                        original_content_url=card_public_url,
                        preview_image_url=card_public_url,
                    )
                ],
            )

        # 2) Full（Phase1 注入）→ 【1】【2】【3】のみ
        full_text = generate_critique_for_line(
            img_path,
            metadata=exif_meta,
            dop_info=dop_info,
            mode="full",
            phase1_override=phase1_cache,
        )

        supabase_mgr.save_critique_log(
            line_user_id=line_user_id,
            image_url="",
            critique_text=full_text,
            card_image_url=card_public_url or "",
        )

        dialogue_parts = split_full_critique_for_line(full_text)
        text_messages = [TextSendMessage(text=part) for part in dialogue_parts]
        if text_messages:
            # N2: 対話の最後に反応 Quick Reply（いいね / もう少し / いまいち）
            last = text_messages[-1]
            text_messages[-1] = TextSendMessage(text=last.text, quick_reply=_reaction_quick_reply())
            push_messages_in_batches(line_bot_api, line_user_id, text_messages)
        else:
            # 対話分割が空でも反応を取れるように案内＋QR
            push_messages_in_batches(
                line_bot_api,
                line_user_id,
                [
                    TextSendMessage(
                        text="講評が届きました。いまの印象を選んでください。",
                        quick_reply=_reaction_quick_reply(),
                    )
                ],
            )

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
        phase1_cache = None
        shutil.rmtree(temp_dir, ignore_errors=True)


def handle_text_message(reply_token: str, line_user_id: str, text: str):
    reaction = parse_reaction_label(text)
    if reaction is not None:
        ok = supabase_mgr.save_user_reaction(line_user_id, reaction)
        ack = reaction_ack_message(reaction)
        if not ok:
            ack += "\n（記録に失敗した可能性があります。列追加 SQL を確認してください）"
        line_bot_api.reply_message(reply_token, TextSendMessage(text=ack))
        return

    if text in ["設定", "せってい", "モード設定"]:
        msg_text = (
            "⚙️【講評の送り方】\n\n"
            "現在は【カード＋対話】に統一しています。\n"
            "写真1枚ごとにカードを先に送り、続けて対話【1】〜【3】を送ります。\n"
            "最後に「いいね／もう少し／いまいち」で印象を送れます。\n\n"
            "カードの見た目は「背景」で変更できます。"
        )
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=msg_text),
        )

    elif text in ["設定:簡易版", "簡易版", "設定:詳細版", "詳細版"]:
        # 互換: 旧コマンドは受け付けるが統合フローを案内
        supabase_mgr.set_user_mode(line_user_id, "full")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(
                text=(
                    "📷 講評の送り方は【カード＋対話】に統一されています。\n"
                    "次回の写真から、カードのあと対話【1】〜【3】が届きます。"
                )
            ),
        )

    elif text in ["背景", "はいけい", "カード背景"]:
        current_theme = supabase_mgr.get_user_card_theme(line_user_id)
        theme_label = card_theme_label(current_theme)
        msg_text = (
            "🎨【カード背景設定】\n\n"
            f"現在の設定：【{theme_label}】\n\n"
            "変更したい背景を下のボタンから選択してください。"
        )
        quick_reply = QuickReply(
            items=[
                QuickReplyButton(action=MessageAction(label="⬜ ライト", text="背景:ライト")),
                QuickReplyButton(action=MessageAction(label="⬛ ダーク", text="背景:ダーク")),
            ]
        )
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=msg_text, quick_reply=quick_reply),
        )

    elif text in ["背景:ライト", "ライト"]:
        supabase_mgr.set_user_card_theme(line_user_id, CARD_THEME_LIGHT)
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(
                text="⬜ カード背景を【ライト】（白背景・黒文字）に変更しました。\n次回の写真送信から反映されます。"
            ),
        )

    elif text in ["背景:ダーク", "ダーク"]:
        supabase_mgr.set_user_card_theme(line_user_id, CARD_THEME_DARK)
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(
                text="⬛ カード背景を【ダーク】に変更しました。\n次回の写真送信から反映されます。"
            ),
        )

    else:
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(
                text=(
                    "写真を送信いただくと、カードと対話【1】〜【3】を自動生成します📷\n"
                    "・送り方の説明 → 「設定」\n"
                    "・カード背景切替 → 「背景」"
                )
            ),
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