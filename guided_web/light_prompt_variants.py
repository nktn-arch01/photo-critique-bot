"""Guided 光方位プロンプトの上限つき案（最大3）。自動で無限に書き換えない。

判定は朝夕逆転が無いこと（prompt_contracts.check_output_east_west_reversal）。
"""

from __future__ import annotations

from typing import Literal

LightPromptVariant = Literal["azimuth_fact", "direction_only", "title_slot_ban"]

# 試す順。先頭が現行に近い。本番の既定は評価後に選ぶ。
VARIANT_IDS: tuple[LightPromptVariant, ...] = (
    "azimuth_fact",
    "direction_only",
    "title_slot_ban",
)

# ブルーアワーという語が夕の連想を呼びやすいので、本番は方位だけの案を既定にする。
DEFAULT_VARIANT: LightPromptVariant = "title_slot_ban"

_TWILIGHT_NAME_BITS = ("・ブルーアワー相当", "・ゴールデンアワー相当")

_TITLE_SLOT_RULE = """
■TITLE と ■SUMMARY は光の方位の事実に合わせる。東の空／一日の前半のとき、『夕』で始まる語（夕暮れ・夕刻・夕方・夕景）を TITLE・SUMMARY・タグに出さない。西の空／一日の後半のとき、『朝日』『早朝』を出さない。
"""


def present_light_hint(hint: str, variant: str) -> str:
    """案ごとにヒント文面を変える。天文計算の結果自体は変えない。"""
    text = hint or ""
    if variant == "azimuth_fact":
        return text
    for bit in _TWILIGHT_NAME_BITS:
        text = text.replace(bit, "")
    return text


def extra_phase1_rules(variant: str) -> str:
    if variant == "title_slot_ban":
        return _TITLE_SLOT_RULE.strip()
    return ""
