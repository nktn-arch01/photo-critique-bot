"""2段階講評生成のオーケストレーション（プロバイダは ai_vision 経由で差し替え）。"""

import time
from pathlib import Path

from ai_vision import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OPENAI_MODEL,
    VisionProvider,
    complete_with_image,
    get_openai_client,
)
from critique_parser import parse_critique_text
from critique_prompts import CritiquePromptContext, build_phase1_prompt, build_phase2_prompt

# デスクトップ等からの後方互換
__all__ = [
    "generate_critique",
    "generate_critique_openai",
    "generate_critique_gemini",
    "generate_critique_for_line",
    "get_openai_client",
]


def _run_two_phase_generation(
    image_path: Path,
    *,
    provider: VisionProvider,
    model: str | None,
    mode: str,
    metadata: dict | None,
    dop_info: dict | None,
    max_retries: int,
    backoff_factor: float,
) -> str:
    ctx = CritiquePromptContext.from_metadata(metadata, dop_info)
    prompt_phase1 = build_phase1_prompt(ctx)

    phase1_output = ""
    for attempt in range(1, max_retries + 1):
        try:
            content = complete_with_image(
                provider,
                image_path,
                prompt_phase1,
                model=model,
                max_tokens=800,
            )
            parsed_check = parse_critique_text(content)
            if parsed_check["has_valid_phase1"] and "申し訳ありません" not in content:
                phase1_output = content
                break

            if attempt < max_retries:
                time.sleep(backoff_factor ** attempt)
            else:
                raise ValueError("Phase 1 API出力に必須構造が含まれませんでした。")
        except Exception as e:
            if attempt == max_retries:
                raise e
            time.sleep(backoff_factor ** attempt)

    if mode != "full":
        return phase1_output

    prompt_phase2 = build_phase2_prompt(ctx, phase1_output)
    phase2_output = ""
    for attempt in range(1, max_retries + 1):
        try:
            content = complete_with_image(
                provider,
                image_path,
                prompt_phase2,
                model=model,
                max_tokens=2500,
            )
            if "【1." in content or "【1" in content:
                phase2_output = content
                break

            if attempt < max_retries:
                time.sleep(backoff_factor ** attempt)
            else:
                raise ValueError("Phase 2 API出力に本文構造が含まれませんでした。")
        except Exception as e:
            if attempt == max_retries:
                raise e
            time.sleep(backoff_factor ** attempt)

    return f"{phase1_output}\n\n---\n\n{phase2_output}"


def generate_critique(
    image_path: Path,
    metadata: dict = None,
    dop_info: dict = None,
    model: str = DEFAULT_OPENAI_MODEL,
    mode: str = "compact",
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    provider: VisionProvider = "openai",
) -> str:
    """
    写真の AI 講評文を生成する共通エントリポイント。
    デスクトップ既定: provider=\"openai\"
    LINE Bot 既定: generate_critique_gemini() または provider=\"gemini\"
    """
    return _run_two_phase_generation(
        image_path,
        provider=provider,
        model=model,
        mode=mode,
        metadata=metadata,
        dop_info=dop_info,
        max_retries=max_retries,
        backoff_factor=backoff_factor,
    )


def generate_critique_openai(
    image_path: Path,
    metadata: dict = None,
    dop_info: dict = None,
    model: str = DEFAULT_OPENAI_MODEL,
    mode: str = "compact",
    max_retries: int = 3,
    backoff_factor: float = 2.0,
) -> str:
    """デスクトップ版: OpenAI Vision（安定性・一括バッチ向け）。"""
    return generate_critique(
        image_path,
        metadata=metadata,
        dop_info=dop_info,
        model=model,
        mode=mode,
        max_retries=max_retries,
        backoff_factor=backoff_factor,
        provider="openai",
    )


def generate_critique_gemini(
    image_path: Path,
    metadata: dict = None,
    dop_info: dict = None,
    model: str | None = None,
    mode: str = "compact",
    max_retries: int = 3,
    backoff_factor: float = 2.0,
) -> str:
    """Google Gemini（低レイテンシ・Free Tier 向け。full は OpenAI 推奨）。"""
    return generate_critique(
        image_path,
        metadata=metadata,
        dop_info=dop_info,
        model=model or DEFAULT_GEMINI_MODEL,
        mode=mode,
        max_retries=max_retries,
        backoff_factor=backoff_factor,
        provider="gemini",
    )


def generate_critique_for_line(
    image_path: Path,
    metadata: dict = None,
    dop_info: dict = None,
    mode: str = "compact",
    max_retries: int = 3,
    backoff_factor: float = 2.0,
) -> str:
    """
    LINE Bot 用エントリ（プロバイダ方針はここで一元管理）。
    - 簡易版 (compact): Gemini / Phase 1 のみ
    - 詳細版 (full): OpenAI / Phase 1 + 2（Gemini full は不安定のため使用しない）
    """
    if mode == "full":
        return generate_critique_openai(
            image_path,
            metadata=metadata,
            dop_info=dop_info,
            mode="full",
            max_retries=max_retries,
            backoff_factor=backoff_factor,
        )
    return generate_critique_gemini(
        image_path,
        metadata=metadata,
        dop_info=dop_info,
        mode="compact",
        max_retries=max_retries,
        backoff_factor=backoff_factor,
    )
