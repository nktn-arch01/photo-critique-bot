"""API 抽象パラメータの画面表示用ラベルと一覧構築。"""

from __future__ import annotations

from typing import Any

IMAGE_PARAM_ROWS: tuple[tuple[str, str], ...] = (
    ("file_name", "ファイル名"),
    ("size", "サイズ"),
    ("shot_at", "撮影日時"),
    ("timezone", "タイムゾーン"),
    ("region", "地域"),
    ("time_band", "時間帯"),
)

CAMERA_PARAM_ROWS: tuple[tuple[str, str], ...] = (
    ("focal_length", "焦点距離"),
    ("aperture", "絞り"),
    ("shutter_speed", "シャッター速度"),
    ("iso", "ISO"),
    ("mode", "露出モード"),
    ("exposure_compensation", "露出補正"),
)


def build_parameter_display(
    api_parameters: dict[str, Any],
    *,
    file_name: str | None = None,
) -> list[dict[str, Any]]:
    """構想 PDF / §7.3 準拠のパラメータ一覧を返す。"""
    image = dict(api_parameters.get("image") or {})
    if file_name:
        image["file_name"] = file_name
    camera = api_parameters.get("camera") or {}
    return [
        {
            "title": "画像情報",
            "rows": _rows(image, IMAGE_PARAM_ROWS),
        },
        {
            "title": "カメラ設定",
            "rows": _rows(camera, CAMERA_PARAM_ROWS),
        },
    ]


def _rows(source: dict[str, Any], schema: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key, label in schema:
        value = source.get(key)
        rows.append({"key": key, "label": label, "value": _format_value(value)})
    return rows


def _format_value(value: object) -> str:
    if value is None:
        return "不明"
    text = str(value).strip()
    return text if text else "不明"
