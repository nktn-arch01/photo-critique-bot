import os
import shutil
import tempfile
import traceback
from pathlib import Path
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Header
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, ImageMessage, TextSendMessage, ImageSendMessage
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
    """
    スリープ防止用ヘルスチェックエンドポイント
    (UptimeRobot等の外部サービスから14分おきに叩くことで常時ウォーム状態を維持)
    """
    return {"status": "ok", "service": "Photo AI Critique Bot"}


def process_image_and_reply(reply_token: str, line_user_id: str, message_id: str):
    """
    非同期バックグラウンド処理
    - 個人情報・画像データの完全即時削除を保証 (finally節で処理終了時にフォルダ丸ごと全削除)
    - message_id ごとの独立一時フォルダ構造により他ユーザーとのデータ混同を100%遮断
    """
    temp_dir = Path(tempfile.mkdtemp())
    img_path = temp_dir / f"{message_id}.jpg"
    card_path = temp_dir / f"{message_id}_card.png"

    try:
        # 1. LINEサーバーから画像バイナリを取得
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

        # 5. カード画像を Supabase Storage (critique-cards) にアップロード
        card_public_url = supabase_mgr.upload_card_image(
            card_path=card_path,
            file_name=f"{message_id}_card.png",
            bucket_name="critique-cards"
        )

        # 6. Supabase DB に分析ログを保存
        supabase_mgr.save_critique_log(
            line_user_id=line_user_id,
            image_url="",
            critique_text=critique_text,
            card_image_url=card_public_url
        )

        # 7. 特定の line_user_id に対してのみ応答を送信 (他ユーザーへの誤送信防止)
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
        print(f"[Processing Error] {e}")
        traceback.print_exc()
        try:
            line_bot_api.push_message(
                line_user_id,
                TextSendMessage(text="申し訳ありません。写真の解析中にエラーが発生しました。もう一度お試しください。")
            )
        except Exception:
            pass
    finally:
        # サーバー上の一次ファイル・フォルダを完全物理削除 (セキュリティ・プライバシー保護)
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/webhook")
async def callback(request: Request, background_tasks: BackgroundTasks, x_line_signature: str = Header(None)):
    """
    LINE Webhook 受信エンドポイント (WebhookParser 方式)
    """
    if not x_line_signature:
        raise HTTPException(status_code=400, detail="Missing signature")

    body = (await request.body()).decode("utf-8")

    try:
        # 署名検証とイベント抽出
        events = parser.parse(body, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, ImageMessage):
            line_user_id = event.source.user_id
            message_id = event.message.id
            reply_token = event.reply_token

            # FastAPIの依存関係注入を活かした安全なタスク登録
            background_tasks.add_task(
                process_image_and_reply,
                reply_token,
                line_user_id,
                message_id
            )

    return "OK"
