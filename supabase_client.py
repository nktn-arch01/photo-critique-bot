import os
import json
from pathlib import Path
from typing import Any, Optional

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = Any  # type: ignore[misc,assignment]

from critique_parser import parse_critique_text
from card_theme import DEFAULT_CARD_THEME, normalize_card_theme
from line_reactions import REACTION_VALUES, parse_reaction_label
from privacy_utils import (
    card_signed_url_seconds,
    redact_line_user_id,
    should_save_critique_db,
    full_critique_text_for_storage,
)


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
            print(
                f"[Supabase set_user_mode Success] user={redact_line_user_id(line_user_id)}, mode={mode}",
                flush=True,
            )
            return True
        except Exception as e:
            print(f"[Supabase set_user_mode Error] {e}", flush=True)
            return False

    def get_user_card_theme(self, line_user_id: str) -> str:
        """カード背景テーマ (dark / light)。列未作成時は DEFAULT。"""
        if not self.client:
            return DEFAULT_CARD_THEME

        try:
            res = (
                self.client.table("user_settings")
                .select("card_theme")
                .eq("user_id", line_user_id)
                .execute()
            )
            if res.data and len(res.data) > 0:
                return normalize_card_theme(res.data[0].get("card_theme"))
        except Exception as e:
            print(f"[Supabase get_user_card_theme Error] {e}", flush=True)

        return DEFAULT_CARD_THEME

    def set_user_card_theme(self, line_user_id: str, theme: str) -> bool:
        if not self.client:
            return False

        theme_norm = normalize_card_theme(theme)
        try:
            payload = {
                "user_id": line_user_id,
                "card_theme": theme_norm,
            }
            self.client.table("user_settings").upsert(payload, on_conflict="user_id").execute()
            print(
                f"[Supabase set_user_card_theme Success] "
                f"user={redact_line_user_id(line_user_id)}, theme={theme_norm}",
                flush=True,
            )
            return True
        except Exception as e:
            print(f"[Supabase set_user_card_theme Error] {e}", flush=True)
            return False

    def _card_access_url(self, bucket_name: str, destination_path: str) -> str:
        signed_sec = card_signed_url_seconds()
        if signed_sec:
            res = self.client.storage.from_(bucket_name).create_signed_url(destination_path, signed_sec)
            if isinstance(res, dict):
                return res.get("signedURL") or res.get("signedUrl") or ""
            return str(res)
        return self.client.storage.from_(bucket_name).get_public_url(destination_path)

    def upload_card_image(
        self,
        card_path: Path,
        storage_path: str,
        bucket_name: str = "critique-cards",
    ) -> str:
        if not self.client or not card_path.exists():
            return ""

        try:
            with open(card_path, "rb") as f:
                self.client.storage.from_(bucket_name).upload(
                    path=storage_path,
                    file=f,
                    file_options={"content-type": "image/png", "x-upsert": "true"},
                )

            url = self._card_access_url(bucket_name, storage_path)
            print(f"[Supabase Storage Success] path={storage_path}", flush=True)
            return url
        except Exception as e:
            print(f"[Supabase Storage Error] {e}", flush=True)
            return ""

    def save_critique_log(
        self,
        line_user_id: str,
        image_url: str,
        critique_text: str,
        card_image_url: str = "",
    ) -> str | None:
        """講評ログを保存。成功時は行 id（文字列）を返す。失敗・スキップ時は None。"""
        if not should_save_critique_db():
            print("[Supabase DB] CRITIQUE_SAVE_DB=false — skip insert", flush=True)
            return None

        if not self.client:
            print("[Supabase DB Error] Client not initialized", flush=True)
            return None

        parsed = parse_critique_text(critique_text)
        full_text = full_critique_text_for_storage(critique_text)

        payload = {
            "line_user_id": line_user_id,
            "image_url": image_url,
            "title": parsed["title"],
            "summary": parsed["summary"],
            "scores_json": json.loads(json.dumps(parsed["scores"], ensure_ascii=False)),
            "critique_summary": parsed["point_text"],
            "full_critique_text": full_text,
            "card_image_url": card_image_url,
        }

        try:
            res = self.client.table("critique_logs").insert(payload).execute()
            row_id = None
            if res.data and len(res.data) > 0:
                row_id = str(res.data[0].get("id") or "") or None
            print(
                f"[Supabase DB Success] user={redact_line_user_id(line_user_id)} id={row_id}",
                flush=True,
            )
            return row_id
        except Exception as e:
            print(f"[Supabase DB Error] {e}", flush=True)
            return None

    def save_user_reaction(self, line_user_id: str, reaction: str) -> bool:
        """直近の未反応 critique_logs 行に user_reaction を書く。

        列未作成時は失敗ログのみ（アプリは落ちない）。
        """
        value = parse_reaction_label(reaction) if reaction not in REACTION_VALUES else reaction
        if value is None or value not in REACTION_VALUES:
            return False
        if not self.client:
            return False

        try:
            # 最新ログを1件取得
            res = (
                self.client.table("critique_logs")
                .select("id,user_reaction")
                .eq("line_user_id", line_user_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if not res.data:
                print(
                    f"[Supabase reaction] no log for user={redact_line_user_id(line_user_id)}",
                    flush=True,
                )
                return False
            row = res.data[0]
            row_id = row.get("id")
            if row.get("user_reaction"):
                # 上書き更新（同じ講評への再タップを許可）
                pass
            self.client.table("critique_logs").update({"user_reaction": value}).eq(
                "id", row_id
            ).execute()
            print(
                f"[Supabase reaction Success] user={redact_line_user_id(line_user_id)} "
                f"id={row_id} reaction={value}",
                flush=True,
            )
            return True
        except Exception as e:
            print(f"[Supabase reaction Error] {e}", flush=True)
            return False
