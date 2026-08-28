"""Guided Web 向けメタデータ抽象化（API 送信パラメータ）。

ローカルログには scanner の全文を残し、API には本モジュールの出力のみ渡す。
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from guided_futei_time import FuteiBandLabel, classify_futei_band
from scanner import ensure_heif_support, extract_file_metadata

DEFAULT_TZ = ZoneInfo("Asia/Tokyo")
_GEOCODE_CACHE_PATH = Path.home() / ".lumina_notes" / "geocode_cache.json"


@dataclass(frozen=True)
class GuidedImageInfo:
    image_id: str
    size: str  # "4032x3024" 等
    shot_at: str  # ISO 8601
    timezone: str  # IANA または UTC オフセット
    region: str  # 都市レベル
    time_band: FuteiBandLabel  # 不定時法インスパイア7段階 + 夜


@dataclass(frozen=True)
class GuidedCameraSettings:
    focal_length: str
    aperture: str
    shutter_speed: str
    iso: str
    mode: str
    exposure_compensation: str


@dataclass(frozen=True)
class GuidedApiParameters:
    """API 送信に使う抽象化パラメータ（画像バイトは別送）。"""

    image: GuidedImageInfo
    camera: GuidedCameraSettings

    def to_dict(self) -> dict[str, Any]:
        return {
            "image": asdict(self.image),
            "camera": asdict(self.camera),
        }

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, **kwargs)


def build_guided_api_parameters(
    image_path: Path,
    *,
    image_id: str | None = None,
    tz: ZoneInfo | None = None,
    geocode: bool = True,
) -> tuple[GuidedApiParameters, dict, dict, str]:
    """ファイルから API 用パラメータとローカル用メタを構築。

    Returns:
        (api_params, metadata_dict, dop_info, meta_block)
    """
    ensure_heif_support()
    metadata, dop_info, meta_block = extract_file_metadata(image_path)
    extra = _read_exiftool_extra(image_path)
    merged = {**metadata, **extra}

    tz = tz or _resolve_timezone(merged)
    shot_dt = _parse_shot_datetime(merged.get("date_time"), merged.get("datetime_offset"))
    lat, lon = merged.get("gps_lat"), merged.get("gps_lon")

    width = merged.get("image_width")
    height = merged.get("image_height")
    size = f"{width}x{height}" if width and height else _size_from_path(image_path)

    iid = image_id or _image_id_from_path(image_path)
    region = resolve_city_region(lat, lon, merged, geocode=geocode)
    band = classify_futei_band(shot_dt, lat, lon, tz) if shot_dt else "不明"

    shot_at_iso = shot_dt.isoformat() if shot_dt else "不明"

    api = GuidedApiParameters(
        image=GuidedImageInfo(
            image_id=iid,
            size=size,
            shot_at=shot_at_iso,
            timezone=str(tz.key) if hasattr(tz, "key") else str(tz),
            region=region,
            time_band=band,
        ),
        camera=GuidedCameraSettings(
            focal_length=_nz(merged.get("focal_length")),
            aperture=_nz(merged.get("f_number")),
            shutter_speed=_nz(merged.get("shutter_speed")),
            iso=_nz(merged.get("iso")),
            mode=_nz(merged.get("exposure_mode")),
            exposure_compensation=_nz(merged.get("exposure_compensation")),
        ),
    )
    return api, metadata, dop_info, meta_block


def _nz(val: object, default: str = "不明") -> str:
    if val is None:
        return default
    text = str(val).replace("\x00", "").strip()
    return text if text and text != "不明" else default


def _image_id_from_path(path: Path) -> str:
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return digest[:16]
    except OSError:
        return uuid.uuid4().hex[:16]


def _size_from_path(path: Path) -> str:
    try:
        from PIL import Image

        with Image.open(path) as img:
            return f"{img.width}x{img.height}"
    except Exception:
        return "不明"


def _parse_shot_datetime(date_time: str | None, offset: str | None) -> datetime | None:
    if not date_time or date_time == "不明":
        return None
    raw = str(date_time).strip()
    normalized = raw.replace(":", "-", 2) if re.match(r"^\d{4}:\d{2}:\d{2}", raw) else raw
    try:
        dt = datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    if offset and re.match(r"^[+-]\d{2}:\d{2}$", offset.strip()):
        sign = 1 if offset[0] == "+" else -1
        hours, minutes = int(offset[1:3]), int(offset[4:6])
        from datetime import timedelta, timezone as dt_tz

        fixed = dt_tz(sign * timedelta(hours=hours, minutes=minutes))
        return dt.replace(tzinfo=fixed)
    return dt.replace(tzinfo=DEFAULT_TZ)


def _resolve_timezone(merged: dict) -> ZoneInfo:
    off = merged.get("datetime_offset")
    if off and re.match(r"^[+-]\d{2}:\d{2}$", str(off).strip()):
        sign = 1 if str(off)[0] == "+" else -1
        hours, minutes = int(str(off)[1:3]), int(str(off)[4:6])
        # zoneinfo には固定オフセットのみの Zone がないため、よく使う Asia/Tokyo を優先
        if str(off) in ("+09:00",):
            return ZoneInfo("Asia/Tokyo")
        _ = (sign, hours, minutes)
    tz_name = merged.get("timezone_name")
    if tz_name:
        try:
            return ZoneInfo(str(tz_name))
        except Exception:
            pass
    return DEFAULT_TZ


def resolve_city_region(
    lat: float | None,
    lon: float | None,
    exif_tags: dict | None = None,
    *,
    geocode: bool = True,
) -> str:
    """撮影地域を都市レベルで返す。GPS は API に送らない。"""
    tags = exif_tags or {}
    city = _first_nonempty(tags.get("city"), tags.get("location_city"))
    state = _first_nonempty(tags.get("state"), tags.get("province"))
    country = _first_nonempty(tags.get("country"))

    if city and city != "不明":
        if state and state != "不明":
            return f"{city}, {state}"
        if country and country != "不明":
            return f"{city}, {country}"
        return city

    if lat is None or lon is None:
        return "不明"

    if geocode:
        cached = _geocode_cached(lat, lon)
        if cached:
            return cached

    return "不明"


def _first_nonempty(*vals: object) -> str | None:
    for v in vals:
        if v is None:
            continue
        s = str(v).replace("\x00", "").strip()
        if s and s != "不明":
            return s
    return None


def _geocode_cached(lat: float, lon: float) -> str | None:
    key = f"{round(lat, 2)},{round(lon, 2)}"
    cache = _load_geocode_cache()
    if key in cache:
        return cache[key]

    city = _nominatim_city(lat, lon)
    if city:
        cache[key] = city
        _save_geocode_cache(cache)
    return city


def _load_geocode_cache() -> dict[str, str]:
    if not _GEOCODE_CACHE_PATH.is_file():
        return {}
    try:
        return json.loads(_GEOCODE_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_geocode_cache(cache: dict[str, str]) -> None:
    try:
        _GEOCODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _GEOCODE_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _nominatim_city(lat: float, lon: float) -> str | None:
    try:
        import urllib.parse
        import urllib.request

        q = urllib.parse.urlencode(
            {"format": "jsonv2", "lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "zoom": 10, "addressdetails": 1}
        )
        url = f"https://nominatim.openstreetmap.org/reverse?{q}"
        req = urllib.request.Request(url, headers={"User-Agent": "LuminaNotes-Guided/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        addr = data.get("address") or {}
        city = (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("municipality")
            or addr.get("county")
        )
        state = addr.get("state") or addr.get("province")
        if city and state:
            return f"{city}, {state}"
        if city:
            return str(city)
    except Exception:
        return None
    return None


def _read_exiftool_extra(image_path: Path) -> dict[str, Any]:
    """GPS・寸法・露出補正・モードなど scanner 未収録項目。"""
    import shutil
    import subprocess

    if not shutil.which("exiftool"):
        return _read_pil_extra(image_path)

    try:
        proc = subprocess.run(
            ["exiftool", "-json", "-n", str(image_path)],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return _read_pil_extra(image_path)
        tags = json.loads(proc.stdout)[0]
    except Exception:
        return _read_pil_extra(image_path)

    out: dict[str, Any] = {}
    lat, lon = _parse_gps_tags(tags)
    if lat is not None and lon is not None:
        out["gps_lat"] = lat
        out["gps_lon"] = lon

    for tag, key in (
        ("ImageWidth", "image_width"),
        ("ImageHeight", "image_height"),
        ("OffsetTimeOriginal", "datetime_offset"),
        ("TimeZone", "timezone_name"),
        ("City", "city"),
        ("State", "state"),
        ("Country", "country"),
        ("Location", "location_city"),
    ):
        if tags.get(tag) is not None:
            out[key] = tags[tag]

    exp_comp = tags.get("ExposureCompensation")
    if exp_comp is not None:
        try:
            out["exposure_compensation"] = f"{float(exp_comp):+.1f} EV"
        except (TypeError, ValueError):
            out["exposure_compensation"] = str(exp_comp)

    mode = tags.get("ExposureProgram") or tags.get("SceneCaptureType") or tags.get("Mode")
    if mode is not None:
        out["exposure_mode"] = _exposure_program_label(mode)

    return out


def _exposure_program_label(value: object) -> str:
    mapping = {
        0: "未設定",
        1: "マニュアル",
        2: "プログラム",
        3: "絞り優先",
        4: "シャッター優先",
        5: "クリエイティブプログラム",
        6: "マニュアル",
        7: "ポートレート",
        8: "風景",
    }
    if isinstance(value, (int, float)):
        return mapping.get(int(value), str(int(value)))
    return str(value)


def _parse_gps_tags(tags: dict) -> tuple[float | None, float | None]:
    if tags.get("GPSLatitude") is not None and tags.get("GPSLongitude") is not None:
        try:
            lat = float(tags["GPSLatitude"])
            lon = float(tags["GPSLongitude"])
            if str(tags.get("GPSLatitudeRef", "N")).upper().startswith("S"):
                lat = -abs(lat)
            if str(tags.get("GPSLongitudeRef", "E")).upper().startswith("W"):
                lon = -abs(lon)
            return lat, lon
        except (TypeError, ValueError):
            pass
    pos = tags.get("GPSPosition")
    if isinstance(pos, str) and pos.strip():
        m = re.match(r"([+-]?\d+\.?\d*)\s+([+-]?\d+\.?\d*)", pos.replace("deg", " ").replace("'", " "))
        if m:
            return float(m.group(1)), float(m.group(2))
    return None, None


def _read_pil_extra(image_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            out["image_width"] = img.width
            out["image_height"] = img.height
    except Exception:
        pass
    return out
