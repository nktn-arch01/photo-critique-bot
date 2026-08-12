"""スクリーニング単位向け「カード」生成（Rating 3/4 JPEG）。

Compact（Phase1）→ PNG カード → JPEG Description へ Phase1 upsert。
Works の Lumina Review（Full ノート）とは別経路。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from card_theme import DEFAULT_CARD_THEME, normalize_card_theme
from critique_engine import generate_critique
from critique_lens import DEFAULT_LENS
from generate_critique_card import create_critique_card
from iptc_rating_io import ExifToolNotFoundError, read_screening_meta, require_exiftool
from library_unit import list_source_jpegs, unit_from_dir
from phase1_jpeg import jpeg_has_complete_phase1, write_phase1_from_critique
from scanner import extract_file_metadata

ProgressCb = Callable[[str, str], None]  # event, message

_CARDS_SUFFIX = "Luminaカード"


def _cards_dir(unit_dir: Path) -> Path:
    return unit_dir / f"{unit_dir.name}{_CARDS_SUFFIX}"


def _card_path(unit_dir: Path, file_name: str) -> Path:
    return _cards_dir(unit_dir) / f"{Path(file_name).stem}_card.png"


def _existing_card(unit_dir: Path, file_name: str) -> Path | None:
    candidate = _card_path(unit_dir, file_name)
    return candidate if candidate.is_file() else None



def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ScreeningCardItemResult:
    file_name: str
    path: str
    status: str  # processed | skipped | error
    reason: str = ""
    card_path: str | None = None


@dataclass
class ScreeningCardBatchResult:
    status: str = "running"
    processed: int = 0
    skipped: int = 0
    errors: int = 0
    items: list[ScreeningCardItemResult] = field(default_factory=list)
    error: str | None = None
    started_at: str = field(default_factory=_utc_now_iso)
    finished_at: str | None = None


@dataclass
class ScreeningCardConfig:
    force_overwrite: bool = False
    card_theme: str = DEFAULT_CARD_THEME
    lens: str = DEFAULT_LENS
    ratings: tuple[int, ...] = (3, 4)
    critique_fn: Callable | None = None


class ScreeningCardRunner:
    def __init__(
        self,
        config: ScreeningCardConfig | None = None,
        on_progress: ProgressCb | None = None,
    ) -> None:
        self.config = config or ScreeningCardConfig()
        self._on_progress = on_progress
        self._cancel = threading.Event()

    def request_cancel(self) -> None:
        self._cancel.set()

    def _emit(self, event: str, message: str) -> None:
        if self._on_progress:
            self._on_progress(event, message)

    def run_on_dir(self, unit_dir: Path | str) -> ScreeningCardBatchResult:
        result = ScreeningCardBatchResult()
        target = Path(unit_dir)
        try:
            require_exiftool()
        except ExifToolNotFoundError as e:
            result.status = "failed"
            result.error = str(e)
            result.finished_at = _utc_now_iso()
            self._emit("failed", str(e))
            return result

        if not target.is_dir():
            result.status = "failed"
            result.error = f"フォルダがありません: {target}"
            result.finished_at = _utc_now_iso()
            self._emit("failed", result.error)
            return result

        unit = unit_from_dir(target)
        if unit is None:
            result.status = "failed"
            result.error = f"スクリーニング単位として認識できません: {target.name}"
            result.finished_at = _utc_now_iso()
            self._emit("failed", result.error)
            return result

        try:
            jpegs = list_source_jpegs(unit)
            targets: list[Path] = []
            for jpeg in jpegs:
                try:
                    meta = read_screening_meta(jpeg)
                except Exception:
                    continue
                if meta.rating in self.config.ratings:
                    targets.append(jpeg)

            self._emit("start", f"カード対象 Rating {list(self.config.ratings)}: {len(targets)} 枚")
            if not targets:
                result.status = "completed"
                result.finished_at = _utc_now_iso()
                self._emit("done", "対象 JPEG がありません")
                return result

            theme = normalize_card_theme(self.config.card_theme)
            cards_root = _cards_dir(target)
            cards_root.mkdir(parents=True, exist_ok=True)
            total = len(targets)

            for idx, img_path in enumerate(targets, 1):
                if self._cancel.is_set():
                    result.status = "cancelled"
                    self._emit("cancel", "中断しました")
                    break

                file_name = img_path.name
                self._emit("item", f"({idx}/{total}) {file_name}")

                already = jpeg_has_complete_phase1(img_path) or (
                    _existing_card(target, file_name) is not None
                )
                if already and not self.config.force_overwrite:
                    result.skipped += 1
                    result.items.append(
                        ScreeningCardItemResult(
                            file_name=file_name,
                            path=str(img_path),
                            status="skipped",
                            reason="already_has_phase1_or_card",
                        )
                    )
                    self._emit("skip", f"スキップ（処理済み）: {file_name}")
                    continue

                try:
                    exif_meta, dop_info, _ = extract_file_metadata(img_path)
                    if self.config.critique_fn is not None:
                        critique_text = self.config.critique_fn(
                            img_path, exif_meta, dop_info, "compact", self.config.lens
                        )
                    else:
                        critique_text = generate_critique(
                            img_path,
                            metadata=exif_meta,
                            dop_info=dop_info,
                            mode="compact",
                            lens=self.config.lens,
                        )

                    card_path = _card_path(target, file_name)
                    create_critique_card(img_path, critique_text, card_path, theme=theme)
                    write_phase1_from_critique(img_path, critique_text, lens=self.config.lens)

                    result.processed += 1
                    result.items.append(
                        ScreeningCardItemResult(
                            file_name=file_name,
                            path=str(img_path),
                            status="processed",
                            card_path=str(card_path),
                        )
                    )
                    self._emit("ok", f"完了: {file_name}")
                except Exception as exc:
                    result.errors += 1
                    result.items.append(
                        ScreeningCardItemResult(
                            file_name=file_name,
                            path=str(img_path),
                            status="error",
                            reason=str(exc),
                        )
                    )
                    self._emit("error", f"エラー ({file_name}): {exc}")

            if result.status == "running":
                result.status = "completed"
            result.finished_at = _utc_now_iso()
            self._emit(
                "done",
                f"カード生成{result.status}: 新規={result.processed} "
                f"スキップ={result.skipped} エラー={result.errors}",
            )
            return result
        except Exception as exc:
            result.status = "failed"
            result.error = str(exc)
            result.finished_at = _utc_now_iso()
            self._emit("failed", str(exc))
            return result
