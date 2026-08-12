"""Works（または確定フォルダ）上の Lumina Review.

- 本アプリは Works へコピーしない（DxO 等が書き出した JPEG を読むだけ）
- 同一 stem では ``{stem}_dev.jpg`` を優先。なければ撮って出し ``.jpg``
- 既存コア再利用: scanner → critique_engine → generate_critique_card → DesktopLogManager
- ``_dev`` / Works 経路ではプロンプトに「画優先・EXIFは撮影記録」を注入

Wave 3: 正式モジュール名。旧 ``trace_from_works`` は互換再エクスポート。
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
from phase1_jpeg import read_phase1_critique_text, write_phase1_from_critique
from scanner import extract_file_metadata

JPEG_SUFFIXES = frozenset({".jpg", ".jpeg"})
DEV_STEM_SUFFIX = "_dev"

ReviewStatus = Literal["running", "completed", "cancelled", "failed"]
ProgressFn = Callable[["ReviewProgress"], None]
# path, metadata, dop_info, mode, lens → critique text
CritiqueFn = Callable[..., str]


@dataclass(frozen=True)
class ReviewProgress:
    stage: str
    message: str
    current: int | None = None
    total: int | None = None
    file_name: str | None = None


@dataclass
class ReviewConfig:
    mode: str = "full"
    force_overwrite: bool = False
    card_theme: str = DEFAULT_CARD_THEME
    lens: str = DEFAULT_LENS
    # Works Lumina Reviewは常に画優先（現像 JPEG の見た目を一次ソースに）
    pixel_priority: bool = True
    # テスト差し替え（本番は None → critique_engine）
    critique_fn: CritiqueFn | None = None


@dataclass
class ReviewItemResult:
    file_name: str
    path: str
    status: Literal["processed", "skipped", "error", "held"]
    reason: str | None = None
    card_path: str | None = None
    note_path: str | None = None
    used_dev: bool = False


@dataclass
class ReviewBatchResult:
    works_dir: str
    status: ReviewStatus
    created_at: str
    finished_at: str | None = None
    targets_found: int = 0
    processed: int = 0
    skipped: int = 0
    errors: int = 0
    held: int = 0
    items: list[ReviewItemResult] = field(default_factory=list)
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


def summarize_review_errors(result: ReviewBatchResult, *, limit: int = 5) -> str:
    """完了ダイアログ用のエラー要約（Wave B4）。空なら空文字。"""
    lines: list[str] = []
    if result.error:
        lines.append(f"バッチ: {result.error}")
    err_items = [i for i in result.items if i.status == "error"]
    for item in err_items[:limit]:
        reason = (item.reason or "不明").strip()
        if len(reason) > 80:
            reason = reason[:77] + "…"
        lines.append(f"・{item.file_name}: {reason}")
    extra = len(err_items) - limit
    if extra > 0:
        lines.append(f"・他 {extra} 件（ログを確認）")
    if not lines:
        return ""
    return "\n".join(lines)


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


def _works_review_slots(works_dir: Path) -> dict[str, dict[str, Path | None]]:
    """Works 直下 JPEG を base stem → {dev, sooc} に分類（直下のみ）。"""
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
    return by_base


def list_works_review_targets(works_dir: Path) -> list[Path]:
    """Works 直下の Lumina Review 対象 JPEG を列挙（コピーしない）.

    優先順（stem 単位）:
    1. ``{stem}_dev.jpg``
    2. なければ撮って出し ``.jpg`` / ``.jpeg``
    3. どちらも無ければその stem は対象外（保留相当＝リストに出さない）

    運用契約どおり **直下のみ**（サブフォルダは再帰しない）。
    """
    return list(summarize_works_review_selection(works_dir)["targets"])


def summarize_works_review_selection(works_dir: Path | str) -> dict:
    """Lumina Review 対象の内訳（§2.6: _dev 優先で外した撮って出しを見える化）.

    戻り値キー:
    - ``targets``: 実際にレビューする Path リスト
    - ``dev_count`` / ``sooc_count``: 対象のうち _dev / 撮って出しの枚数
    - ``sooc_skipped``: _dev があるため対象外になった撮って出し Path リスト
    """
    by_base = _works_review_slots(Path(works_dir))
    targets: list[Path] = []
    sooc_skipped: list[Path] = []
    for base in sorted(by_base.keys()):
        slot = by_base[base]
        if slot["dev"] is not None:
            targets.append(slot["dev"])
            if slot["sooc"] is not None:
                sooc_skipped.append(slot["sooc"])
        elif slot["sooc"] is not None:
            targets.append(slot["sooc"])

    return {
        "targets": targets,
        "dev_count": sum(1 for p in targets if is_dev_export(p)),
        "sooc_count": sum(1 for p in targets if not is_dev_export(p)),
        "sooc_skipped": sooc_skipped,
    }


def count_jpegs_in_immediate_subdirs(works_dir: Path | str) -> int:
    """直下サブフォルダ内の JPEG 枚数（L4 案内用。再帰は1段のみ）。"""
    root = Path(works_dir)
    if not root.is_dir():
        return 0
    total = 0
    for child in root.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name.startswith("_"):
            continue
        for path in child.iterdir():
            if not path.is_file():
                continue
            if path.name.startswith("._"):
                continue
            if path.suffix.lower() in JPEG_SUFFIXES:
                total += 1
    return total


def works_empty_targets_hint(works_dir: Path | str) -> str:
    """対象0枚のときのユーザー向け追記（サブフォルダに JPEG がある場合）。"""
    n = count_jpegs_in_immediate_subdirs(works_dir)
    if n <= 0:
        return ""
    return (
        f"\n\n注意: サブフォルダ内に JPEG が {n} 枚ありますが、"
        "Works Lumina Review の対象は月フォルダ直下のみです。"
        "イベント用サブフォルダは使わず、直下へ置いてください。"
    )


def _note_path_for(log_mgr: DesktopLogManager, file_name: str) -> Path:
    stem = Path(file_name).stem
    return log_mgr.notes_dir / f"{stem}.md"


class LuminaReviewRunner:
    """Works フォルダ上の確定 JPEG にカード／ノート／ログを付ける。"""

    def __init__(
        self,
        config: ReviewConfig | None = None,
        on_progress: ProgressFn | None = None,
    ) -> None:
        self.config = config or ReviewConfig()
        self.on_progress = on_progress
        self._cancel = threading.Event()

    def request_cancel(self) -> None:
        self._cancel.set()

    def _emit(self, stage: str, message: str, **kwargs) -> None:
        if self.on_progress:
            self.on_progress(ReviewProgress(stage=stage, message=message, **kwargs))

    def run(self, works_dir: Path) -> ReviewBatchResult:
        works_dir = Path(works_dir)
        created = _utc_now_iso()
        result = ReviewBatchResult(
            works_dir=str(works_dir.resolve()),
            status="running",
            created_at=created,
        )
        self._cancel.clear()

        try:
            if not works_dir.is_dir():
                raise NotADirectoryError(f"Works フォルダがありません: {works_dir}")

            targets = list_works_review_targets(works_dir)
            result.targets_found = len(targets)
            self._emit(
                "scan",
                f"Lumina Review 対象 {len(targets)} 枚（_dev 優先・コピーなし）",
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
                        ReviewItemResult(
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

                    embedded_phase1 = read_phase1_critique_text(img_path, lens=self.config.lens)
                    had_phase1 = embedded_phase1 is not None

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
                            phase1_override=embedded_phase1,
                        )

                    card_path = log_mgr.get_card_output_path(file_name)
                    create_critique_card(
                        img_path, critique_text, card_path, theme=theme
                    )
                    log_mgr.save_analysis_result(file_name, metadata_block, critique_text)
                    # Console 未処理 JPEG にも Phase1 を埋め込み（再 Review の正本）
                    if not had_phase1 or self.config.force_overwrite:
                        try:
                            write_phase1_from_critique(
                                img_path, critique_text, lens=self.config.lens
                            )
                        except Exception as iptc_exc:
                            self._emit(
                                "warn",
                                f"Phase1 IPTC 書込注意 ({file_name}): {iptc_exc}",
                                file_name=file_name,
                            )
                    note_path = _note_path_for(log_mgr, file_name)

                    result.processed += 1
                    result.items.append(
                        ReviewItemResult(
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
                        ReviewItemResult(
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
                f"Lumina Review{result.status}: 新規={result.processed} "
                f"スキップ={result.skipped} エラー={result.errors}",
            )
            return result
        except Exception as exc:
            result.status = "failed"
            result.error = str(exc)
            result.finished_at = _utc_now_iso()
            self._emit("failed", str(exc))
            return result


# Wave 3 互換 alias（1リリース据え置き）
TraceStatus = ReviewStatus
TraceProgress = ReviewProgress
TraceConfig = ReviewConfig
TraceItemResult = ReviewItemResult
TraceBatchResult = ReviewBatchResult
WorksTraceRunner = LuminaReviewRunner
list_works_trace_targets = list_works_review_targets
