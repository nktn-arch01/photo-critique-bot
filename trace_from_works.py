"""R1′-A T8: Works（または確定フォルダ）上の対話痕跡生成.

- 本アプリは Works へコピーしない（DxO 等が書き出した JPEG を読むだけ）
- 同一 stem では ``{stem}_dev.jpg`` を優先。なければ撮って出し ``.jpg``
- 既存コア再利用: scanner → critique_engine → generate_critique_card → DesktopLogManager
- ``_dev`` / Works 経路ではプロンプトに「画優先・EXIFは撮影記録」を注入
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from card_theme import DEFAULT_CARD_THEME, normalize_card_theme
from critique_engine import generate_critique
from critique_lens import DEFAULT_LENS
from generate_critique_card import create_critique_card
from log_manager import DesktopLogManager
from scanner import extract_file_metadata

JPEG_SUFFIXES = frozenset({".jpg", ".jpeg"})
DEV_STEM_SUFFIX = "_dev"

TraceStatus = Literal["running", "completed", "cancelled", "failed"]
ProgressFn = Callable[["TraceProgress"], None]
# path, metadata, dop_info, mode, lens → critique text
CritiqueFn = Callable[..., str]


@dataclass(frozen=True)
class TraceProgress:
    stage: str
    message: str
    current: int | None = None
    total: int | None = None
    file_name: str | None = None


@dataclass
class TraceConfig:
    mode: str = "full"
    force_overwrite: bool = False
    card_theme: str = DEFAULT_CARD_THEME
    lens: str = DEFAULT_LENS
    # Works 痕跡は常に画優先（現像 JPEG の見た目を一次ソースに）
    pixel_priority: bool = True
    # テスト差し替え（本番は None → critique_engine）
    critique_fn: CritiqueFn | None = None


@dataclass
class TraceItemResult:
    file_name: str
    path: str
    status: Literal["processed", "skipped", "error", "held"]
    reason: str | None = None
    card_path: str | None = None
    note_path: str | None = None
    used_dev: bool = False


@dataclass
class TraceBatchResult:
    works_dir: str
    status: TraceStatus
    created_at: str
    finished_at: str | None = None
    targets_found: int = 0
    processed: int = 0
    skipped: int = 0
    errors: int = 0
    held: int = 0
    items: list[TraceItemResult] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "works_dir": self.works_dir,
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "targets_found": self.targets_found,
            "processed": self.processed,
            "skipped": self.skipped,
            "errors": self.errors,
            "held": self.held,
            "items": [item.__dict__ for item in self.items],
            "error": self.error,
            "copy_performed": False,
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def works_base_stem(path: Path) -> str:
    """``P614_dev.jpg`` → ``P614``、``P614.jpg`` → ``P614``。"""
    stem = path.stem
    lower = stem.lower()
    if lower.endswith(DEV_STEM_SUFFIX):
        return stem[: -len(DEV_STEM_SUFFIX)]
    return stem


def is_dev_export(path: Path) -> bool:
    return path.suffix.lower() in JPEG_SUFFIXES and path.stem.lower().endswith(DEV_STEM_SUFFIX)


def list_works_trace_targets(works_dir: Path) -> list[Path]:
    """Works 直下の痕跡対象 JPEG を列挙（コピーしない）.

    優先順（stem 単位）:
    1. ``{stem}_dev.jpg``
    2. なければ撮って出し ``.jpg`` / ``.jpeg``
    3. どちらも無ければその stem は対象外（保留相当＝リストに出さない）
    """
    root = Path(works_dir)
    if not root.is_dir():
        raise NotADirectoryError(f"Works フォルダがありません: {root}")

    by_base: dict[str, dict[str, Path | None]] = {}
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if name.startswith("._"):
            continue
        if "_card" in path.stem.lower():
            continue
        if path.suffix.lower() not in JPEG_SUFFIXES:
            continue

        base = works_base_stem(path)
        slot = by_base.setdefault(base, {"dev": None, "sooc": None})
        if is_dev_export(path):
            # 同名競合時は辞書順最後を採用（通常1枚）
            slot["dev"] = path
        else:
            slot["sooc"] = path

    targets: list[Path] = []
    for base in sorted(by_base.keys()):
        slot = by_base[base]
        if slot["dev"] is not None:
            targets.append(slot["dev"])
        elif slot["sooc"] is not None:
            targets.append(slot["sooc"])
    return targets


def _note_path_for(log_mgr: DesktopLogManager, file_name: str) -> Path:
    stem = Path(file_name).stem
    return log_mgr.notes_dir / f"{stem}.md"


class WorksTraceRunner:
    """Works フォルダ上の確定 JPEG にカード／ノート／ログを付ける。"""

    def __init__(
        self,
        config: TraceConfig | None = None,
        on_progress: ProgressFn | None = None,
    ) -> None:
        self.config = config or TraceConfig()
        self.on_progress = on_progress
        self._cancel = threading.Event()

    def request_cancel(self) -> None:
        self._cancel.set()

    def _emit(self, stage: str, message: str, **kwargs) -> None:
        if self.on_progress:
            self.on_progress(TraceProgress(stage=stage, message=message, **kwargs))

    def run(self, works_dir: Path) -> TraceBatchResult:
        works_dir = Path(works_dir)
        created = _utc_now_iso()
        result = TraceBatchResult(
            works_dir=str(works_dir.resolve()),
            status="running",
            created_at=created,
        )
        self._cancel.clear()

        try:
            if not works_dir.is_dir():
                raise NotADirectoryError(f"Works フォルダがありません: {works_dir}")

            targets = list_works_trace_targets(works_dir)
            result.targets_found = len(targets)
            self._emit(
                "scan",
                f"痕跡対象 {len(targets)} 枚（_dev 優先・コピーなし）",
                current=0,
                total=len(targets),
            )

            if not targets:
                result.status = "completed"
                result.finished_at = _utc_now_iso()
                self._emit("done", "対象 JPEG がありません")
                return result

            theme = normalize_card_theme(self.config.card_theme)
            log_mgr = DesktopLogManager(works_dir)
            total = len(targets)

            for idx, img_path in enumerate(targets, 1):
                if self._cancel.is_set():
                    result.status = "cancelled"
                    self._emit("cancel", "中断しました", current=idx - 1, total=total)
                    break

                file_name = img_path.name
                used_dev = is_dev_export(img_path)
                self._emit(
                    "item",
                    f"処理中: {file_name}",
                    current=idx,
                    total=total,
                    file_name=file_name,
                )

                if not self.config.force_overwrite and log_mgr.is_processed(file_name):
                    result.skipped += 1
                    result.items.append(
                        TraceItemResult(
                            file_name=file_name,
                            path=str(img_path),
                            status="skipped",
                            reason="already_processed",
                            used_dev=used_dev,
                        )
                    )
                    self._emit("skip", f"スキップ（処理済み）: {file_name}", file_name=file_name)
                    continue

                try:
                    exif_meta, dop_info, metadata_block = extract_file_metadata(img_path)
                    # Works: 画優先フラグをメタに載せてプロンプトへ（T9 前の軽い注記）
                    if self.config.pixel_priority:
                        exif_meta = {**exif_meta, "pixel_priority": True}
                        if used_dev:
                            exif_meta["critique_image_kind"] = "dev_export"
                        else:
                            exif_meta["critique_image_kind"] = "sooc_export"

                    if self.config.critique_fn is not None:
                        critique_text = self.config.critique_fn(
                            img_path,
                            exif_meta,
                            dop_info,
                            self.config.mode,
                            self.config.lens,
                        )
                    else:
                        critique_text = generate_critique(
                            img_path,
                            metadata=exif_meta,
                            dop_info=dop_info,
                            mode=self.config.mode,
                            lens=self.config.lens,
                        )

                    card_path = log_mgr.get_card_output_path(file_name)
                    create_critique_card(
                        img_path, critique_text, card_path, theme=theme
                    )
                    log_mgr.save_analysis_result(file_name, metadata_block, critique_text)
                    note_path = _note_path_for(log_mgr, file_name)

                    result.processed += 1
                    result.items.append(
                        TraceItemResult(
                            file_name=file_name,
                            path=str(img_path),
                            status="processed",
                            card_path=str(card_path),
                            note_path=str(note_path),
                            used_dev=used_dev,
                        )
                    )
                    self._emit("ok", f"完了: {file_name}", file_name=file_name)
                except Exception as exc:
                    result.errors += 1
                    result.items.append(
                        TraceItemResult(
                            file_name=file_name,
                            path=str(img_path),
                            status="error",
                            reason=str(exc),
                            used_dev=used_dev,
                        )
                    )
                    self._emit("error", f"エラー ({file_name}): {exc}", file_name=file_name)

            if result.status == "running":
                result.status = "completed"
            result.finished_at = _utc_now_iso()
            self._emit(
                "done",
                f"痕跡生成{result.status}: 新規={result.processed} "
                f"スキップ={result.skipped} エラー={result.errors}",
            )
            return result
        except Exception as exc:
            result.status = "failed"
            result.error = str(exc)
            result.finished_at = _utc_now_iso()
            self._emit("failed", str(exc))
            return result
