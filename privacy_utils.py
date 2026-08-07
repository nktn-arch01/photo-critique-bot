"""ログ・Storage パス用のプライバシー補助（個人識別子の露出を減らす）。"""

import hashlib
import os


def redact_line_user_id(line_user_id: str) -> str:
    """Render ログ等に載せる際の LINE user ID マスク。"""
    if not line_user_id:
        return "(empty)"
    if len(line_user_id) <= 10:
        return "***"
    return f"{line_user_id[:4]}…{line_user_id[-4:]}"


def storage_folder_for_user(line_user_id: str) -> str:
    """Storage 上のユーザーフォルダ名（生の LINE ID をパスに含めない）。"""
    salt = os.getenv("STORAGE_PATH_SALT", "photo-ai-critique")
    digest = hashlib.sha256(f"{salt}:{line_user_id}".encode("utf-8")).hexdigest()
    return digest[:16]


def should_save_critique_db() -> bool:
    return os.getenv("CRITIQUE_SAVE_DB", "true").strip().lower() in ("1", "true", "yes")


def should_save_full_critique_text() -> bool:
    return os.getenv("CRITIQUE_SAVE_FULL_TEXT", "true").strip().lower() in ("1", "true", "yes")


def storage_path_from_card_url(card_image_url: str) -> str | None:
    """Supabase Storage の card URL からオブジェクトパス（例: abcd…/msg_card.png）を取り出す。"""
    if not card_image_url:
        return None
    for marker in ("/object/sign/critique-cards/", "/object/public/critique-cards/"):
        if marker in card_image_url:
            rest = card_image_url.split(marker, 1)[1]
            return rest.split("?", 1)[0].strip() or None
    return None


def card_signed_url_seconds() -> int | None:
    """設定時は Public URL の代わりに署名付き URL を返す（バケット非公開向け）。"""
    raw = os.getenv("SUPABASE_CARD_SIGNED_SECONDS", "").strip()
    if not raw:
        return None
    try:
        sec = int(raw)
        return sec if sec > 0 else None
    except ValueError:
        return None
