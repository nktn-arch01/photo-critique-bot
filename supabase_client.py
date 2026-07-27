import os
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from supabase import create_client, Client
except ImportError:
    # ライブラリ未インストール時のフォールバック定義
    create_client = None
    Client = Any


class SupabaseManager:
    """
    Supabase DBおよびStorageへのアクセスを一元管理するクラス
    """
    def __init__(self):
        self.url: str = os.getenv("SUPABASE_URL", "")
        self.key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_KEY", ""))
        self.client: Optional[Client] = None

        if create_client and self.url and self.key:
            self.client = create_client(self.url, self.key)

    def get_user_mode(self, line_user_id: str) -> str:
        """
        ユーザーの出力モード ('compact' または 'full') を取得する
        未設定の場合はデフォルトの 'compact' を返す
        """
        if not self.client:
            return "compact"

        try:
            res = self.client.table("user_settings").select("output_mode").eq("line_user_id", line_user_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0].get("output_mode", "compact")
        except Exception:
            pass

        return "compact"

    def upload_card_image(self, card_path: Path, file_name: str) -> str:
        """
        評価カード画像を Supabase Storage ('critique-cards') にアップロードし、公開URLを返す
        """
        if not self.client or not card_path.exists():
            return ""

        bucket_name = "cards"
        destination_path = file_name

        try:
            with open(card_path, "rb") as f:
                # 既存ファイルが存在する場合は上書きアップロード
                self.client.storage.from_(bucket_name).upload(
                    path=destination_path,
                    file=f,
                    file_options={"content-type": "image/png", "x-upsert": "true"}
                )
            
            # 公開URLを取得
            public_url = self.client.storage.from_(bucket_name).get_public_url(destination_path)
            return public_url
        except Exception as e:
            print(f"[Supabase Storage Error] {e}")
            return ""

    def save_critique_log(
        self,
        line_user_id: str,
        image_url: str,
        critique_text: str,
        card_image_url: str = ""
    ) -> bool:
        """
        講評結果テキストをパースし、Supabase DB ('critique_logs') へ保存する
        """
        if not self.client:
            return False

        # テキストパース
        title_m = re.search(r'■TITLE:\s*(.+)', critique_text)
        summary_m = re.search(r'■SUMMARY:\s*(.+)', critique_text)
        crit_sum_m = re.search(r'■CRITIQUE_SUMMARY:\s*(.+)', critique_text)
        
        scores = {}
        score_pattern = re.compile(r'・([^:\s]+)\s*:\s*([★☆]+)\s*\(([\d\.]+)/5\)')
        for m in score_pattern.finditer(critique_text):
            scores[m.group(1)] = {"stars": m.group(2), "val": m.group(3)}

        payload = {
            "line_user_id": line_user_id,
            "image_url": image_url,
            "title": title_m.group(1).strip() if title_m else "",
            "summary": summary_m.group(1).strip() if summary_m else "",
            "scores_json": scores,
            "critique_summary": crit_sum_m.group(1).strip() if crit_sum_m else "",
            "full_critique_text": critique_text,
            "card_image_url": card_image_url
        }

        try:
            self.client.table("critique_logs").insert(payload).execute()
            return True
        except Exception as e:
            print(f"[Supabase DB Error] {e}")
            return False
