"""LINE Messaging API 向けテキスト分割（追加 API 呼び出しはバッチ上限超過時のみ）。"""

import re

from linebot import LineBotApi
from linebot.models import Message

# LINE 公式: テキスト1通あたり最大 5000 文字 / 1リクエスト最大 5 メッセージ
LINE_TEXT_MESSAGE_MAX = 5000
LINE_SAFE_CHUNK_SIZE = 4800
LINE_MAX_MESSAGES_PER_REQUEST = 5

# 詳細版講評本文の見出し（表記揺れ: ## の後ろの空白、全角数字は非対応）
_FULL_SECTION_HEADING = re.compile(r"##\s*【([146])\.")


def split_full_critique_for_line(text: str) -> list[str]:
    """
    詳細版全文を読みやすい4通に分割する。
    1通目: ## 【1. より前（Phase1 の TITLE/SUMMARY/SCORES 等）
    2通目: ## 【1. 〜 ## 【4. より前
    3通目: ## 【4. 〜 ## 【6. より前
    4通目: ## 【6. 〜 末尾（【7】含む）
    """
    text = text.strip()
    if not text:
        return []

    indices: dict[str, int] = {}
    for m in _FULL_SECTION_HEADING.finditer(text):
        num = m.group(1)
        if num not in indices:
            indices[num] = m.start()

    i1 = indices.get("1")
    i4 = indices.get("4")
    i6 = indices.get("6")

    if i1 is None:
        return [text]

    parts = [
        text[:i1].strip(),
        text[i1:i4].strip() if i4 is not None else text[i1:].strip(),
    ]
    if i4 is not None:
        parts.append(text[i4:i6].strip() if i6 is not None else text[i4:].strip())
    else:
        parts.append("")
    if i6 is not None:
        parts.append(text[i6:].strip())
    else:
        parts.append("")

    return [p for p in parts if p]


def split_text_for_line(text: str, max_len: int = LINE_SAFE_CHUNK_SIZE) -> list[str]:
    """長文を LINE 上限内のチャンクに分割（簡易版など・改行優先）。"""
    text = text.strip()
    if not text:
        return [""]
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        window = remaining[:max_len]
        break_at = window.rfind("\n\n")
        if break_at < max_len // 3:
            break_at = window.rfind("\n")
        if break_at < max_len // 3:
            break_at = max_len

        chunks.append(remaining[:break_at].rstrip())
        remaining = remaining[break_at:].lstrip()

    return chunks


def push_messages_in_batches(line_bot_api: LineBotApi, user_id: str, messages: list[Message]) -> None:
    """5件ずつ push（上限超過分のみ追加リクエスト）。"""
    batch: list[Message] = []
    for msg in messages:
        batch.append(msg)
        if len(batch) >= LINE_MAX_MESSAGES_PER_REQUEST:
            line_bot_api.push_message(user_id, batch)
            batch = []
    if batch:
        line_bot_api.push_message(user_id, batch)
