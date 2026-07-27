import re
from datetime import datetime
from pathlib import Path
from PIL import Image, IptcImagePlugin
from PIL.ExifTags import TAGS


def get_time_zone_fact(hour: int, minute: int) -> str:
    """撮影時刻(HH:MM)から時間帯ファクトラベルを厳格に判定する"""
    time_val = hour * 60 + minute

    if 240 <= time_val < 390:      # 04:00 - 06:29
        return "早朝・黎明（日の出前後）"
    elif 390 <= time_val < 660:    # 06:30 - 10:59
        return "午前（朝の光）"
    elif 660 <= time_val < 900:    # 11:00 - 14:59
        return "昼間・日中（トップライト）"
    elif 900 <= time_val < 1020:  # 15:00 - 16:59
        return "午後・遅い午後（斜光）"
    elif 1020 <= time_val < 1140:  # 17:00 - 18:59
        return "夕方・日没前後（マジックアワー）"
    elif 1140 <= time_val < 1260:  # 19:00 - 20:59
        return "夜間・黄昏時"
    else:                          # 21:00 - 03:59
        return "深夜・ナイト"


def extract_dop_metadata(image_path: Path) -> dict:
    """.dop ファイルから全拡張IPTCメタデータを抽出する"""
    dop_data = {
        "user_intent": "なし",
        "category": "なし",
        "headline": "なし",
        "other_categories": "なし",
        "subject_code": "なし",
    }

    # 検索候補
    candidates = [
        image_path.with_suffix(".dop"),
        Path(str(image_path) + ".dop"),
    ]
    
    target_dop = None
    for cand in candidates:
        if cand.exists():
            target_dop = cand
            break

    if not target_dop:
        dop_files = list(image_path.parent.glob("*.dop"))
        if dop_files:
            target_dop = dop_files[0]

    if not target_dop or not target_dop.exists():
        return dop_data

    try:
        content = target_dop.read_text(encoding="utf-8", errors="ignore")

        # フィールド対応マップ
        field_map = {
            "contentDescription": "user_intent",
            "contentCategory": "category",
            "contentHeadline": "headline",
            "contentOtherCategories": "other_categories",
            "contentSubjectCode": "subject_code",
        }

        for dop_key, meta_key in field_map.items():
            match = re.search(rf'{dop_key}\s*=\s*"([^"]*)"', content)
            if match and match.group(1).strip():
                dop_data[meta_key] = match.group(1).strip()

    except Exception as e:
        print(f"[-] DOP抽出エラー ({image_path.name}): {e}")

    return dop_data


def extract_jpeg_metadata(image_path: Path) -> dict:
    """JPEG画像および関連.dopから全メタデータを抽出する"""
    metadata = {
        "file_name": image_path.name,
        "date_time": "不明",
        "time_zone_fact": "不明",
        "camera_model": "不明",
        "lens_model": "不明",
        "f_number": "不明",
        "shutter_speed": "不明",
        "iso": "不明",
        "focal_length": "不明",
        "user_intent": "なし",
        "category": "なし",
        "headline": "なし",
        "other_categories": "なし",
        "subject_code": "なし",
    }

    try:
        with Image.open(image_path) as img:
            # 1. EXIFデータの抽出
            exif_data = img._getexif()
            if exif_data:
                exif = {
                    TAGS.get(key, key): value
                    for key, value in exif_data.items()
                }

                # 撮影日時 ＆ time_zone_fact
                dt_str = exif.get("DateTimeOriginal") or exif.get("DateTime")
                if dt_str:
                    try:
                        dt = datetime.strptime(str(dt_str), "%Y:%m:%d %H:%M:%S")
                        metadata["date_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                        metadata["time_zone_fact"] = get_time_zone_fact(dt.hour, dt.minute)
                    except ValueError:
                        pass

                # パラメータ
                metadata["camera_model"] = str(exif.get("Model", "不明")).strip()
                metadata["lens_model"] = str(exif.get("LensModel", "不明")).strip()

                if "FNumber" in exif:
                    try:
                        metadata["f_number"] = f"f/{float(exif['FNumber']):.1f}"
                    except (ValueError, TypeError):
                        pass

                if "ExposureTime" in exif:
                    try:
                        exp = float(exif["ExposureTime"])
                        metadata["shutter_speed"] = f"1/{int(1/exp)}s" if exp < 1 else f"{exp}s"
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

                if "ISOSpeedRatings" in exif:
                    metadata["iso"] = f"ISO {exif['ISOSpeedRatings']}"

                if "FocalLength" in exif:
                    try:
                        metadata["focal_length"] = f"{int(float(exif['FocalLength']))}mm"
                    except (ValueError, TypeError):
                        pass

        # 2. DOP拡張メタデータの統合
        dop_meta = extract_dop_metadata(image_path)
        metadata.update(dop_meta)

    except Exception as e:
        print(f"[-] メタデータ抽出エラー ({image_path.name}): {e}")

    return metadata


def format_metadata_block(metadata: dict) -> str:
    """分析ノート・ログ追記用のメタデータブロック文字列を生成する"""
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
