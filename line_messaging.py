"""LINE Messaging API 向けテキスト分割（追加 API 呼び出しはバッチ上限超過時のみ）。"""

import re

from linebot import LineBotApi
from linebot.models import Message

# LINE 公式: テキスト1通あたり最大 5000 文字 / 1リクエスト最大 5 メッセージ
LINE_TEXT_MESSAGE_MAX = 5000
LINE_SAFE_CHUNK_SIZE = 4800
LINE_MAX_MESSAGES_PER_REQUEST = 5

# Wave C: 対話は 【1】【2】【3】のみを3通（カードは別途 Image）
_DIALOGUE_SECTION_HEADING = re.compile(r"##\s*【([123])\.")


def split_dialogue_sections_1_to_3(text: str) -> list[str]:
    """Full 講評から 【1】【2】【3】をそれぞれ1通ずつ取り出す（カード・Phase1見出しは含めない）。"""
    text = text.strip()
    if not text:
        return []

    indices: dict[str, int] = {}
    for m in _DIALOGUE_SECTION_HEADING.finditer(text):
        num = m.group(1)
        if num not in indices:
            indices[num] = m.start()

    i1 = indices.get("1")
    if i1 is None:
        # フォールバック: 旧4分割互換（Phase1+【1〜】がまとまっている場合）
        return split_full_critique_for_line_legacy(text)

    i2 = indices.get("2")
    i3 = indices.get("3")
    # 【4】以降は捨てる
    end_of_3 = None
    m4 = re.search(r"##\s*【4\.", text)
    if m4:
        end_of_3 = m4.start()

    parts: list[str] = []
    if i2 is not None:
        parts.append(text[i1:i2].strip())
        if i3 is not None:
            parts.append(text[i2:i3].strip())
            parts.append(text[i3:end_of_3].strip() if end_of_3 is not None else text[i3:].strip())
        else:
            parts.append(text[i2:end_of_3].strip() if end_of_3 is not None else text[i2:].strip())
    else:
        parts.append(text[i1:end_of_3].strip() if end_of_3 is not None else text[i1:].strip())

    return [p for p in parts if p]


def split_full_critique_for_line_legacy(text: str) -> list[str]:
    """旧: 詳細版を4通分割（Phase1 + 【1】/【4】/【6】）。テスト・フォールバック用。"""
    _FULL_SECTION_HEADING = re.compile(r"##\s*【([146])\.")
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


def split_full_critique_for_line(text: str) -> list[str]:
    """Wave C: LINE 対話返信は 【1】【2】【3】の3通（カードは別送）。

    本文に 【2】【3】見出しが無い旧サンプルでは legacy 4分割にフォールバックする。
    """
    text = text.strip()
    if not text:
        return []
    if _DIALOGUE_SECTION_HEADING.search(text) and re.search(r"##\s*【2\.", text):
        return split_dialogue_sections_1_to_3(text)
    # 【1】と【4】だけの旧テストデータ → 対話部分だけ返す意図で legacy の2通目以降
    legacy = split_full_critique_for_line_legacy(text)
    if len(legacy) >= 2 and "■TITLE" in legacy[0]:
        # Phase1 通を除き、本文側を返す（最大3通）
        return legacy[1:4]
    return split_dialogue_sections_1_to_3(text)


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
