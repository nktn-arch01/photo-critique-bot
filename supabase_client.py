import os
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from supabase import create_client, Client
except ImportError:
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
        if not self.client:
            return "compact"

        try:
            # 実際のDBカラム名 user_id と mode を指定
            res = self.client.table("user_settings").select("mode").eq("user_id", line_user_id).execute()
            if res.data and len(res.data) > 0:
                mode_val = res.data[0].get("mode", "compact")
                # simple や compact は要約モード、full や detail は全文モード
                return "full" if mode_val in ["full", "detail"] else "compact"
        except Exception as e:
            print(f"[Supabase get_user_mode Error] {e}", flush=True)

        return "compact"

    def upload_card_image(self, card_path: Path, file_name: str, bucket_name: str = "critique-cards") -> str:
        if not self.client or not card_path.exists():
            return ""

        destination_path = file_name

        try:
            with open(card_path, "rb") as f:
                self.client.storage.from_(bucket_name).upload(
                    path=destination_path,
                    file=f,
                    file_options={"content-type": "image/png", "x-upsert": "true"}
                )
            
            public_url = self.client.storage.from_(bucket_name).get_public_url(destination_path)
            print(f"[Supabase Storage Success] URL: {public_url}", flush=True)
            return public_url
        except Exception as e:
            print(f"[Supabase Storage Error] {e}", flush=True)
            return ""

    def save_critique_log(
        self,
        line_user_id: str,
        image_url: str,
        critique_text: str,
        card_image_url: str = ""
    ) -> bool:
        if not self.client:
            print("[Supabase DB Error] Client not initialized", flush=True)
            return False

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
            res = self.client.table("critique_logs").insert(payload).execute()
            print(f"[Supabase DB Success] Log saved for user: {line_user_id}", flush=True)
            return True
        except Exception as e:
            print(f"[Supabase DB Error] {e}", flush=True)
            return False
