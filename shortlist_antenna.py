"""M2 アンテナ: 5軸の相対熱量で短絡（軽量 Vision）。

仕様（R1′ §6.3）:
- 入力は原則 Rating≥1（M1 合格）
- 合格は Rating=2 ＋説明 ``[M2]``
- ★絶対ゲート禁止（★5必須にしない）。バッチ内の相対順位で選ぶ
- フル Phase2 講評は走らせない
- 画素非破壊。1枚失敗で全体停止しない
- 合格数目安は入力の約 25–28%（ガイド。設定化）

Vision 応答は短い JSON のみ。オフラインでは ``score_fn`` 差し替えでテスト可能。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable, Sequence

from ai_vision import VisionProvider, complete_with_image
from critique_lens import DEFAULT_LENS, get_lens, normalize_lens
from iptc_rating_io import (
    ExifToolError,
    ExifToolNotFoundError,
    read_shortlist_meta,
    write_shortlist_decision,
)
from library_unit import LibraryUnit, list_source_jpegs

STAGE = "M2"
AXIS_KEYS: tuple[str, ...] = (
    "framing",
    "sensitivity",
    "story",
    "technical",
    "sense",
)

ScoreFn = Callable[[Path], "AntennaScore"]


@dataclass(frozen=True)
class AntennaConfig:
    """M2 相対選抜・Vision パラメータ。"""

    # 候補のうち合格させる比率（ガイド: 180→≈50 ≒ 0.28）
    pass_ratio: float = 0.28
    min_pass: int = 0
    max_pass: int | None = None
    min_input_rating: int = 1
    # 熱量: heat = peak*w_peak + mean*w_mean + resonance*w_res
    peak_weight: float = 1.0
    mean_weight: float = 0.55
    resonance_weight: float = 0.35
    resonance_floor: int = 3
    # Vision
    provider: VisionProvider = "openai"
    model: str | None = None
    max_tokens: int = 220
    temperature: float = 0.25
    max_side: int = 1024
    image_detail: str = "low"
    lens: str = DEFAULT_LENS
    reason_max_chars: int = 48


@dataclass(frozen=True)
class AntennaScore:
    scores: dict[str, int]
    reason: str
    raw_response: str = ""

    def peak_axis(self) -> tuple[str, int]:
        best_key = max(AXIS_KEYS, key=lambda k: (self.scores.get(k, 0), k))
        return best_key, int(self.scores.get(best_key, 0))

    def mean(self) -> float:
        vals = [int(self.scores.get(k, 0)) for k in AXIS_KEYS]
        return sum(vals) / max(1, len(vals))

    def resonance_count(self, floor: int) -> int:
        return sum(1 for k in AXIS_KEYS if int(self.scores.get(k, 0)) >= floor)

    def heat(self, config: AntennaConfig | None = None) -> float:
        cfg = config or AntennaConfig()
        peak = self.peak_axis()[1]
        return (
            cfg.peak_weight * peak
            + cfg.mean_weight * self.mean()
            + cfg.resonance_weight * self.resonance_count(cfg.resonance_floor)
        )


@dataclass(frozen=True)
class AntennaDecision:
    path: Path
    input_rating: int | None
    score: AntennaScore | None
    heat: float
    rank: int | None
    passed: bool
    rating: int  # 書き込み予定: 合格2 / 非合格は入力維持（通常1）
    reason_brief: str
    skipped: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "stage": STAGE,
            "input_rating": self.input_rating,
            "scores": self.score.scores if self.score else None,
            "peak_axis": self.score.peak_axis() if self.score else None,
            "heat": self.heat,
            "rank": self.rank,
            "passed": self.passed,
            "rating": self.rating,
            "reason_brief": self.reason_brief,
            "skipped": self.skipped,
            "error": self.error,
        }


@dataclass
class AntennaBatchResult:
    decisions: list[AntennaDecision] = field(default_factory=list)
    written: int = 0
    skipped: int = 0
    errors: int = 0
    pass_count: int = 0
    cancelled: bool = False

    def to_dict(self) -> dict:
        return {
            "stage": STAGE,
            "total": len(self.decisions),
            "pass_count": self.pass_count,
            "written": self.written,
            "skipped": self.skipped,
            "errors": self.errors,
            "pass_ratio_guide": 0.28,
            "decisions": [d.to_dict() for d in self.decisions],
        }


def default_config() -> AntennaConfig:
    return AntennaConfig()


def compute_heat(scores: AntennaScore, config: AntennaConfig | None = None) -> float:
    return scores.heat(config)


def select_pass_count(n_candidates: int, config: AntennaConfig | None = None) -> int:
    """相対合格数。★絶対ゲートは使わない。"""
    cfg = config or default_config()
    if n_candidates <= 0:
        return 0
    raw = int(round(n_candidates * cfg.pass_ratio))
    n = max(cfg.min_pass, raw)
    # 候補が少ないとき 0 になりすぎないよう、比率>0 なら少なくとも1（候補≥1）
    if cfg.pass_ratio > 0 and n_candidates >= 1 and n < 1 and cfg.min_pass == 0:
        n = 1
    if cfg.max_pass is not None:
        n = min(n, cfg.max_pass)
    return min(n, n_candidates)


def _clamp_score(value) -> int:
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        n = 1
    return max(1, min(5, n))


def parse_antenna_response(text: str) -> AntennaScore:
    """Vision 応答から5軸＋reason を取り出す。JSON 優先、行形式フォールバック。"""
    if not text or not str(text).strip():
        raise ValueError("empty antenna response")
    raw = str(text).strip()

    payload = None
    # ```json ... ``` を許容
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        try:
            payload = json.loads(fence.group(1))
        except json.JSONDecodeError:
            payload = None
    if payload is None:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                payload = None

    scores: dict[str, int] = {}
    reason = ""
    if isinstance(payload, dict):
        for key in AXIS_KEYS:
            if key in payload:
                scores[key] = _clamp_score(payload[key])
        reason = str(payload.get("reason") or payload.get("reason_brief") or "").strip()

    if len(scores) < len(AXIS_KEYS):
        # framing=4 形式
        for key in AXIS_KEYS:
            if key in scores:
                continue
            m = re.search(rf"\b{key}\b\s*[=:：]\s*([1-5])", raw, re.IGNORECASE)
            if m:
                scores[key] = int(m.group(1))
        if not reason:
            m = re.search(r"(?:REASON|reason|理由)\s*[=:：]\s*(.+)", raw)
            if m:
                reason = m.group(1).strip().strip('"')

    missing = [k for k in AXIS_KEYS if k not in scores]
    if missing:
        raise ValueError(f"antenna scores missing: {missing}")

    if not reason:
        peak_key, peak_val = max(scores.items(), key=lambda kv: kv[1])
        reason = f"{peak_key}に熱量({peak_val})"

    return AntennaScore(scores={k: scores[k] for k in AXIS_KEYS}, reason=reason, raw_response=raw)


def build_antenna_prompt(*, lens: str | None = None) -> str:
    lens_obj = get_lens(normalize_lens(lens))
    axis_lines = []
    for axis in lens_obj.score_axes:
        axis_lines.append(f"- {axis.key}（表示名: {axis.label}）: {axis.meaning}")
    axes_block = "\n".join(axis_lines)
    keys = ", ".join(AXIS_KEYS)
    return f"""この写真を、Lumina Notes の5軸だけで短く採点してください。
