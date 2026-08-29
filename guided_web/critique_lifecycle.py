"""Guided 講評ライフサイクルの正本。

ユーザー操作は Intent、講評への効果は Effect の3つだけ。
「キャンセルした／してない」という第四の状態は持たない。
詳細: docs/P2_2_GUIDED_CRITIQUE_LIFECYCLE.md
"""

from __future__ import annotations

from enum import Enum


class UserIntent(str, Enum):
    SPEAK = "speak"
    AGAIN = "again"
    TAB_SWITCH = "tab_switch"
    CLEAR = "clear"
    PHOTO_REPLACE_SUCCESS = "photo_replace_success"
    PHOTO_REPLACE_FAIL = "photo_replace_fail"
    PHOTO_PICK_CANCEL = "photo_pick_cancel"
    PHASE2_RETRY = "phase2_retry"
    EXPORT_SAVE = "export_save"
    EXPORT_CANCEL = "export_cancel"
    PAGE_UNLOAD = "page_unload"
    PAGE_BFCACHE = "page_bfcache"


class CritiqueEffect(str, Enum):
    """講評セッションへの効果。これ以外は表せない。"""

    NOOP = "noop"
    SUPERSEDE = "supersede"
    DESTROY_SESSION = "destroy"


_EFFECTS: dict[UserIntent, CritiqueEffect] = {
    UserIntent.TAB_SWITCH: CritiqueEffect.NOOP,
    UserIntent.AGAIN: CritiqueEffect.NOOP,
    UserIntent.PHOTO_PICK_CANCEL: CritiqueEffect.NOOP,
    UserIntent.PHOTO_REPLACE_FAIL: CritiqueEffect.NOOP,
    UserIntent.EXPORT_CANCEL: CritiqueEffect.NOOP,
    UserIntent.EXPORT_SAVE: CritiqueEffect.NOOP,
    UserIntent.PAGE_BFCACHE: CritiqueEffect.NOOP,
    UserIntent.SPEAK: CritiqueEffect.SUPERSEDE,
    UserIntent.PHASE2_RETRY: CritiqueEffect.SUPERSEDE,
    UserIntent.CLEAR: CritiqueEffect.DESTROY_SESSION,
    UserIntent.PHOTO_REPLACE_SUCCESS: CritiqueEffect.DESTROY_SESSION,
    UserIntent.PAGE_UNLOAD: CritiqueEffect.DESTROY_SESSION,
}


def effect_for(intent: UserIntent) -> CritiqueEffect:
    """操作に対する唯一の効果。表に無い操作は追加しない。"""
    try:
        return _EFFECTS[intent]
    except KeyError as exc:
        raise ValueError(f"unknown guided critique intent: {intent}") from exc


def keeps_photo(intent: UserIntent) -> bool:
    """写真セッションを残すか。destroy だけ捨てる。"""
    return effect_for(intent) is not CritiqueEffect.DESTROY_SESSION


def may_call_critique_cancel(_intent: UserIntent) -> bool:
    """画面操作から /critique/cancel を呼んでよいか。常に不可。"""
    return False
