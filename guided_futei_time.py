"""江戸時代の不定時法に準じた時間帯（画面用）と、光の手掛かり（講評用）。

画面の時間帯は日出〜日没を不定時で7区分し、夜間は「夜」。
講評プロンプトには朝日／夕日などの名前を渡さず、太陽の方位と高度から
東／西の低い光などの手掛かりだけを渡す（朝夕の取り違え防止）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

# 昼間7段階（明け六つ〜暮れ六つに沿った現代表記）— 選ぶ画面用
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

# 太陽高度（度）。ブルーアワー〜マジックアワー相当の境界。
# 夜: 高度 < BLUE_HOUR_LOW / ブルーアワー: BLUE_HOUR_LOW〜GOLDEN_HOUR_LOW /
# ゴールデンアワー: GOLDEN_HOUR_LOW〜GOLDEN_HOUR_HIGH / それ以上は高い自然光
BLUE_HOUR_LOW_DEG = -8.0
GOLDEN_HOUR_LOW_DEG = -4.0
GOLDEN_HOUR_HIGH_DEG = 6.0

# NOAA 日出（屈折込み）とブルーアワー開始（太陽高度 -8°）の天頂角
_ZENITH_SUNRISE_DEG = 90.833
_ZENITH_BLUE_HOUR_DEG = 90.0 - BLUE_HOUR_LOW_DEG  # 98°
_ZENITH_CIVIL_DEG = 96.0

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
    """指定日・緯度経度の日出・日没と薄明境界（ローカル時計時刻）。"""

    sunrise: datetime
    sunset: datetime
    dawn_roku: datetime  # ブルーアワー開始（太陽高度 約 -8°）。算出不能時は日出30分前
    dusk_roku: datetime  # ブルーアワー終了（太陽高度 約 -8°）。算出不能時は日没30分後


@dataclass(frozen=True)
class SolarPosition:
    """太陽の見かけ位置。方位は北=0・東=90・南=180・西=270。"""

    elevation_deg: float
    azimuth_deg: float


def solar_sun_times(day: date, lat: float, lon: float, tz: ZoneInfo) -> SunTimes | None:
    """日出・日没を天文近似で算出し、タイムゾーンの時計時刻へ変換する。"""
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None

    sunrise = _solar_event_local(day, lat, lon, tz, _ZENITH_SUNRISE_DEG, sunrise=True)
    sunset = _solar_event_local(day, lat, lon, tz, _ZENITH_SUNRISE_DEG, sunrise=False)
    if sunrise is None or sunset is None or sunset <= sunrise:
        return None

    dawn = _solar_event_local(day, lat, lon, tz, _ZENITH_BLUE_HOUR_DEG, sunrise=True)
    dusk = _solar_event_local(day, lat, lon, tz, _ZENITH_BLUE_HOUR_DEG, sunrise=False)
    if dawn is None or dusk is None:
        dawn = _solar_event_local(day, lat, lon, tz, _ZENITH_CIVIL_DEG, sunrise=True)
        dusk = _solar_event_local(day, lat, lon, tz, _ZENITH_CIVIL_DEG, sunrise=False)
    if dawn is None or dusk is None:
        dawn = sunrise - timedelta(minutes=30)
        dusk = sunset + timedelta(minutes=30)
    if dusk <= dawn:
        return None

    return SunTimes(sunrise=sunrise, sunset=sunset, dawn_roku=dawn, dusk_roku=dusk)


def _solar_event_local(
    day: date,
    lat: float,
    lon: float,
    tz: ZoneInfo,
    zenith_deg: float,
    *,
    sunrise: bool,
) -> datetime | None:
    """NOAA 近似の太陽時を UTC 経由でローカル時計へ直す。"""
    lng_hour = lon / 15.0
    local_mean = _solar_time_transit(
        day.timetuple().tm_yday,
        lng_hour,
        lat,
        math.radians(zenith_deg),
        sunrise=sunrise,
    )
    if local_mean is None:
        return None
    ut_hours = (local_mean - lng_hour) % 24.0
    return _ut_hours_to_local_date(day, ut_hours, tz)


def _ut_hours_to_local_date(day: date, ut_hours: float, tz: ZoneInfo) -> datetime:
    """UTC 時刻（0–24h）を、指定したローカル暦日の時計時刻へ合わせる。"""
    ut_hours = ut_hours % 24.0
    hour = int(ut_hours)
    minute_frac = (ut_hours - hour) * 60.0
    minute = int(minute_frac)
    second = int(round((minute_frac - minute) * 60.0))
    if second >= 60:
        second = 0
        minute += 1
    if minute >= 60:
        minute = 0
        hour += 1
    extra_days = 0
    if hour >= 24:
        extra_days, hour = divmod(hour, 24)
    utc = datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=timezone.utc)
    if extra_days:
        utc += timedelta(days=extra_days)
    local = utc.astimezone(tz)
    if local.date() > day:
        local = (utc - timedelta(days=1)).astimezone(tz)
    elif local.date() < day:
        local = (utc + timedelta(days=1)).astimezone(tz)
    return local


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


def solar_position(shot_at: datetime, lat: float, lon: float) -> SolarPosition | None:
    """撮影瞬間の太陽高度・方位（NOAA 近似）。"""
    if shot_at.tzinfo is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None

    dt_utc = shot_at.astimezone(timezone.utc)
    jd = _julian_day(dt_utc)
    jc = (jd - 2451545.0) / 36525.0

    geom_mean_long = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360.0
    geom_mean_anom = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    eccent = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    mr = math.radians(geom_mean_anom)
    eq_center = (
        (1.914602 - jc * (0.004817 + 0.000014 * jc)) * math.sin(mr)
        + (0.019993 - 0.000101 * jc) * math.sin(2.0 * mr)
        + 0.000289 * math.sin(3.0 * mr)
    )
    sun_true_long = geom_mean_long + eq_center
    omega = 125.04 - 1934.136 * jc
    lambda_app = sun_true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    mean_obliq = 23.0 + (26.0 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60.0) / 60.0
    obliq = mean_obliq + 0.00256 * math.cos(math.radians(omega))
    decl = math.asin(math.sin(math.radians(obliq)) * math.sin(math.radians(lambda_app)))

    y = math.tan(math.radians(obliq) / 2.0) ** 2
    l0 = math.radians(geom_mean_long)
    eqtime = 4.0 * math.degrees(
        y * math.sin(2.0 * l0)
        - 2.0 * eccent * math.sin(mr)
        + 4.0 * eccent * y * math.sin(mr) * math.cos(2.0 * l0)
        - 0.5 * y * y * math.sin(4.0 * l0)
        - 1.25 * eccent * eccent * math.sin(2.0 * mr)
    )

    minutes_utc = dt_utc.hour * 60.0 + dt_utc.minute + dt_utc.second / 60.0
    true_solar_min = (minutes_utc + eqtime + 4.0 * lon) % 1440.0
    if true_solar_min / 4.0 < 0:
        ha = true_solar_min / 4.0 + 180.0
    else:
        ha = true_solar_min / 4.0 - 180.0

    lat_r = math.radians(lat)
    ha_r = math.radians(ha)
    czenith = math.sin(lat_r) * math.sin(decl) + math.cos(lat_r) * math.cos(decl) * math.cos(ha_r)
    czenith = max(-1.0, min(1.0, czenith))
    zenith = math.degrees(math.acos(czenith))
    elevation = 90.0 - zenith

    az_y = math.sin(ha_r)
    az_x = math.cos(ha_r) * math.sin(lat_r) - math.tan(decl) * math.cos(lat_r)
    azimuth = (math.degrees(math.atan2(az_y, az_x)) + 180.0) % 360.0
    return SolarPosition(elevation_deg=elevation, azimuth_deg=azimuth)


def _julian_day(dt_utc: datetime) -> float:
    y = dt_utc.year
    m = dt_utc.month
    day_frac = dt_utc.day + (dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0) / 24.0
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + day_frac + b - 1524.5


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
    """撮影時刻と座標から不定時法インスパイアの時間帯ラベルを返す（画面用）。"""
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


def _azimuth_bearing(azimuth_deg: float) -> str:
    a = azimuth_deg % 360.0
    if 45.0 <= a < 135.0:
        return "東寄り"
    if 135.0 <= a < 225.0:
        return "南寄り"
    if 225.0 <= a < 315.0:
        return "西寄り"
    return "北寄り"


def classify_light_hint(
    shot_at: datetime | None,
    lat: float | None,
    lon: float | None,
    tz: ZoneInfo,
) -> str:
    """講評用の光の手掛かり。禁止語（朝日・夕日・夕暮れ等）を含めない。"""
    if shot_at is None or lat is None or lon is None:
        return "不明"

    if shot_at.tzinfo is None:
        shot_local = shot_at.replace(tzinfo=tz)
    else:
        shot_local = shot_at.astimezone(tz)

    pos = solar_position(shot_local, lat, lon)
    if pos is None:
        return "不明"

    el = pos.elevation_deg
    bearing = _azimuth_bearing(pos.azimuth_deg)

    if el < BLUE_HOUR_LOW_DEG:
        return "太陽は地平線のかなり下（人工光が主になりやすい）"

    if el < GOLDEN_HOUR_HIGH_DEG:
        quality = "ブルーアワー相当" if el < GOLDEN_HOUR_LOW_DEG else "ゴールデンアワー相当"
        if bearing == "東寄り":
            return (
                f"東の空からの低い自然光（一日の前半・{quality}。"
                "ガラスのオレンジや青い空があっても西の空の光ではない）"
            )
        if bearing == "西寄り":
            return (
                f"西の空からの低い自然光（一日の後半・{quality}。"
                "ガラスのオレンジや青い空があっても東の空の光ではない）"
            )
        return f"低い自然光（{quality}）"

    if bearing in {"南寄り", "北寄り"}:
        return f"{bearing}の高い自然光"
    return "高い自然光"