フル講評・長文・見出し・カード項目は不要です。

## 5軸（深層基準）
{axes_block}

## 厳守
- ★5必須などの絶対ゲートは禁止。観察に応じて1–5の整数を付ける。迷ったら低め。
- 5軸をできるだけ独立に採点する（同じ理由で複数を5にしない）。
- 写真にない人物・出来事を story で創作しない。
- 出力は JSON オブジェクトのみ（前後の説明文禁止）。

## 出力形式
{{"{AXIS_KEYS[0]}":1,"{AXIS_KEYS[1]}":1,"{AXIS_KEYS[2]}":1,"{AXIS_KEYS[3]}":1,"{AXIS_KEYS[4]}":1,"reason":"40文字以内の日本語で熱量の要点"}}

キーは必ず次のみ: {keys}, reason
"""


def build_antenna_system_prompt(*, lens: str | None = None) -> str:
    lens_obj = get_lens(normalize_lens(lens))
    return (
        f"{lens_obj.system_role} "
        "今は短絡用のアンテナ採点のみ。評価ではなく熱量の相対比較のための短いスコアを返す。"
    )


def score_image_with_vision(
    path: Path | str,
    config: AntennaConfig | None = None,
) -> AntennaScore:
    cfg = config or default_config()
    jpeg = Path(path)
    text = complete_with_image(
        cfg.provider,
        jpeg,
        build_antenna_prompt(lens=cfg.lens),
        model=cfg.model,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        system_prompt=build_antenna_system_prompt(lens=cfg.lens),
        max_side=cfg.max_side,
        image_detail=cfg.image_detail,
    )
    return parse_antenna_response(text)


def _truncate_reason(reason: str, max_chars: int) -> str:
    text = " ".join(str(reason).split())
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)].rstrip() + "…"


def _read_input_rating(path: Path) -> int | None:
    try:
        return read_shortlist_meta(path).rating
    except Exception:
        return None


def rank_and_select(
    scored: Sequence[tuple[Path, int | None, AntennaScore]],
    config: AntennaConfig | None = None,
) -> list[AntennaDecision]:
    """熱量で降順ソートし、相対上位を合格にする。"""
    cfg = config or default_config()
    decorated: list[tuple[float, int, Path, int | None, AntennaScore]] = []
    for path, input_rating, score in scored:
        heat = compute_heat(score, cfg)
        peak = score.peak_axis()[1]
        # 安定ソート用: heat desc, peak desc, mean desc
        decorated.append((heat, peak, path, input_rating, score))

    decorated.sort(key=lambda t: (-t[0], -t[1], -t[4].mean(), str(t[2])))
    n_pass = select_pass_count(len(decorated), cfg)

    out: list[AntennaDecision] = []
    for idx, (heat, _peak, path, input_rating, score) in enumerate(decorated, start=1):
        passed = idx <= n_pass
        keep_rating = input_rating if input_rating is not None else cfg.min_input_rating
        reason = _truncate_reason(score.reason, cfg.reason_max_chars)
        out.append(
            AntennaDecision(
                path=path,
                input_rating=input_rating,
                score=score,
                heat=heat,
                rank=idx,
                passed=passed,
                rating=2 if passed else keep_rating,
                reason_brief=reason,
                skipped=False,
                error=None,
            )
        )
    return out


def apply_antenna_decision(
    decision: AntennaDecision,
    *,
    write: bool = True,
) -> AntennaDecision:
    if not write or decision.skipped or decision.error or not decision.passed:
        return decision
    try:
        write_shortlist_decision(
            decision.path,
            rating=2,
            stage="M2",
            reason=decision.reason_brief,
        )
        return decision
    except (ExifToolNotFoundError, ExifToolError, OSError, ValueError) as exc:
        return replace(decision, error=f"write_failed: {exc}")


def run_antenna_on_paths(
    paths: Sequence[Path | str] | Iterable[Path | str],
    config: AntennaConfig | None = None,
    *,
    write: bool = True,
    score_fn: ScoreFn | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> AntennaBatchResult:
    """M2 バッチ。score_fn があれば Vision の代わりに使う（テスト用）。"""
    cfg = config or default_config()
    result = AntennaBatchResult()
    scored: list[tuple[Path, int | None, AntennaScore]] = []

    for raw in paths:
        if should_cancel and should_cancel():
            result.cancelled = True
            break
        path = Path(raw)
        try:
            input_rating = _read_input_rating(path)
            if input_rating is None or input_rating < cfg.min_input_rating:
                result.decisions.append(
                    AntennaDecision(
                        path=path.resolve() if path.exists() else path,
                        input_rating=input_rating,
                        score=None,
                        heat=0.0,
                        rank=None,
                        passed=False,
                        rating=input_rating if input_rating is not None else 0,
                        reason_brief="",
                        skipped=True,
                        error=None,
                    )
                )
                result.skipped += 1
                continue

            score = score_fn(path) if score_fn else score_image_with_vision(path, cfg)
            scored.append((path.resolve() if path.exists() else path, input_rating, score))
        except Exception as exc:
            result.decisions.append(
                AntennaDecision(
                    path=path,
                    input_rating=None,
                    score=None,
                    heat=0.0,
                    rank=None,
                    passed=False,
                    rating=cfg.min_input_rating,
                    reason_brief="",
                    skipped=False,
                    error=str(exc),
                )
            )
            result.errors += 1

    if result.cancelled:
        return result

    selected = rank_and_select(scored, cfg)
    for decision in selected:
        if should_cancel and should_cancel():
            result.cancelled = True
            break
        final = apply_antenna_decision(decision, write=write)
        result.decisions.append(final)
        if final.error:
            result.errors += 1
        elif final.passed and write:
            result.written += 1
        if final.passed and not final.error:
            result.pass_count += 1

    return result


def run_antenna_on_unit(
    unit: LibraryUnit,
    config: AntennaConfig | None = None,
    *,
    write: bool = True,
    score_fn: ScoreFn | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> AntennaBatchResult:
    return run_antenna_on_paths(
        list_source_jpegs(unit),
        config=config,
        write=write,
        score_fn=score_fn,
        should_cancel=should_cancel,
    )
