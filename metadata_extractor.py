"""
後方互換ラッパ（非推奨）。
新規コード・本番処理は scanner.extract_file_metadata() を使用すること（規則8）。
"""

from pathlib import Path

from scanner import extract_file_metadata


def extract_jpeg_metadata(image_path: Path) -> dict:
    """scanner.extract_file_metadata の平坦化ラッパ（CLIテスト用）。"""
    exif_meta, dop_info, _ = extract_file_metadata(image_path)
    return {
        "file_name": image_path.name,
        "date_time": exif_meta.get("date_time", "不明"),
        "time_zone_fact": exif_meta.get("time_zone_fact", "不明"),
        "camera_model": exif_meta.get("camera_model", "不明"),
        "lens_model": exif_meta.get("lens_model", "不明"),
        "f_number": exif_meta.get("f_number", "不明"),
        "shutter_speed": exif_meta.get("shutter_speed", "不明"),
        "iso": exif_meta.get("iso", "不明"),
        "focal_length": exif_meta.get("focal_length", "不明"),
        "user_intent": exif_meta.get("user_intent", "なし"),
        "category": dop_info.get("category") or "なし",
        "headline": dop_info.get("content_headline") or "なし",
        "other_categories": dop_info.get("other_categories") or "なし",
        "subject_code": dop_info.get("subject_code") or "なし",
    }


def format_metadata_block(metadata: dict) -> str:
    """辞書からメタデータブロック文字列を生成（テスト表示用）。"""
    return f"""=== メタデータ ===
file_name: {metadata.get('file_name', '不明')}
date_time: {metadata.get('date_time', '不明')}
time_zone_fact: {metadata.get('time_zone_fact', '不明')}
camera_model: {metadata.get('camera_model', '不明')}
lens_model: {metadata.get('lens_model', '不明')}
f_number: {metadata.get('f_number', '不明')}
shutter_speed: {metadata.get('shutter_speed', '不明')}
iso: {metadata.get('iso', '不明')}
focal_length: {metadata.get('focal_length', '不明')}
user_intent: {metadata.get('user_intent', 'なし')}
Category: {metadata.get('category', 'なし')}
contentHeadline: {metadata.get('headline', 'なし')}
OtherCategories: {metadata.get('other_categories', 'なし')}
SubjectCode: {metadata.get('subject_code', 'なし')}"""


def format_metadata_block_from_path(image_path: Path) -> str:
    """画像パスから scanner 経由でメタデータブロックを取得。"""
    _, _, meta_block = extract_file_metadata(image_path)
    return meta_block
