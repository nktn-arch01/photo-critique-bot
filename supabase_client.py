import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = Any

from critique_parser import parse_critique_text


class SupabaseManager:
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
            res = self.client.table("user_settings").select("mode").eq("user_id", line_user_id).execute()
            if res.data and len(res.data) > 0:
                mode_val = res.data[0].get("mode", "compact")
                return "full" if mode_val in ["full", "detail"] else "compact"
        except Exception as e:
            print(f"[Supabase get_user_mode Error] {e}", flush=True)

        return "compact"

    def set_user_mode(self, line_user_id: str, mode: str) -> bool:
        if not self.client:
            return False

        try:
            payload = {
                "user_id": line_user_id,
                "mode": mode
            }
            self.client.table("user_settings").upsert(payload, on_conflict="user_id").execute()
            print(f"[Supabase set_user_mode Success] user_id: {line_user_id}, mode: {mode}", flush=True)
            return True
        except Exception as e:
            print(f"[Supabase set_user_mode Error] {e}", flush=True)
            return False

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

        # 共通パーサーを使用してパース漏れを完全回避
        parsed = parse_critique_text(critique_text)

        payload = {
            "line_user_id": line_user_id,
            "image_url": image_url,
            "title": parsed["title"],
            "summary": parsed["summary"],
            "scores_json": json.loads(json.dumps(parsed["scores"], ensure_ascii=False)),
            "critique_summary": parsed["point_text"],
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