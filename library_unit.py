"""ライブラリ単位（月 / イベント）の識別と JPEG 列挙.

規則（[`R1A_DESKTOP_OPS_POLICY.md`](docs/R1A_DESKTOP_OPS_POLICY.md)）:

オリジナル（スクリーニング対象）:

- 月: ``YYYYMM`` または ``XXYYYYMM``（``XX`` = 機種2文字、例 ``OM`` / ``FF``）
- イベント: ``YYYYMMDD_短い名前`` または ``XXYYYYMMDD_短い名前``
  - スペースなし。日本語可。記号は ``_`` と ``-`` 以外を避ける
  - このパターンに一致するサブフォルダだけをイベント単位とする
- 月単位の画像: 月フォルダ直下のバラ JPEG（イベント配下は含めない）
- イベント単位の画像: そのイベントフォルダ直下の JPEG

Works（Lumina Review 対象・ユーザー自作）:

- **月 ``YYYYMM`` のみ**（接頭辞なし。イベントサブフォルダは作らない）

スクリーニングの書き込み対象は主に JPEG（``.jpg`` / ``.jpeg``）。
``.dop`` / ``.xmp`` は扱わない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, Literal

UnitKind = Literal["month", "event"]

# 接頭辞なし（後方互換）と XX 接頭辞（実運用）
MONTH_PLAIN_RE = re.compile(r"^(\d{4})(\d{2})$")
MONTH_PREFIXED_RE = re.compile(r"^([A-Za-z]{2})(\d{4})(\d{2})$")
EVENT_PLAIN_RE = re.compile(r"^(\d{8})_([^\s]+)$")
EVENT_PREFIXED_RE = re.compile(r"^([A-Za-z]{2})(\d{8})_([^\s]+)$")
EVENT_DISPLAY_RE = re.compile(r"^[\w\-]+$", re.UNICODE)

SCREENING_JPEG_SUFFIXES = frozenset({".jpg", ".jpeg"})
# Wave 3 互換 alias
SHORTLIST_JPEG_SUFFIXES = SCREENING_JPEG_SUFFIXES


@dataclass(frozen=True)
class LibraryUnit:
    """月またはイベントの1単位。"""

    kind: UnitKind
    unit_id: str
    path: Path
    display_name: str
    month_id: str | None = None  # 暦の YYYYMM（Works 対応・集計用。接頭辞なし）
    start_date: date | None = None
    camera_code: str | None = None  # XX（接頭辞なしなら None）

    @property
    def is_month(self) -> bool:
        return self.kind == "month"

    @property
    def is_event(self) -> bool:
        return self.kind == "event"

    @property
    def works_month_id(self) -> str | None:
        """対応する Works 月フォルダ名（YYYYMM）。"""
        return self.month_id


def _valid_calendar_month(year: int, month: int) -> bool:
    return 1 <= month <= 12 and 1 <= year <= 9999


def _parse_yyyymmdd(text: str) -> date | None:
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def is_works_month_folder_name(name: str) -> bool:
    """Works Lumina Review対象: 接頭辞なし ``YYYYMM`` のみ。"""
    m = MONTH_PLAIN_RE.fullmatch(name)
    if not m:
        return False
    year, month = int(m.group(1)), int(m.group(2))
    return _valid_calendar_month(year, month)


def is_month_folder_name(name: str) -> bool:
    """フォルダ名が月規則（``YYYYMM`` または ``XXYYYYMM``）か。"""
    return try_parse_month_name(name) is not None


def try_parse_month_name(name: str) -> str | None:
    """成功時はフォルダ名そのもの（unit_id）を返す。"""
    m = MONTH_PLAIN_RE.fullmatch(name)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if _valid_calendar_month(year, month):
            return name
        return None
    m = MONTH_PREFIXED_RE.fullmatch(name)
    if m:
        year, month = int(m.group(2)), int(m.group(3))
        if _valid_calendar_month(year, month):
            return name
        return None
    return None


def calendar_month_id_from_folder_name(name: str) -> str | None:
    """フォルダ名から暦の ``YYYYMM`` を取り出す（接頭辞があれば除去）。"""
    m = MONTH_PLAIN_RE.fullmatch(name)
    if m and _valid_calendar_month(int(m.group(1)), int(m.group(2))):
        return name
    m = MONTH_PREFIXED_RE.fullmatch(name)
    if m and _valid_calendar_month(int(m.group(2)), int(m.group(3))):
        return f"{m.group(2)}{m.group(3)}"
    parsed = try_parse_event_name(name)
    if parsed is not None:
        _uid, _disp, start, _code = parsed
        return month_id_from_event_start(start)
    return None


def is_event_folder_name(name: str) -> bool:
    """フォルダ名がイベント規則か。"""
    return try_parse_event_name(name) is not None


def try_parse_event_name(name: str) -> tuple[str, str, date, str | None] | None:
    """成功時: (unit_id, display_name, start_date, camera_code|None)。"""
    m = EVENT_PLAIN_RE.fullmatch(name)
    if m:
        ymd, display = m.group(1), m.group(2)
        if not EVENT_DISPLAY_RE.fullmatch(display):
            return None
        start = _parse_yyyymmdd(ymd)
        if start is None:
            return None
        return name, display, start, None

    m = EVENT_PREFIXED_RE.fullmatch(name)
    if m:
        code, ymd, display = m.group(1), m.group(2), m.group(3)
        if not EVENT_DISPLAY_RE.fullmatch(display):
            return None
        start = _parse_yyyymmdd(ymd)
        if start is None:
            return None
        return name, display, start, code.upper()

    return None


def month_id_from_event_start(start: date) -> str:
    return f"{start.year:04d}{start.month:02d}"


def unit_from_dir(path: Path | str) -> LibraryUnit | None:
    """ディレクトリ1つを LibraryUnit に解釈。規則外なら None。"""
    p = Path(path)
    if not p.is_dir():
        return None
    name = p.name

    m_plain = MONTH_PLAIN_RE.fullmatch(name)
    if m_plain and _valid_calendar_month(int(m_plain.group(1)), int(m_plain.group(2))):
        return LibraryUnit(
            kind="month",
            unit_id=name,
            path=p.resolve(),
            display_name=name,
            month_id=name,
            start_date=None,
            camera_code=None,
        )

    m_pref = MONTH_PREFIXED_RE.fullmatch(name)
    if m_pref and _valid_calendar_month(int(m_pref.group(2)), int(m_pref.group(3))):
        cal = f"{m_pref.group(2)}{m_pref.group(3)}"
        return LibraryUnit(
            kind="month",
            unit_id=name,
            path=p.resolve(),
            display_name=name,
            month_id=cal,
            start_date=None,
            camera_code=m_pref.group(1).upper(),
        )

    parsed = try_parse_event_name(name)
    if parsed is not None:
        unit_id, display, start, code = parsed
        return LibraryUnit(
            kind="event",
            unit_id=unit_id,
            path=p.resolve(),
            display_name=display,
            month_id=month_id_from_event_start(start),
            start_date=start,
            camera_code=code,
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


def is_screening_jpeg(path: Path | str) -> bool:
    p = Path(path)
    return p.is_file() and p.suffix.lower() in SCREENING_JPEG_SUFFIXES and not p.name.startswith(".")


# Wave 3 互換 alias
is_shortlist_jpeg = is_screening_jpeg


def iter_direct_jpegs(directory: Path | str) -> Iterator[Path]:
    """ディレクトリ直下の JPEG のみ（非再帰）。"""
    d = Path(directory)
    if not d.is_dir():
        return
    for child in sorted(d.iterdir(), key=lambda x: x.name.lower()):
        if is_screening_jpeg(child):
            yield child.resolve()


def list_source_jpegs(unit: LibraryUnit) -> list[Path]:
    """単位に属するスクリーニング対象 JPEG。

    - 月: 直下のバラのみ（イベント配下は含まない）
    - イベント: イベントフォルダ直下
    """
    return list(iter_direct_jpegs(unit.path))


def resolve_unit(path: Path | str) -> LibraryUnit:
    """パスを単位として解決。規則外なら ValueError。"""
    unit = unit_from_dir(path)
    if unit is None:
        raise ValueError(
            f"ライブラリ単位として解釈できません"
            f"（月 YYYYMM|XXYYYYMM または イベント YYYYMMDD_名前|XXYYYYMMDD_名前）: {path}"
        )
    return unit


def session_belongs_to_unit(session_path: Path | str, unit_dir: Path | str) -> bool:
    """監査セッション JSON が当該 unit の ``_lumina/sessions`` 配下か。"""
    session = Path(session_path)
    unit = Path(unit_dir)
    if not session.is_file():
        return False
    expected = (unit / "_lumina" / "sessions").resolve()
    try:
        return session.resolve().parent == expected
    except OSError:
        return False


def resolve_session_for_unit(
    unit_dir: Path | str,
    preferred: Path | None = None,
) -> Path | None:
    """H3 記録用: unit 配下のセッションだけを返す（preferred がずれていれば無視）。"""
    from delta_log import latest_session_path, list_session_paths

    target = Path(unit_dir)
    if preferred is not None and session_belongs_to_unit(preferred, target):
        return Path(preferred)
    latest = latest_session_path(target)
    if latest is not None:
        return latest
    paths = list_session_paths(target)
    return paths[-1] if paths else None
