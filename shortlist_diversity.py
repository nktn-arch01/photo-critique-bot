"""M3 多様性: 余白(3)／上位(4)の相対選抜＋偏り抑制.

仕様（R1′ §6）:
- 入力は原則 Rating≥2（M2 合格）
- 残すコマに Rating=3（余白）または 4（上位）と説明 ``[M3]``
- 最終 roughly 10% ガイド（M2 入力の約 40% を残す想定）
- 執着の癖（attachment / sense 寄り）を優先しうる
- タグ語彙は設定化。フル Phase2 は走らせない
- 画素非破壊。1枚失敗で全体停止しない

選抜:
1. 画素フィンガープリント（色相・輝度）＋軽量 Vision（quality / tags / attachment）
2. 品質と多様性の貪欲法で keep_ratio 分を残す
3. 残したうち上位 top_ratio を 4、残りを 3

オフラインでは ``feature_fn`` 差し替えで Vision 不要テストが可能。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable, Sequence

from PIL import Image, ImageStat

from ai_vision import VisionProvider, complete_with_image
from critique_lens import DEFAULT_LENS, get_lens, normalize_lens
from iptc_rating_io import (
    ExifToolError,
    ExifToolNotFoundError,
    read_shortlist_meta,
    write_shortlist_decision,
)
from library_unit import LibraryUnit, list_source_jpegs

STAGE = "M3"

# 第一波の既定語彙（設定で差し替え可能）
DEFAULT_TAG_VOCAB: tuple[str, ...] = (
    "人物",
    "風景",
    "都市",
    "自然",
    "海",
    "空",
    "光",
    "影",
    "静物",
    "建物",
    "夜",
    "抽象",
    "動物",
    "細部",
    "旅",
)

FeatureFn = Callable[[Path], "DiversityFeature"]


@dataclass(frozen=True)
class DiversityConfig:
    """M3 多様性・上位分割パラメータ。"""

    # M2 候補のうち残す比率（50→≈20 ≒ 0.40）。週200の最終≈10%ガイドと整合
    keep_ratio: float = 0.40
    min_keep: int = 0
    max_keep: int | None = None
    # 残したうち Rating=4 にする比率（残りは 3）
    top_ratio: float = 0.40
    min_input_rating: int = 2
    # 貪欲スコア: quality_weight * quality_norm + diversity_weight * min_dist
    quality_weight: float = 0.45
    diversity_weight: float = 0.55
    # 執着ブースト（attachment 1–5 を quality に加点）
    attachment_boost: float = 0.30
    tag_vocab: tuple[str, ...] = DEFAULT_TAG_VOCAB
    max_tags: int = 3
    # Vision
    provider: VisionProvider = "openai"
    model: str | None = None
    max_tokens: int = 220
    temperature: float = 0.2
    max_side: int = 1024
    image_detail: str = "low"
    lens: str = DEFAULT_LENS
    reason_max_chars: int = 48
    analysis_max_side: int = 128


@dataclass(frozen=True)
class DiversityFeature:
    """1枚の多様性・品質特徴。"""

    hue_bin: int  # 0–11
    luma_bin: int  # 0–4
    tags: tuple[str, ...]
    quality: float  # 1–5
    attachment: float  # 1–5（執着／sense 寄り）
    reason: str
    raw_response: str = ""

    def adjusted_quality(self, config: DiversityConfig | None = None) -> float:
        cfg = config or DiversityConfig()
        q = max(1.0, min(5.0, float(self.quality)))
        a = max(1.0, min(5.0, float(self.attachment)))
        return q + cfg.attachment_boost * ((a - 1.0) / 4.0)


@dataclass(frozen=True)
class DiversityDecision:
    path: Path
    input_rating: int | None
    feature: DiversityFeature | None
    keep_rank: int | None
    passed: bool
    rating: int  # 4 / 3 / 入力維持(通常2)
    slot: str  # "top" | "margin" | "reject" | "skipped" | "error"
    reason_brief: str
    skipped: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "stage": STAGE,
            "input_rating": self.input_rating,
            "feature": {
                "hue_bin": self.feature.hue_bin,
                "luma_bin": self.feature.luma_bin,
                "tags": list(self.feature.tags),
                "quality": self.feature.quality,
                "attachment": self.feature.attachment,
                "reason": self.feature.reason,
            }
            if self.feature
            else None,
            "keep_rank": self.keep_rank,
            "passed": self.passed,
            "rating": self.rating,
            "slot": self.slot,
            "reason_brief": self.reason_brief,
            "skipped": self.skipped,
            "error": self.error,
        }


@dataclass
class DiversityBatchResult:
    decisions: list[DiversityDecision] = field(default_factory=list)
    written: int = 0
    skipped: int = 0
    errors: int = 0
    pass_count: int = 0
    top_count: int = 0
    margin_count: int = 0
    cancelled: bool = False

    def to_dict(self) -> dict:
        return {
            "stage": STAGE,
            "total": len(self.decisions),
            "pass_count": self.pass_count,
            "top_count": self.top_count,
            "margin_count": self.margin_count,
            "written": self.written,
            "skipped": self.skipped,
            "errors": self.errors,
            "keep_ratio_guide": 0.40,
            "final_share_guide": 0.10,
            "decisions": [d.to_dict() for d in self.decisions],
        }


def default_config() -> DiversityConfig:
    return DiversityConfig()


def select_keep_count(n_candidates: int, config: DiversityConfig | None = None) -> int:
    cfg = config or default_config()
    if n_candidates <= 0:
        return 0
    raw = int(round(n_candidates * cfg.keep_ratio))
    n = max(cfg.min_keep, raw)
    if cfg.keep_ratio > 0 and n_candidates >= 1 and n < 1 and cfg.min_keep == 0:
        n = 1
    if cfg.max_keep is not None:
        n = min(n, cfg.max_keep)
    return min(n, n_candidates)


def select_top_count(n_kept: int, config: DiversityConfig | None = None) -> int:
    cfg = config or default_config()
    if n_kept <= 0:
        return 0
    n = int(round(n_kept * cfg.top_ratio))
    if cfg.top_ratio > 0 and n_kept >= 1 and n < 1:
        n = 1
    return min(max(0, n), n_kept)


def _clamp_1_5(value) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        n = 3.0
    return max(1.0, min(5.0, n))


def _truncate_reason(reason: str, max_chars: int) -> str:
    text = " ".join(str(reason).split())
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)].rstrip() + "…"


def compute_pixel_bins(path: Path | str, config: DiversityConfig | None = None) -> tuple[int, int]:
    """色相ビン(0–11)と輝度ビン(0–4)。読み取りのみ。"""
    cfg = config or default_config()
    with Image.open(path) as im:
        im.load()
        rgb = im.convert("RGB")
        w, h = rgb.size
        long_side = max(w, h)
        if long_side > cfg.analysis_max_side:
            scale = cfg.analysis_max_side / float(long_side)
            rgb = rgb.resize(
                (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                Image.Resampling.BILINEAR,
            )
        hsv = rgb.convert("HSV")
        h_stat = ImageStat.Stat(hsv)
        # HSV の H は Pillow で 0–255
        hue = float(h_stat.mean[0]) / 255.0
        hue_bin = int(hue * 12) % 12
        gray = rgb.convert("L")
        luma = float(ImageStat.Stat(gray).mean[0])
        luma_bin = min(4, int(luma / 51.0))
    return hue_bin, luma_bin


def diversity_distance(a: DiversityFeature, b: DiversityFeature) -> float:
    """0–1 程度の距離。大きいほど多様。"""
    dh = abs(a.hue_bin - b.hue_bin)
    hue_d = min(dh, 12 - dh) / 6.0
    luma_d = abs(a.luma_bin - b.luma_bin) / 4.0
    ta, tb = set(a.tags), set(b.tags)
    if not ta and not tb:
        tag_d = 0.5
    else:
        union = ta | tb
        inter = ta & tb
        tag_d = 1.0 - (len(inter) / len(union)) if union else 0.5
    return 0.35 * hue_d + 0.25 * luma_d + 0.40 * tag_d


def parse_diversity_response(
    text: str,
    *,
    hue_bin: int,
    luma_bin: int,
    config: DiversityConfig | None = None,
) -> DiversityFeature:
    cfg = config or default_config()
    if not text or not str(text).strip():
        raise ValueError("empty diversity response")
    raw = str(text).strip()
    payload = None
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
    if not isinstance(payload, dict):
        raise ValueError("diversity response is not JSON object")

    quality = _clamp_1_5(payload.get("quality", 3))
    attachment = _clamp_1_5(payload.get("attachment", payload.get("sense", 3)))
    reason = str(payload.get("reason") or payload.get("reason_brief") or "").strip()
    vocab = set(cfg.tag_vocab)
    tags_raw = payload.get("tags") or []
    if isinstance(tags_raw, str):
        tags_raw = re.split(r"[,、/\s]+", tags_raw)
    tags: list[str] = []
    for t in tags_raw:
        s = str(t).strip()
        if s in vocab and s not in tags:
            tags.append(s)
        if len(tags) >= cfg.max_tags:
            break
    if not reason:
        reason = "多様性候補"
    return DiversityFeature(
        hue_bin=hue_bin,
        luma_bin=luma_bin,
        tags=tuple(tags),
        quality=quality,
        attachment=attachment,
        reason=reason,
        raw_response=raw,
    )


def build_diversity_prompt(*, lens: str | None = None, config: DiversityConfig | None = None) -> str:
    cfg = config or default_config()
    lens_obj = get_lens(normalize_lens(lens or cfg.lens))
    vocab = "、".join(cfg.tag_vocab)
    return f"""この写真を短絡用に短く見てください。フル講評は不要です。

