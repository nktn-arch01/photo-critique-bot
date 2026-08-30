"""Guided 画面向けの講評エラー文。通信の生文や『API』でオーナーを驚かせない。"""

from __future__ import annotations

from ai_vision import is_quota_or_rate_limit_error
from critique_engine import CritiqueContractError

OWNER_RETRY = "言葉を読み取れませんでした。「もう一度」を押してください。"
OWNER_AZIMUTH = "言葉が光の向きと合いませんでした。「もう一度」を押してください。"
OWNER_BUSY = "いま混み合っています。少し待ってから、「もう一度」を押してください。"
OWNER_MISSING_KEY = "OpenAI の鍵が見つかりません。~/.openai_api_key を確認してください。"


def owner_critique_error(exc: BaseException) -> str:
    """例外を、選ぶ／読むに出す一文にする。"""
    if isinstance(exc, CritiqueContractError):
        return OWNER_AZIMUTH
    if is_quota_or_rate_limit_error(exc):
        return OWNER_BUSY
    text = str(exc)
    if "見つかりません" in text or "APIキー" in text:
        return OWNER_MISSING_KEY
    return OWNER_RETRY
