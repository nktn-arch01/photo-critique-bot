"""ライブラリ単位（月 / イベント）の識別と JPEG 列挙.

規則（LUMINA_NOTES_SERVICE_CONCEPT §5 / R1′ LibraryUnit）:

- 月フォルダ名: ``YYYYMM``（実在する年月）
- イベントフォルダ名: ``YYYYMMDD_短い名前``
  - スペースなし。日本語可。記号は ``_`` と ``-`` 以外を避ける
  - このパターンに一致するサブフォルダだけをイベント単位とする
  - 一致しないサブフォルダはイベント扱いしない
- 月単位の画像: 月フォルダ直下のバラ JPEG（イベント配下は含めない）
- イベント単位の画像: そのイベントフォルダ直下の JPEG

短絡バッチの書き込み対象は主に JPEG（``.jpg`` / ``.jpeg``）。
``.dop`` / ``.xmp`` は扱わない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, Literal

UnitKind = Literal["month", "event"]

MONTH_NAME_RE = re.compile(r"^(\d{4})(\d{2})$")
# 表示名: 空白なし。英数字・日本語等の単語文字と _ - のみ
EVENT_NAME_RE = re.compile(r"^(\d{8})_([^\s]+)$")
EVENT_DISPLAY_RE = re.compile(r"^[\w\-]+$", re.UNICODE)

SHORTLIST_JPEG_SUFFIXES = frozenset({".jpg", ".jpeg"})


@dataclass(frozen=True)
class LibraryUnit:
    """月またはイベントの1単位。"""

    kind: UnitKind
    unit_id: str
    path: Path
    display_name: str
    month_id: str | None = None
    start_date: date | None = None

    @property
    def is_month(self) -> bool:
        return self.kind == "month"

    @property
    def is_event(self) -> bool:
        return self.kind == "event"


def _valid_calendar_month(year: int, month: int) -> bool:
    return 1 <= month <= 12 and 1 <= year <= 9999


def _parse_yyyymmdd(text: str) -> date | None:
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def is_month_folder_name(name: str) -> bool:
    """フォルダ名が月規則 ``YYYYMM`` か。"""
    return try_parse_month_name(name) is not None


def try_parse_month_name(name: str) -> str | None:
    m = MONTH_NAME_RE.fullmatch(name)
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if not _valid_calendar_month(year, month):
        return None
    return name


def is_event_folder_name(name: str) -> bool:
    """フォルダ名がイベント規則 ``YYYYMMDD_短い名前`` か。"""
    return try_parse_event_name(name) is not None


def try_parse_event_name(name: str) -> tuple[str, str, date] | None:
    """成功時: (unit_id, display_name, start_date)。"""
    m = EVENT_NAME_RE.fullmatch(name)
    if not m:
        return None
    ymd, display = m.group(1), m.group(2)
    if not EVENT_DISPLAY_RE.fullmatch(display):
        return None
    # 表示名だけの余分なルール: 先頭末尾の _- は許容するが空は不可（正規表現で担保）
    start = _parse_yyyymmdd(ymd)
    if start is None:
        return None
    return name, display, start


def month_id_from_event_start(start: date) -> str:
    return f"{start.year:04d}{start.month:02d}"


def unit_from_dir(path: Path | str) -> LibraryUnit | None:
    """ディレクトリ1つを LibraryUnit に解釈。規則外なら None。"""
    p = Path(path)
    if not p.is_dir():
        return None
    name = p.name

    month = try_parse_month_name(name)
    if month is not None:
        return LibraryUnit(
            kind="month",
            unit_id=month,
            path=p.resolve(),
            display_name=month,
            month_id=month,
            start_date=None,
        )

    parsed = try_parse_event_name(name)
    if parsed is not None:
        unit_id, display, start = parsed
        return LibraryUnit(
            kind="event",
            unit_id=unit_id,
            path=p.resolve(),
            display_name=display,
            month_id=month_id_from_event_start(start),
            start_date=start,
        )

    return None


def list_month_units(photos_root: Path | str) -> list[LibraryUnit]:
    """Photos ルート直下の月フォルダを列挙（名前順）。"""
    root = Path(photos_root)
    if not root.is_dir():
        return []
    units: list[LibraryUnit] = []
    for child in sorted(root.iterdir(), key=lambda x: x.name):
        if not child.is_dir() or child.name.startswith("."):
            continue
        unit = unit_from_dir(child)
        if unit is not None and unit.is_month:
            units.append(unit)
    return units


def list_event_units(month_unit: LibraryUnit) -> list[LibraryUnit]:
    """月フォルダ直下のイベント単位のみ列挙。規則外サブフォルダは無視。"""
    if not month_unit.is_month:
        raise ValueError("list_event_units は月単位に対してのみ呼べます")
    events: list[LibraryUnit] = []
    for child in sorted(month_unit.path.iterdir(), key=lambda x: x.name):
        if not child.is_dir() or child.name.startswith("."):
            continue
        unit = unit_from_dir(child)
        if unit is not None and unit.is_event:
            events.append(unit)
    return events


def list_non_event_subdirs(month_unit: LibraryUnit) -> list[Path]:
    """月直下でイベント規則に一致しないサブフォルダ（診断・リネーム案内用）。"""
    if not month_unit.is_month:
        raise ValueError("list_non_event_subdirs は月単位に対してのみ呼べます")
    odd: list[Path] = []
    for child in sorted(month_unit.path.iterdir(), key=lambda x: x.name):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if not is_event_folder_name(child.name):
            odd.append(child.resolve())
    return odd


def discover_units(photos_root: Path | str) -> list[LibraryUnit]:
    """ルート配下の月＋そのイベントを平坦リストで返す（月→イベントの順）。"""
    out: list[LibraryUnit] = []
    for month in list_month_units(photos_root):
        out.append(month)
        out.extend(list_event_units(month))
    return out


def is_shortlist_jpeg(path: Path | str) -> bool:
    p = Path(path)
    return p.is_file() and p.suffix.lower() in SHORTLIST_JPEG_SUFFIXES and not p.name.startswith(".")


def iter_direct_jpegs(directory: Path | str) -> Iterator[Path]:
    """ディレクトリ直下の JPEG のみ（非再帰）。"""
    d = Path(directory)
    if not d.is_dir():
        return
    for child in sorted(d.iterdir(), key=lambda x: x.name.lower()):
        if is_shortlist_jpeg(child):
            yield child.resolve()


def list_source_jpegs(unit: LibraryUnit) -> list[Path]:
    """単位に属する短絡対象 JPEG。

    - 月: 直下のバラのみ（イベント配下は含まない）
    - イベント: イベントフォルダ直下
    """
    return list(iter_direct_jpegs(unit.path))


def resolve_unit(path: Path | str) -> LibraryUnit:
    """パスを単位として解決。規則外なら ValueError。"""
    unit = unit_from_dir(path)
    if unit is None:
        raise ValueError(
            f"ライブラリ単位として解釈できません（月 YYYYMM または "
            f"イベント YYYYMMDD_名前）: {path}"
        )
    return unit
