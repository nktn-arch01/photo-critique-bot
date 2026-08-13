"""LINE 講評後のユーザー反応（Quick Reply）の識別子・文言。"""

from __future__ import annotations

# DB / 内部キー
REACTION_GOOD = "good"
REACTION_MIXED = "mixed"
REACTION_WEAK = "weak"

REACTION_VALUES: tuple[str, ...] = (REACTION_GOOD, REACTION_MIXED, REACTION_WEAK)

# ユーザーがタップしたときに送られるテキスト（ボタンラベルと一致）
REACTION_LABEL_GOOD = "👍 いいね"
REACTION_LABEL_MIXED = "💭 もう少し"
REACTION_LABEL_WEAK = "😐 いまいち"

_LABEL_TO_VALUE: dict[str, str] = {
    REACTION_LABEL_GOOD: REACTION_GOOD,
    REACTION_LABEL_MIXED: REACTION_MIXED,
    REACTION_LABEL_WEAK: REACTION_WEAK,
    # テキスト揺れ用
    "いいね": REACTION_GOOD,
    "もう少し": REACTION_MIXED,
    "いまいち": REACTION_WEAK,
}

_VALUE_TO_ACK: dict[str, str] = {
    REACTION_GOOD: "ありがとうございます。いいね、として残しました。",
    REACTION_MIXED: "ありがとうございます。もう少し、として残しました。",
    REACTION_WEAK: "ありがとうございます。いまいち、として残しました。",
}


def parse_reaction_label(text: str) -> str | None:
    """ユーザー送信テキスト → good/mixed/weak。該当しなければ None。"""
    key = (text or "").strip()
    return _LABEL_TO_VALUE.get(key)


def reaction_ack_message(value: str) -> str:
    return _VALUE_TO_ACK.get(value, "反応を受け取りました。ありがとうございます。")


def reaction_quick_reply_items() -> list[tuple[str, str]]:
    """(button_label, message_text) — LINE QuickReply 用。"""
    return [
        (REACTION_LABEL_GOOD, REACTION_LABEL_GOOD),
        (REACTION_LABEL_MIXED, REACTION_LABEL_MIXED),
        (REACTION_LABEL_WEAK, REACTION_LABEL_WEAK),
    ]