観点:
- quality: Lumina Notes としての残す熱量（1–5）。★5必須禁止。迷ったら低め。
- attachment: 撮影者の執着・偏り・反復しそうなこだわりの兆し（1–5）。{lens_obj.score_axes[-1].label} に近い。
- tags: 次の語彙からのみ最大{cfg.max_tags}個（無いなら空配列）: {vocab}

出力は JSON のみ:
{{"quality":3,"attachment":3,"tags":["風景"],"reason":"40文字以内の日本語"}}
"""


def build_diversity_system_prompt(*, lens: str | None = None) -> str:
    lens_obj = get_lens(normalize_lens(lens))
    return (
        f"{lens_obj.system_role} "
        "今は多様性短絡用の短いラベル付けのみ。評価ではなく残す余白と上位の材料を返す。"
    )


def extract_diversity_feature(
    path: Path | str,
    config: DiversityConfig | None = None,
) -> DiversityFeature:
    """画素ビン＋軽量 Vision で特徴を取得。"""
    cfg = config or default_config()
    jpeg = Path(path)
    hue_bin, luma_bin = compute_pixel_bins(jpeg, cfg)
    text = complete_with_image(
        cfg.provider,
        jpeg,
        build_diversity_prompt(lens=cfg.lens, config=cfg),
        model=cfg.model,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        system_prompt=build_diversity_system_prompt(lens=cfg.lens),
        max_side=cfg.max_side,
        image_detail=cfg.image_detail,
    )
    return parse_diversity_response(text, hue_bin=hue_bin, luma_bin=luma_bin, config=cfg)


def greedy_diversity_select(
    items: Sequence[tuple[Path, int | None, DiversityFeature]],
    config: DiversityConfig | None = None,
) -> list[DiversityDecision]:
    """品質×多様性の貪欲法で残し、上位/余白に分割する。"""
    cfg = config or default_config()
    if not items:
        return []

    n_keep = select_keep_count(len(items), cfg)
    # 品質の高い順を初期候補順に
    indexed = list(enumerate(items))
    indexed.sort(
        key=lambda it: (
            -it[1][2].adjusted_quality(cfg),
            -it[1][2].quality,
            -it[1][2].attachment,
            str(it[1][0]),
        )
    )

    selected_idx: list[int] = []
    remaining = [i for i, _ in indexed]

    while remaining and len(selected_idx) < n_keep:
        if not selected_idx:
            # 最初は執着込み品質の最大
            pick = remaining[0]
            selected_idx.append(pick)
            remaining.remove(pick)
            continue

        best_i = None
        best_score = -1.0
        selected_feats = [items[i][2] for i in selected_idx]
        # 品質正規化用
        quals = [items[i][2].adjusted_quality(cfg) for i in remaining]
        q_min, q_max = min(quals), max(quals)
        q_span = max(1e-6, q_max - q_min)

        for i in remaining:
            feat = items[i][2]
            q_norm = (feat.adjusted_quality(cfg) - q_min) / q_span
            min_dist = min(diversity_distance(feat, s) for s in selected_feats)
            score = cfg.quality_weight * q_norm + cfg.diversity_weight * min_dist
            if score > best_score:
                best_score = score
                best_i = i
        assert best_i is not None
        selected_idx.append(best_i)
        remaining.remove(best_i)

    # 残したものを品質順で top / margin
    kept_sorted = sorted(
        selected_idx,
        key=lambda i: (
            -items[i][2].adjusted_quality(cfg),
            -items[i][2].quality,
            str(items[i][0]),
        ),
    )
    n_top = select_top_count(len(kept_sorted), cfg)
    top_set = set(kept_sorted[:n_top])
    keep_rank_map = {idx: rank for rank, idx in enumerate(kept_sorted, start=1)}

    out: list[DiversityDecision] = []
    for i, (path, input_rating, feat) in enumerate(items):
        keep_rating = input_rating if input_rating is not None else cfg.min_input_rating
        reason = _truncate_reason(feat.reason, cfg.reason_max_chars)
        if i in top_set:
            slot = "top"
            rating = 4
            passed = True
            # 理由に上位であることを短く添える（既存 reason 優先）
            brief = reason if reason else "上位"
        elif i in keep_rank_map:
            slot = "margin"
            rating = 3
            passed = True
            brief = reason if reason else "余白"
        else:
            slot = "reject"
            rating = keep_rating
            passed = False
            brief = reason
        out.append(
            DiversityDecision(
                path=path,
                input_rating=input_rating,
                feature=feat,
                keep_rank=keep_rank_map.get(i),
                passed=passed,
                rating=rating,
                slot=slot,
                reason_brief=brief,
                skipped=False,
                error=None,
            )
        )
    # 監査しやすいよう keep_rank のあるものを前に並べ替えない（入力順維持）
    return out


def apply_diversity_decision(
    decision: DiversityDecision,
    *,
    write: bool = True,
) -> DiversityDecision:
    if not write or decision.skipped or decision.error or not decision.passed:
        return decision
    try:
        write_shortlist_decision(
            decision.path,
            rating=decision.rating,
            stage="M3",
            reason=decision.reason_brief,
        )
        return decision
    except (ExifToolNotFoundError, ExifToolError, OSError, ValueError) as exc:
        return replace(decision, error=f"write_failed: {exc}")


def _read_input_rating(path: Path) -> int | None:
    try:
        return read_shortlist_meta(path).rating
    except Exception:
        return None


def run_diversity_on_paths(
    paths: Sequence[Path | str] | Iterable[Path | str],
    config: DiversityConfig | None = None,
    *,
    write: bool = True,
    feature_fn: FeatureFn | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> DiversityBatchResult:
    """M3 バッチ。feature_fn があれば Vision の代わりに使う。"""
    cfg = config or default_config()
    result = DiversityBatchResult()
    scored: list[tuple[Path, int | None, DiversityFeature]] = []

    for raw in paths:
        if should_cancel and should_cancel():
            result.cancelled = True
            break
        path = Path(raw)
        try:
            input_rating = _read_input_rating(path)
            if input_rating is None or input_rating < cfg.min_input_rating:
                result.decisions.append(
                    DiversityDecision(
                        path=path.resolve() if path.exists() else path,
                        input_rating=input_rating,
                        feature=None,
                        keep_rank=None,
                        passed=False,
                        rating=input_rating if input_rating is not None else 0,
                        slot="skipped",
                        reason_brief="",
                        skipped=True,
                        error=None,
                    )
                )
                result.skipped += 1
                continue

            feat = feature_fn(path) if feature_fn else extract_diversity_feature(path, cfg)
            scored.append((path.resolve() if path.exists() else path, input_rating, feat))
        except Exception as exc:
            result.decisions.append(
                DiversityDecision(
                    path=path,
                    input_rating=None,
                    feature=None,
                    keep_rank=None,
                    passed=False,
                    rating=cfg.min_input_rating,
                    slot="error",
                    reason_brief="",
                    skipped=False,
                    error=str(exc),
                )
            )
            result.errors += 1

    if result.cancelled:
        return result

    selected = greedy_diversity_select(scored, cfg)
    # skipped/error を先に入れているので、選抜結果を後ろに追加
    for decision in selected:
        if should_cancel and should_cancel():
            result.cancelled = True
            break
        final = apply_diversity_decision(decision, write=write)
        result.decisions.append(final)
        if final.error:
            result.errors += 1
        elif final.passed and write:
            result.written += 1
        if final.passed and not final.error:
            result.pass_count += 1
            if final.slot == "top":
                result.top_count += 1
            elif final.slot == "margin":
                result.margin_count += 1

    return result


def run_diversity_on_unit(
    unit: LibraryUnit,
    config: DiversityConfig | None = None,
    *,
    write: bool = True,
    feature_fn: FeatureFn | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> DiversityBatchResult:
    return run_diversity_on_paths(
        list_source_jpegs(unit),
        config=config,
        write=write,
        feature_fn=feature_fn,
        should_cancel=should_cancel,
    )
