"""江戸時代の不定時法に準じた時間帯（光の状態の手掛かり）。

日出・日没（天文計算）を基準に、昼間を7区分、夜間を「夜」に一括する。
表記はオーナー指定の7段階 + 夜。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

# 昼間7段階（明け六つ〜暮れ六つに沿った現代表記）
FUTEI_DAY_BANDS: tuple[str, ...] = (
    "夜明け（六）",
    "朝方（五）",
    "午前（四）",
    "正午（九）",
    "午後（八）",
    "夕方（七）",
    "夕暮れ（六）",
)
FUTEI_NIGHT_BAND = "夜"

FuteiBandLabel = Literal[
    "夜明け（六）",
    "朝方（五）",
    "午前（四）",
    "正午（九）",
    "午後（八）",
    "夕方（七）",
    "夕暮れ（六）",
    "夜",
    "不明",
]


@dataclass(frozen=True)
class SunTimes:
    """指定日・緯度経度の日出・日没（ローカル時刻）。"""

    sunrise: datetime
    sunset: datetime
    dawn_roku: datetime  # 明け六つ目安（日出約30分前）
    dusk_roku: datetime  # 暮れ六つ目安（日没約30分後）


def _to_local(dt_utc: datetime, tz: ZoneInfo) -> datetime:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(tz)


def solar_sun_times(day: date, lat: float, lon: float, tz: ZoneInfo) -> SunTimes | None:
    """日出・日没を天文近似で算出。極地など算出不能時は None。"""
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None

    zenith = math.radians(90.833)  # 日出日没の標準天頂角
    day_of_year = day.timetuple().tm_yday
    lng_hour = lon / 15.0

    t_rise = _solar_time_transit(day_of_year, lng_hour, lat, zenith, sunrise=True)
    t_set = _solar_time_transit(day_of_year, lng_hour, lat, zenith, sunrise=False)
    if t_rise is None or t_set is None:
        return None

    def _combine(hour_float: float) -> datetime:
        hour = int(hour_float)
        minute = int((hour_float - hour) * 60)
        second = int(round(((hour_float - hour) * 60 - minute) * 60))
        local_naive = datetime.combine(day, time(hour, minute, second))
        return local_naive.replace(tzinfo=tz)

    sunrise = _combine(t_rise)
    sunset = _combine(t_set)
    if sunset <= sunrise:
        return None

    dawn_roku = sunrise - timedelta(minutes=30)
    dusk_roku = sunset + timedelta(minutes=30)
    return SunTimes(sunrise=sunrise, sunset=sunset, dawn_roku=dawn_roku, dusk_roku=dusk_roku)


def _solar_time_transit(
    day_of_year: int,
    lng_hour: float,
    lat: float,
    zenith: float,
    *,
    sunrise: bool,
) -> float | None:
    lng_rad = math.radians(lat)
    t = day_of_year + ((6 - lng_hour) / 24.0 if sunrise else (18 - lng_hour) / 24.0)

    m = (0.9856 * t) - 3.289
    l = m + (1.916 * math.sin(math.radians(m))) + (0.020 * math.sin(math.radians(2 * m))) + 282.634
    l = l % 360.0

    ra = math.degrees(math.atan(0.91764 * math.tan(math.radians(l))))
    ra = (ra + 360.0) % 360.0
    l_quadrant = (math.floor(l / 90.0)) * 90.0
    ra_quadrant = (math.floor(ra / 90.0)) * 90.0
    ra = ra + (l_quadrant - ra_quadrant)
    ra /= 15.0

    sin_dec = 0.39782 * math.sin(math.radians(l))
    cos_dec = math.cos(math.asin(sin_dec))

    cos_h = (math.cos(zenith) - (sin_dec * math.sin(lng_rad))) / (cos_dec * math.cos(lng_rad))
    if cos_h > 1.0 or cos_h < -1.0:
        return None

    h = 360.0 - math.degrees(math.acos(cos_h)) if sunrise else math.degrees(math.acos(cos_h))
    h /= 15.0

    local_time = h + ra - (0.06571 * t) - 6.622
    return (local_time + 24.0) % 24.0


def classify_futei_band(
    shot_at: datetime,
    lat: float | None,
    lon: float | None,
    tz: ZoneInfo,
) -> FuteiBandLabel:
    """撮影時刻と GPS から不定時法インスパイアの時間帯ラベルを返す。"""
    if shot_at.tzinfo is None:
        shot_local = shot_at.replace(tzinfo=tz)
    else:
        shot_local = shot_at.astimezone(tz)

    if lat is None or lon is None:
        return "不明"

    sun = solar_sun_times(shot_local.date(), lat, lon, tz)
    if sun is None:
        return "不明"

    if shot_local < sun.dawn_roku or shot_local >= sun.dusk_roku:
        return FUTEI_NIGHT_BAND

    span = sun.dusk_roku - sun.dawn_roku
    if span.total_seconds() <= 0:
        return "不明"

    ratio = (shot_local - sun.dawn_roku).total_seconds() / span.total_seconds()
    idx = min(6, max(0, int(ratio * 7)))
    return FUTEI_DAY_BANDS[idx]  # type: ignore[return-value]
