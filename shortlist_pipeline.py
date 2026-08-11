"""R1′-A スクリーニングパイプライン: M1 → M2 → M3 オーケストレーション.

- 月／イベント LibraryUnit 単位
- 進捗コールバック・中断フラグ
- 1枚失敗で全体停止しない（各段の方針を継承）
- 既存講評バッチ（app_gui / analyze_folder）とは別導線
- 監査 JSON は ``delta_log`` により ``_lumina/sessions/`` へ保存（T7）
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from delta_log import save_pipeline_session
from library_unit import LibraryUnit, list_source_jpegs, resolve_unit
from shortlist_antenna import (
    AntennaBatchResult,
    AntennaConfig,
    ScoreFn,
    run_antenna_on_paths,
)
from shortlist_diversity import (
    DiversityBatchResult,
    DiversityConfig,
    FeatureFn,
    run_diversity_on_paths,
)
from shortlist_mechanical import (
    MechanicalBatchResult,
    MechanicalConfig,
    run_mechanical_on_paths,
)

PipelineStatus = Literal["running", "completed", "cancelled", "failed"]
StageName = Literal["m1", "m2", "m3"]

ProgressFn = Callable[["PipelineProgress"], None]


@dataclass(frozen=True)
class PipelineProgress:
    stage: str
    message: str
    current: int | None = None
    total: int | None = None


@dataclass
class PipelineConfig:
    write: bool = True
    run_m1: bool = True
    run_m2: bool = True
    run_m3: bool = True
    persist_session: bool = True
    session_jpeg_rescan: bool = True
    mechanical: MechanicalConfig = field(default_factory=MechanicalConfig)
    antenna: AntennaConfig = field(default_factory=AntennaConfig)
    diversity: DiversityConfig = field(default_factory=DiversityConfig)
    # テスト差し替え（本番は None → Vision）
    m2_score_fn: ScoreFn | None = None
    m3_feature_fn: FeatureFn | None = None


@dataclass
class PipelineResult:
    session_id: str
    unit: LibraryUnit
    status: PipelineStatus
    created_at: str
    finished_at: str | None = None
    jpeg_count: int = 0
    m1: MechanicalBatchResult | None = None
    m2: AntennaBatchResult | None = None
    m3: DiversityBatchResult | None = None
    error: str | None = None
    cancelled: bool = False
    session_path: Path | None = None

    def counts_by_rating_hint(self) -> dict[str, int]:
        """各段結果からの粗い件数。正確な件数は session の counts / jpeg_rescan を参照。"""
        out = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0}
        if self.m1:
            for d in self.m1.decisions:
                if d.error:
                    continue
                key = str(d.rating)
                if key in out:
                    out[key] += 1
        if self.m2:
            for d in self.m2.decisions:
                if d.error or d.skipped:
                    continue
                if d.passed:
                    out["1"] = max(0, out["1"] - 1)
                    out["2"] += 1
        if self.m3:
            for d in self.m3.decisions:
                if d.error or d.skipped or not d.passed:
                    continue
                if d.rating == 4:
                    out["2"] = max(0, out["2"] - 1)
                    out["4"] += 1
                elif d.rating == 3:
                    out["2"] = max(0, out["2"] - 1)
                    out["3"] += 1
        return out

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "library_unit_id": self.unit.unit_id,
            "library_unit_kind": self.unit.kind,
            "library_unit_path": str(self.unit.path),
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "jpeg_count": self.jpeg_count,
            "cancelled": self.cancelled,
            "error": self.error,
            "session_path": str(self.session_path) if self.session_path else None,
            "counts_by_rating_hint": self.counts_by_rating_hint(),
            "m1": self.m1.to_dict() if self.m1 else None,
            "m2": self.m2.to_dict() if self.m2 else None,
            "m3": self.m3.to_dict() if self.m3 else None,
        }


class ShortlistPipeline:
    """キャンセル可能なスクリーニングパイプライン。"""

    def __init__(
        self,
        config: PipelineConfig | None = None,
        *,
        on_progress: ProgressFn | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self.on_progress = on_progress
        self._cancel = threading.Event()

    def request_cancel(self) -> None:
        self._cancel.set()

    def clear_cancel(self) -> None:
        self._cancel.clear()

    def is_cancel_requested(self) -> bool:
        return self._cancel.is_set()

    def _emit(self, stage: str, message: str, current: int | None = None, total: int | None = None) -> None:
        if self.on_progress:
            self.on_progress(
                PipelineProgress(stage=stage, message=message, current=current, total=total)
            )

    def _persist(self, result: PipelineResult) -> PipelineResult:
        cfg = self.config
        if not cfg.persist_session:
            return result
        try:
            path = save_pipeline_session(
                result,
                write_meta=cfg.write,
                include_jpeg_rescan=cfg.session_jpeg_rescan,
            )
            result.session_path = path
            self._emit("session", f"監査ログを保存: {path}")
        except Exception as exc:
            # 監査失敗でスクリーニング結果自体は落とさない
            self._emit("session", f"監査ログ保存に失敗: {exc}")
        return result

    def run_on_unit(self, unit: LibraryUnit) -> PipelineResult:
        cfg = self.config
        created = datetime.now(timezone.utc).isoformat()
        session_id = uuid.uuid4().hex[:12]
        paths = list_source_jpegs(unit)
        result = PipelineResult(
            session_id=session_id,
            unit=unit,
            status="running",
            created_at=created,
            jpeg_count=len(paths),
        )
        self._emit("init", f"{unit.kind} {unit.unit_id}: JPEG {len(paths)} 枚", 0, len(paths))

        if not paths:
            result.status = "completed"
            result.finished_at = datetime.now(timezone.utc).isoformat()
            self._emit("done", "対象 JPEG がありません")
            return self._persist(result)

        try:
            if cfg.run_m1:
                if self.is_cancel_requested():
                    result.status = "cancelled"
                    result.cancelled = True
                    result.finished_at = datetime.now(timezone.utc).isoformat()
                    return self._persist(result)
                self._emit("m1", "M1 機械選別を開始", 0, len(paths))
                result.m1 = run_mechanical_on_paths(
                    paths,
                    cfg.mechanical,
                    write=cfg.write,
                    should_cancel=self.is_cancel_requested,
                )
                self._emit(
                    "m1",
                    f"M1 完了 pass={result.m1.pass_count} fail={result.m1.fail_count} errors={result.m1.errors}",
                    len(result.m1.decisions),
                    len(paths),
                )
                if result.m1.cancelled or self.is_cancel_requested():
                    result.status = "cancelled"
                    result.cancelled = True
                    result.finished_at = datetime.now(timezone.utc).isoformat()
                    return self._persist(result)

            if cfg.run_m2:
                if self.is_cancel_requested():
                    result.status = "cancelled"
                    result.cancelled = True
                    result.finished_at = datetime.now(timezone.utc).isoformat()
                    return self._persist(result)
                self._emit("m2", "M2 アンテナを開始", 0, len(paths))
                result.m2 = run_antenna_on_paths(
                    paths,
                    cfg.antenna,
                    write=cfg.write,
                    score_fn=cfg.m2_score_fn,
                    should_cancel=self.is_cancel_requested,
                )
                self._emit(
                    "m2",
                    f"M2 完了 pass={result.m2.pass_count} skipped={result.m2.skipped} errors={result.m2.errors}",
                    len(result.m2.decisions),
                    len(paths),
                )
                if result.m2.cancelled or self.is_cancel_requested():
                    result.status = "cancelled"
                    result.cancelled = True
                    result.finished_at = datetime.now(timezone.utc).isoformat()
                    return self._persist(result)

            if cfg.run_m3:
                if self.is_cancel_requested():
                    result.status = "cancelled"
                    result.cancelled = True
                    result.finished_at = datetime.now(timezone.utc).isoformat()
                    return self._persist(result)
                self._emit("m3", "M3 多様性を開始", 0, len(paths))
                result.m3 = run_diversity_on_paths(
                    paths,
                    cfg.diversity,
                    write=cfg.write,
                    feature_fn=cfg.m3_feature_fn,
                    should_cancel=self.is_cancel_requested,
                )
                self._emit(
                    "m3",
                    (
                        f"M3 完了 keep={result.m3.pass_count} "
                        f"top={result.m3.top_count} margin={result.m3.margin_count} "
                        f"errors={result.m3.errors}"
                    ),
                    len(result.m3.decisions),
                    len(paths),
                )
                if result.m3.cancelled or self.is_cancel_requested():
                    result.status = "cancelled"
                    result.cancelled = True
                    result.finished_at = datetime.now(timezone.utc).isoformat()
                    return self._persist(result)

            result.status = "completed"
            result.finished_at = datetime.now(timezone.utc).isoformat()
            self._emit("done", "スクリーニングパイプライン完了")
            return self._persist(result)
        except Exception as exc:
            result.status = "failed"
            result.error = str(exc)
            result.finished_at = datetime.now(timezone.utc).isoformat()
            self._emit("error", f"パイプライン失敗: {exc}")
            return self._persist(result)

    def run_on_dir(self, path: Path | str) -> PipelineResult:
        unit = resolve_unit(path)
        return self.run_on_unit(unit)


def parse_stages(text: str) -> tuple[bool, bool, bool]:
    """'m1,m2,m3' 形式。空や all は全段。"""
    raw = (text or "all").strip().lower()
    if raw in ("", "all"):
        return True, True, True
    parts = {p.strip() for p in raw.split(",") if p.strip()}
    unknown = parts - {"m1", "m2", "m3"}
    if unknown:
        raise ValueError(f"未知のステージ: {sorted(unknown)}")
    return ("m1" in parts), ("m2" in parts), ("m3" in parts)
