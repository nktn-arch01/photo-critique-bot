"""2段階講評生成のオーケストレーション（プロバイダは ai_vision 経由で差し替え）。"""

import os
import time
from collections.abc import Callable
from pathlib import Path

from ai_vision import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OPENAI_MODEL,
    VisionProvider,
    complete_with_image,
    get_openai_client,
    is_quota_or_rate_limit_error,
)
from critique_lens import DEFAULT_LENS, normalize_lens
from critique_parser import parse_critique_text, is_valid_phase2_content
from critique_prompts import (
    CritiquePromptContext,
    build_phase1_prompt,
    build_phase2_prompt,
    get_system_role,
)

# デスクトップ等からの後方互換
__all__ = [
    "CritiqueContractError",
    "generate_critique",
    "generate_critique_openai",
    "generate_critique_gemini",
    "generate_critique_for_line",
    "generate_critique_with_prompts",
    "get_openai_client",
]


class CritiqueContractError(ValueError):
    """モデル出力がカード構造または光の方位の契約を満たさない。通信障害ではない。"""


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
    lens: str,
    phase1_override: str | None = None,
    build_phase1_prompt_fn: Callable[[], str] | None = None,
    build_phase2_prompt_fn: Callable[[str], str] | None = None,
    system_role_override: str | None = None,
    phase1_temperature: float | None = None,
    phase_accept: Callable[[str], bool] | None = None,
    phase_retry_note: str | None = None,
    phase1_retry_note: str | None = None,
    phase2_retry_note: str | None = None,
) -> str:
    lens_id = normalize_lens(lens)
    if build_phase1_prompt_fn:
        prompt_phase1 = build_phase1_prompt_fn()
        system_role = system_role_override or get_system_role(lens_id)
        ctx = None
    else:
        ctx = CritiquePromptContext.from_metadata(metadata, dop_info)
        system_role = get_system_role(lens_id)
        prompt_phase1 = build_phase1_prompt(ctx, lens=lens_id)

    # Phase1 はカードの軸になるため温度を下げ、compact/full 間の揺れを抑える
    phase1_temperature = 0.35 if phase1_temperature is None else phase1_temperature
    phase2_temperature = 0.7

    def _retry_note_for(phase: int) -> str | None:
        if phase == 1:
            return phase1_retry_note if phase1_retry_note is not None else phase_retry_note
        return phase2_retry_note if phase2_retry_note is not None else phase_retry_note

    def _prompt_for_attempt(base: str, attempt: int, phase: int) -> str:
        note = _retry_note_for(phase)
        if attempt == 1 or not note:
            return base
        return f"{base}\n\n{note}"

    def _accepts(content: str) -> bool:
        if phase_accept is None:
            return True
        return bool(phase_accept(content))

    phase1_output = ""
    if phase1_override and phase1_override.strip():
        parsed_override = parse_critique_text(phase1_override, lens=lens_id)
        if not parsed_override["has_valid_phase1"]:
            raise ValueError("phase1_override に必須構造（TITLE/SCORES）が含まれません。")
        phase1_output = phase1_override.strip()
    else:
        for attempt in range(1, max_retries + 1):
            try:
                content = complete_with_image(
                    provider,
                    image_path,
                    _prompt_for_attempt(prompt_phase1, attempt, 1),
                    model=model,
                    max_tokens=800,
                    temperature=phase1_temperature,
                    system_prompt=system_role,
                )
                parsed_check = parse_critique_text(content, lens=lens_id)
                structure_ok = (
                    parsed_check["has_valid_phase1"] and "申し訳ありません" not in content
                )
                accept_ok = _accepts(content)
                if structure_ok and accept_ok:
                    phase1_output = content
                    break

                print(
                    f"[Phase1 retry {attempt}/{max_retries}] provider={provider} "
                    f"valid={parsed_check['has_valid_phase1']} accept={accept_ok} "
                    f"preview={content[:200]!r}",
                    flush=True,
                )

                if attempt < max_retries:
                    # モデル文面の差し戻し。通信の指数バックオフは掛けない。
                    continue
                if not structure_ok:
                    raise CritiqueContractError(
                        "Phase 1 出力に必須構造（TITLE/SCORES）が含まれませんでした。"
                    )
                raise CritiqueContractError(
                    "Phase 1 出力が光の方位の事実と食い違っています。"
                )
            except CritiqueContractError:
                raise
            except Exception as e:
                if is_quota_or_rate_limit_error(e):
                    raise
                if attempt == max_retries:
                    raise e
                time.sleep(backoff_factor ** attempt)

    if mode != "full":
        return phase1_output

    if build_phase2_prompt_fn:
        prompt_phase2 = build_phase2_prompt_fn(phase1_output)
    else:
        prompt_phase2 = build_phase2_prompt(ctx, phase1_output, lens=lens_id)
    phase2_output = ""
    for attempt in range(1, max_retries + 1):
        try:
            content = complete_with_image(
                provider,
                image_path,
                _prompt_for_attempt(prompt_phase2, attempt, 2),
                model=model,
                max_tokens=2500,
                temperature=phase2_temperature,
                system_prompt=system_role,
            )
            structure_ok = is_valid_phase2_content(content)
            accept_ok = _accepts(content)
            if structure_ok and accept_ok:
                phase2_output = content
                break

            print(
                f"[Phase2 retry {attempt}/{max_retries}] provider={provider} "
                f"valid={structure_ok} accept={accept_ok} preview={content[:200]!r}",
                flush=True,
            )

            if attempt < max_retries:
                continue
            if not structure_ok:
                raise CritiqueContractError("Phase 2 出力に本文構造が含まれませんでした。")
            raise CritiqueContractError("Phase 2 出力が光の方位の事実と食い違っています。")
        except CritiqueContractError:
            raise
        except Exception as e:
            if is_quota_or_rate_limit_error(e):
                raise
            if attempt == max_retries:
                raise e
            time.sleep(backoff_factor ** attempt)

    return f"{phase1_output}\n\n---\n\n{phase2_output}"


