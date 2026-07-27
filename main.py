import os
import shutil
import tempfile
from pathlib import Path
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Header
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, ImageMessage, TextSendMessage, ImageSendMessage
)

from critique_engine import generate_critique
from generate_critique_card import create_critique_card
from supabase_client import SupabaseManager

app = FastAPI(title="Photo AI Critique LINE Bot")

# 環境変数からのキー取得
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
supabase_mgr = SupabaseManager()


def process_image_and_reply(reply_token: str, line_user_id: str, message_id: str):
    """
    バックグラウンドで実行される重い解析・カード生成・送信処理
    """
    temp_dir = Path(tempfile.mkdtemp())
    img_path = temp_dir / f"{message_id}.jpg"
    card_path = temp_dir / f"{message_id}_card.png"

    try:
        # 1. LINEサーバーから画像バイナリを取得して保存
        message_content = line_bot_api.get_message_content(message_id)
        with open(img_path, "wb") as f:
            for chunk in message_content.iter_content():
                f.write(chunk)

        # 2. ユーザー設定の出力モード ('compact' or 'full') を取得
        user_mode = supabase_mgr.get_user_mode(line_user_id)

        # 3. AI講評生成 (共通モジュール)
        critique_text = generate_critique(img_path)

        # 4. 評価カード画像生成 (共通モジュール)
        create_critique_card(img_path, critique_text, card_path)

        # 5. カード画像を Supabase Storage にアップロードして公開URLを取得
        card_public_url = supabase_mgr.upload_card_image(card_path, f"{message_id}_card.png")

        # 6. Supabase DB に分析ログを保存
        supabase_mgr.save_critique_log(
            line_user_id=line_user_id,
            image_url="",
            critique_text=critique_text,
            card_image_url=card_public_url
        )

        # 7. LINEユーザーへ応答を送信 (プッシュ通知)
        messages_to_send = []

        # カード画像メッセージ (URLが存在する場合)
        if card_public_url:
            messages_to_send.append(
                ImageSendMessage(
                    original_content_url=card_public_url,
                    preview_image_url=card_public_url
                )
            )

        # テキストメッセージ (モードに応じて分岐)
        if user_mode == "full":
            messages_to_send.append(TextSendMessage(text=critique_text))
        else:
            # compactモード: タイトル＋サマリー＋好奇心を煽るフック要約のみ
            import re
            title_m = re.search(r'■TITLE:\s*(.+)', critique_text)
            crit_sum_m = re.search(r'■CRITIQUE_SUMMARY:\s*(.+)', critique_text)
            
            title_str = title_m.group(1).strip() if title_m else "写真分析講評"
            crit_sum_str = crit_sum_m.group(1).strip() if crit_sum_m else "分析が完了しました。"
            
            compact_msg = f"📷【{title_str}】\n\n{crit_sum_str}"
            messages_to_send.append(TextSendMessage(text=compact_msg))

        line_bot_api.push_message(line_user_id, messages_to_send)

    except Exception as e:
        print(f"[Processing Error] {e}")
        try:
            line_bot_api.push_message(
                line_user_id,
                TextSendMessage(text="申し訳ありません。写真の解析中にエラーが発生しました。もう一度お試しください。")
            )
        except Exception:
            pass
    finally:
        # 一時ファイルの完全削除 (クリーンアップ)
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/callback")
async def callback(request: Request, background_tasks: BackgroundTasks, x_line_signature: str = Header(None)):
    """
    LINE Webhook 受信エンドポイント
    """
    if not x_line_signature:
        raise HTTPException(status_code=400, detail="Missing signature")

    body = (await request.body()).decode("utf-8")

    try:
        # 署名検証
        handler.handle(body, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    return "OK"


@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event, background_tasks: BackgroundTasks):
    """
    画像メッセージ受信時のハンドラー
    """
    line_user_id = event.source.user_id
    message_id = event.message.id
    reply_token = event.reply_token

    # バックグラウンドタスクとして重い処理を非同期実行
    background_tasks.add_task(
        process_image_and_reply,
        reply_token,
        line_user_id,
        message_id
    )
