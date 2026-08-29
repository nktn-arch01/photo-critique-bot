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


def analytics_user_hash(line_user_id: str) -> str:
    """分析用の不可逆ハッシュ。STORAGE_PATH_SALT とは別の塩を使う。"""
    salt = os.getenv("ANALYTICS_HASH_SALT", "lumina-analytics")
    return hashlib.sha256(f"{salt}:{line_user_id}".encode("utf-8")).hexdigest()


CRITIQUE_EVENT_KEYS = frozenset(
    {
        "user_hash",
        "card_theme",
        "title",
        "critique_summary",
        "scores_json",
        "user_reaction",
    }
)
CRITIQUE_EVENT_FORBIDDEN_KEYS = frozenset(
    {
        "line_user_id",
        "user_id",
        "card_image_url",
        "image_url",
        "full_critique_text",
    }
)


def critique_event_payload(
    *,
    line_user_id: str,
    card_theme: str,
    title: str,
    critique_summary: str,
    scores_json: object,
    user_reaction: str | None = None,
) -> dict:
    """critique_events に書いてよい項目だけを返す（LINE ID・全文・カード URL は入れない）。"""
    payload = {
        "user_hash": analytics_user_hash(line_user_id),
        "card_theme": card_theme,
        "title": title or "",
        "critique_summary": critique_summary or "",
        "scores_json": scores_json,
    }
    if user_reaction:
        payload["user_reaction"] = user_reaction
    extra = set(payload) - CRITIQUE_EVENT_KEYS
    if extra:
        raise ValueError(f"critique_events に許可しないキー: {sorted(extra)}")
    return payload


def should_save_critique_db() -> bool:
    return os.getenv("CRITIQUE_SAVE_DB", "true").strip().lower() in ("1", "true", "yes")


def should_save_full_critique_text() -> bool:
    """DB に講評全文を残すか。既定は残さない（要約・タイトル・スコア・反応は残る）。"""
    return os.getenv("CRITIQUE_SAVE_FULL_TEXT", "false").strip().lower() in ("1", "true", "yes")


def full_critique_text_for_storage(critique_text: str) -> str:
    """critique_logs.full_critique_text に書く値。既定は空文字。"""
    if should_save_full_critique_text():
        return critique_text
    return ""


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
