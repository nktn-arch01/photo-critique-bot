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

# IANA タイムゾーン → 代表座標（緯度, 経度）と都市レベル地域名。
# GPS が無い場合の日出・日没・region 推定に使う（生 GPS は API に送らない）。
TZ_ANCHORS: dict[str, tuple[float, float, str]] = {
    "Asia/Tokyo": (35.6812, 139.7671, "東京"),
    "Asia/Seoul": (37.5665, 126.9780, "ソウル"),
    "Asia/Shanghai": (31.2304, 121.4737, "上海"),
    "Asia/Hong_Kong": (22.3193, 114.1694, "香港"),
    "Asia/Taipei": (25.0330, 121.5654, "台北"),
    "Asia/Singapore": (1.3521, 103.8198, "シンガポール"),
    "Asia/Bangkok": (13.7563, 100.5018, "バンコク"),
    "Asia/Kolkata": (28.6139, 77.2090, "デリー"),
    "Asia/Dubai": (25.2048, 55.2708, "ドバイ"),
    "Asia/Jerusalem": (31.7683, 35.2137, "エルサレム"),
    "Europe/London": (51.5074, -0.1278, "ロンドン"),
    "Europe/Paris": (48.8566, 2.3522, "パリ"),
    "Europe/Berlin": (52.5200, 13.4050, "ベルリン"),
    "Europe/Rome": (41.9028, 12.4964, "ローマ"),
    "Europe/Moscow": (55.7558, 37.6173, "モスクワ"),
    "America/New_York": (40.7128, -74.0060, "ニューヨーク"),
    "America/Chicago": (41.8781, -87.6298, "シカゴ"),
    "America/Denver": (39.7392, -104.9903, "デンバー"),
    "America/Los_Angeles": (34.0522, -118.2437, "ロサンゼルス"),
    "America/Toronto": (43.6532, -79.3832, "トロント"),
    "America/Vancouver": (49.2827, -123.1207, "バンクーバー"),
    "America/Mexico_City": (19.4326, -99.1332, "メキシコシティ"),
    "America/Sao_Paulo": (-23.5505, -46.6333, "サンパウロ"),
    "Australia/Sydney": (-33.8688, 151.2093, "シドニー"),
    "Pacific/Auckland": (-36.8485, 174.7633, "オークランド"),
    "Pacific/Honolulu": (21.3069, -157.8583, "ホノルル"),
}


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


def timezone_anchor(tz: ZoneInfo) -> tuple[float, float, str]:
    """GPS 無し時にタイムゾーンから代表座標と都市レベル地域名を推定する。"""
    key = tz.key if hasattr(tz, "key") else str(tz)
    if key in TZ_ANCHORS:
        return TZ_ANCHORS[key]

    lon = _approx_longitude_from_tz(tz)
    lat = _approx_latitude_from_zone_key(key)
    region = _region_label_from_zone_key(key)
    return lat, lon, region


def _approx_longitude_from_tz(tz: ZoneInfo) -> float:
    """UTC オフセットからタイムゾーン帯の代表経度を概算（15°/h）。"""
    ref = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    local = ref.astimezone(tz)
    offset = local.utcoffset()
    if offset is None:
        return 139.7671
    hours = offset.total_seconds() / 3600.0
    return max(-180.0, min(180.0, hours * 15.0))


def _approx_latitude_from_zone_key(key: str) -> float:
    """IANA ゾーン名のプレフィックスから代表緯度を概算。"""
    if key.startswith("Australia/") or key.startswith("Pacific/Auckland"):
        return -33.0
    if key.startswith("Pacific/Honolulu") or key.startswith("Pacific/Guam"):
        return 21.0
    if key.startswith("America/"):
        south_markers = ("Sao_Paulo", "Buenos_Aires", "Santiago", "Lima", "Bogota")
        if any(m in key for m in south_markers):
            return -23.0
        return 40.0
    if key.startswith("Europe/"):
        return 50.0
    if key.startswith("Africa/"):
        return 5.0
    if key.startswith("Asia/"):
        return 35.0
    return 35.0


def _region_label_from_zone_key(key: str) -> str:
    """IANA ゾーン名から都市レベルの地域ラベルを生成。"""
    if "/" not in key:
        return key
    city = key.split("/")[-1].replace("_", " ")
    return city


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
