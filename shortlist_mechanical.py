"""M1 機械選別: 明らかな失敗の足切り＋意図保護.

仕様（R1′ §6）:
- 合格 Rating=1、不合格 Rating=0
- 低速 SS・開放寄り・意図的アンダー等は機械不合格から守る
- 閾値は設定化。枚数目安（約80%+）はガイドでありハードゲートではない
- 画素は改変・削除しない（メタデータのみ更新）
- 1枚失敗でバッチ全体を止めない

ブレ指標は Laplacian 分散（Pillow のみ。OpenCV/numpy 非依存）。

使用上の注意（誤判定の想定）:
- 星空・夜景の黒つぶれ、流し撮り／ICM の強いブレは、意図保護 EXIF が
  無い／足りないと Rating 0 になりうる。H3 で拾う前提（詳細は
  docs/R1_DEEP_LOOP_SPEC.md §6.4.1）。
- 白飛び系は意図保護の対象外。
- EXIF 欠落 JPEG では保護が効かない。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageFilter, ImageStat

from iptc_rating_io import ExifToolError, ExifToolNotFoundError, write_rating
from library_unit import LibraryUnit, list_source_jpegs

STAGE = "M1"


@dataclass(frozen=True)
class MechanicalConfig:
    """M1 閾値・解析パラメータ（すべて設定化）。"""

    # 解析サイズ（長辺）。大きいほど精密だが遅い
    analysis_max_side: int = 512
    # Laplacian 分散の下限。これ未満は「明らかなブレ／ピンボケ」候補
    min_sharpness: float = 18.0
    # 意図保護: これ以上遅いシャッター（秒）
    slow_shutter_sec: float = 1.0 / 30.0
    # 意図保護: これ以下の F 値（開放寄り）
    open_aperture_max_f: float = 2.8
    # 意図保護: これ以下の露出補正（EV）＝意図的アンダー
    intentional_under_ev: float = -0.7
    # 黒つぶれ・白飛びの平均輝度（0–255）
    black_mean_luma: float = 16.0
    white_mean_luma: float = 244.0
    # 極端なクリップ比率
    black_clip_ratio: float = 0.60
    white_clip_ratio: float = 0.50
    near_black_level: int = 12
    near_white_level: int = 243


@dataclass(frozen=True)
class CaptureSettings:
    """機械判定用の撮影設定（数値）。メタ欠落は None。"""

    exposure_time_sec: float | None = None
    f_number: float | None = None
    exposure_bias_ev: float | None = None
    iso: int | None = None


@dataclass(frozen=True)
class MechanicalMetrics:
    sharpness: float
    mean_luma: float
    black_clip_ratio: float
    white_clip_ratio: float
    width: int
    height: int


@dataclass(frozen=True)
class MechanicalDecision:
    path: Path
    rating: int
    passed: bool
    intent_protected: bool
    reason_codes: tuple[str, ...]
    metrics: MechanicalMetrics | None
    capture: CaptureSettings
    error: str | None = None

    def to_dict(self) -> dict:
        d = {
            "path": str(self.path),
            "stage": STAGE,
            "rating": self.rating,
            "passed": self.passed,
            "intent_protected": self.intent_protected,
            "reason_codes": list(self.reason_codes),
            "capture": asdict(self.capture),
            "error": self.error,
            "metrics": asdict(self.metrics) if self.metrics else None,
        }
        return d


@dataclass
class MechanicalBatchResult:
    decisions: list[MechanicalDecision] = field(default_factory=list)
    written: int = 0
    skipped_write: int = 0
    errors: int = 0

    @property
    def pass_count(self) -> int:
        return sum(1 for d in self.decisions if d.passed and d.error is None)

    @property
    def fail_count(self) -> int:
        return sum(1 for d in self.decisions if (not d.passed) and d.error is None)

    def pass_ratio(self) -> float | None:
        scored = self.pass_count + self.fail_count
        if scored == 0:
            return None
        return self.pass_count / scored

    def to_dict(self) -> dict:
        return {
            "stage": STAGE,
            "total": len(self.decisions),
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "pass_ratio": self.pass_ratio(),
            "pass_ratio_guide": 0.80,
            "written": self.written,
            "skipped_write": self.skipped_write,
            "errors": self.errors,
            "decisions": [d.to_dict() for d in self.decisions],
        }


def default_config() -> MechanicalConfig:
    return MechanicalConfig()


def _as_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value) -> int | None:
    f = _as_float(value)
    if f is None:
        return None
    return int(round(f))


def read_capture_settings(path: Path | str) -> CaptureSettings:
    """exiftool -n 優先、失敗時は空（保護なし側に倒れる）。"""
    jpeg = Path(path)
    if not shutil.which("exiftool"):
        return CaptureSettings()
    try:
        proc = subprocess.run(
            [
                "exiftool",
                "-json",
                "-n",
                "-ExposureTime",
                "-FNumber",
                "-ExposureCompensation",
                "-ISO",
                str(jpeg),
            ],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return CaptureSettings()
        tags = json.loads(proc.stdout)[0]
    except Exception:
        return CaptureSettings()

    return CaptureSettings(
        exposure_time_sec=_as_float(tags.get("ExposureTime")),
        f_number=_as_float(tags.get("FNumber")),
        exposure_bias_ev=_as_float(tags.get("ExposureCompensation")),
        iso=_as_int(tags.get("ISO")),
    )


def _resize_for_analysis(img: Image.Image, max_side: int) -> Image.Image:
    w, h = img.size
    long_side = max(w, h)
    if long_side <= max_side:
        return img
    scale = max_side / float(long_side)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    return img.resize((nw, nh), Image.Resampling.BILINEAR)


def compute_image_metrics(path: Path | str, config: MechanicalConfig | None = None) -> MechanicalMetrics:
    """画素から機械指標を算出（読み取りのみ・非破壊）。"""
    cfg = config or default_config()
    with Image.open(path) as im:
        im.load()
        width, height = im.size
        rgb = im.convert("RGB")
        small = _resize_for_analysis(rgb, cfg.analysis_max_side)
        gray = small.convert("L")
        # Laplacian 近似カーネル
        lap = gray.filter(
            ImageFilter.Kernel(
                (3, 3),
                [0, 1, 0, 1, -4, 1, 0, 1, 0],
                scale=1,
                offset=128,
            )
        )
        sharpness = float(ImageStat.Stat(lap).var[0])
        luma_stat = ImageStat.Stat(gray)
        mean_luma = float(luma_stat.mean[0])
        hist = gray.histogram()
        total = max(1, sum(hist))
        black = sum(hist[: max(0, cfg.near_black_level) + 1]) / total
        white = sum(hist[min(255, cfg.near_white_level) :]) / total
    return MechanicalMetrics(
        sharpness=sharpness,
        mean_luma=mean_luma,
        black_clip_ratio=float(black),
        white_clip_ratio=float(white),
        width=width,
        height=height,
    )


def is_intent_protected(capture: CaptureSettings, config: MechanicalConfig | None = None) -> tuple[bool, tuple[str, ...]]:
    """意図保護に該当するか。該当理由コードを返す。"""
    cfg = config or default_config()
    codes: list[str] = []
    if capture.exposure_time_sec is not None and capture.exposure_time_sec >= cfg.slow_shutter_sec:
        codes.append("protect_slow_shutter")
    if capture.f_number is not None and capture.f_number <= cfg.open_aperture_max_f:
        codes.append("protect_open_aperture")
    if capture.exposure_bias_ev is not None and capture.exposure_bias_ev <= cfg.intentional_under_ev:
        codes.append("protect_intentional_under")
    return (len(codes) > 0, tuple(codes))


def evaluate_mechanical(
    path: Path | str,
    config: MechanicalConfig | None = None,
    *,
    capture: CaptureSettings | None = None,
) -> MechanicalDecision:
    """1枚を M1 判定する（メタ書き込みなし）。"""
    cfg = config or default_config()
    jpeg = Path(path)
    cap = capture if capture is not None else read_capture_settings(jpeg)
    protected, protect_codes = is_intent_protected(cap, cfg)

    try:
        metrics = compute_image_metrics(jpeg, cfg)
    except Exception as exc:
        return MechanicalDecision(
            path=jpeg,
            rating=0,
            passed=False,
            intent_protected=protected,
            reason_codes=("error_unreadable",),
            metrics=None,
            capture=cap,
            error=str(exc),
        )

    reasons: list[str] = []
    fail = False

    # 白飛び（明らかな失敗）— 意図保護でも救わない（ハイライト保護はアンダー側）
    if metrics.mean_luma >= cfg.white_mean_luma or metrics.white_clip_ratio >= cfg.white_clip_ratio:
        fail = True
        reasons.append("fail_overexposed")

    # 黒つぶれ — 意図的アンダー／低速なら保護
    if metrics.mean_luma <= cfg.black_mean_luma or metrics.black_clip_ratio >= cfg.black_clip_ratio:
        if protected:
            reasons.append("soft_underexposed_but_protected")
        else:
            fail = True
            reasons.append("fail_underexposed")

    # ブレ／ピンボケ
    if metrics.sharpness < cfg.min_sharpness:
        if protected:
            reasons.append("soft_blur_but_protected")
        else:
            fail = True
            reasons.append("fail_blur")

    if not fail and not reasons:
        reasons.append("pass_ok")

    if protected:
        reasons.extend(protect_codes)

    passed = not fail
    return MechanicalDecision(
        path=jpeg.resolve() if jpeg.exists() else jpeg,
        rating=1 if passed else 0,
        passed=passed,
        intent_protected=protected,
        reason_codes=tuple(dict.fromkeys(reasons)),  # 順序保持で重複除去
        metrics=metrics,
        capture=cap,
        error=None,
    )


def apply_mechanical_decision(
    decision: MechanicalDecision,
    *,
    write: bool = True,
) -> MechanicalDecision:
    """判定結果の Rating を JPEG に書く。write=False なら判定のみ。"""
    if not write:
        return decision
    if decision.error is not None:
        return decision
    try:
        write_rating(decision.path, decision.rating)
        return decision
    except (ExifToolNotFoundError, ExifToolError, OSError, ValueError) as exc:
        return replace(decision, error=f"write_failed: {exc}")


def run_mechanical_on_paths(
    paths: Sequence[Path | str] | Iterable[Path | str],
    config: MechanicalConfig | None = None,
    *,
    write: bool = True,
) -> MechanicalBatchResult:
    """複数 JPEG に M1 を実行。1枚失敗でも継続。"""
    cfg = config or default_config()
    result = MechanicalBatchResult()
    for raw in paths:
        path = Path(raw)
        try:
            decision = evaluate_mechanical(path, cfg)
            decision = apply_mechanical_decision(decision, write=write)
        except Exception as exc:
            decision = MechanicalDecision(
                path=path,
                rating=0,
                passed=False,
                intent_protected=False,
                reason_codes=("error_unexpected",),
                metrics=None,
                capture=CaptureSettings(),
                error=str(exc),
            )
        result.decisions.append(decision)
        if decision.error:
            result.errors += 1
            if write:
                result.skipped_write += 1
        elif write:
            result.written += 1
        else:
            result.skipped_write += 1
    return result


def run_mechanical_on_unit(
    unit: LibraryUnit,
    config: MechanicalConfig | None = None,
    *,
    write: bool = True,
) -> MechanicalBatchResult:
    """LibraryUnit 直下 JPEG に M1 を実行。"""
    return run_mechanical_on_paths(list_source_jpegs(unit), config=config, write=write)