def generate_critique_with_prompts(
    image_path: Path,
    *,
    build_phase1: Callable[[], str],
    build_phase2: Callable[[str], str],
    mode: str = "compact",
    model: str = DEFAULT_OPENAI_MODEL,
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    provider: VisionProvider = "openai",
    lens: str = DEFAULT_LENS,
    phase1_override: str | None = None,
    system_role: str | None = None,
    phase1_temperature: float | None = None,
    phase_accept: Callable[[str], bool] | None = None,
    phase_retry_note: str | None = None,
    phase1_retry_note: str | None = None,
    phase2_retry_note: str | None = None,
) -> str:
    """カスタムプロンプトビルダーで講評を生成（Guided Web 等）。"""
    return _run_two_phase_generation(
        image_path,
        provider=provider,
        model=model,
        mode=mode,
        metadata={},
        dop_info={},
        max_retries=max_retries,
        backoff_factor=backoff_factor,
        lens=lens,
        phase1_override=phase1_override,
        build_phase1_prompt_fn=build_phase1,
        build_phase2_prompt_fn=build_phase2,
        system_role_override=system_role,
        phase1_temperature=phase1_temperature,
        phase_accept=phase_accept,
        phase_retry_note=phase_retry_note,
        phase1_retry_note=phase1_retry_note,
        phase2_retry_note=phase2_retry_note,
    )


def generate_critique(
    image_path: Path,
    metadata: dict = None,
    dop_info: dict = None,
    model: str = DEFAULT_OPENAI_MODEL,
    mode: str = "compact",
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    provider: VisionProvider = "openai",
    lens: str = DEFAULT_LENS,
    phase1_override: str | None = None,
) -> str:
    """
    写真の AI 講評文を生成する共通エントリポイント。
    デスクトップ既定: provider=\"openai\"
    lens: 対話の型（v1 は self 固定。mode とは直交）
    phase1_override: JPEG 埋め込み等から渡す Phase1 全文（あれば Phase1 API をスキップ）
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
        lens=lens,
        phase1_override=phase1_override,
    )


def generate_critique_openai(
    image_path: Path,
    metadata: dict = None,
    dop_info: dict = None,
    model: str = DEFAULT_OPENAI_MODEL,
    mode: str = "compact",
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    lens: str = DEFAULT_LENS,
    phase1_override: str | None = None,
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
        lens=lens,
        phase1_override=phase1_override,
    )


def generate_critique_gemini(
    image_path: Path,
    metadata: dict = None,
    dop_info: dict = None,
    model: str | None = None,
    mode: str = "compact",
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    lens: str = DEFAULT_LENS,
    phase1_override: str | None = None,
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
        lens=lens,
        phase1_override=phase1_override,
    )


def generate_critique_for_line(
    image_path: Path,
    metadata: dict = None,
    dop_info: dict = None,
    mode: str = "compact",
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    lens: str = DEFAULT_LENS,
    phase1_override: str | None = None,
) -> str:
    """
    LINE Bot 用エントリ（プロバイダ方針はここで一元管理）。
    - compact: OpenAI / Phase 1 のみ
    - full: OpenAI / Phase 1 + 2（phase1_override があれば Phase2 のみ）
    - lens: v1 は self（将来 audience 等を渡せる）
    将来 Gemini を試す場合のみ環境変数 LINE_COMPACT_PROVIDER=gemini（非推奨）。
    """
    if mode == "full":
        return generate_critique_openai(
            image_path,
            metadata=metadata,
            dop_info=dop_info,
            mode="full",
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            lens=lens,
            phase1_override=phase1_override,
        )

    if os.getenv("LINE_COMPACT_PROVIDER", "openai").strip().lower() == "gemini":
        return generate_critique_gemini(
            image_path,
            metadata=metadata,
            dop_info=dop_info,
            mode="compact",
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            lens=lens,
            phase1_override=phase1_override,
        )

    return generate_critique_openai(
        image_path,
        metadata=metadata,
        dop_info=dop_info,
        mode="compact",
        max_retries=max_retries,
        backoff_factor=backoff_factor,
        lens=lens,
        phase1_override=phase1_override,
    )
