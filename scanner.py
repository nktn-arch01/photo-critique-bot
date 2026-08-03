import datetime
import re
from pathlib import Path
from PIL import Image, ExifTags


class LuaTableParser:
    @staticmethod
    def parse(lua_str: str) -> dict:
        clean_str = re.sub(r'--[^\r\n]*', '', lua_str)
        token_pattern = re.compile(
            r'\[\[(?P<LONG_STR>[\s\S]*?)\]\]|'
            r'"(?P<STR_DOUBLE>[^"\\]*(?:\\.[^"\\]*)*)"|'
            r"'(?P<STR_SINGLE>[^'\\]*(?:\\.[^'\\]*)*)'|"
            r'(?P<LBRACE>\{)|'
            r'(?P<RBRACE>\})|'
            r'(?P<EQUAL>=)|'
            r'(?P<COMMA>,)|'
            r'(?P<NUMBER>-?\d+(?:\.\d+)?)|'
            r'(?P<BOOL>true|false)|'
            r'(?P<IDENT>[a-zA-Z_][a-zA-Z0-9_]*)'
        )
        tokens = []
        for m in token_pattern.finditer(clean_str):
            kind = m.lastgroup
            val = m.group(kind)
            if kind in ("STR_DOUBLE", "STR_SINGLE", "LONG_STR"):
                tokens.append(("STRING", val))
            elif kind == "NUMBER":
                tokens.append(("NUMBER", float(val) if '.' in val else int(val)))
            elif kind == "BOOL":
                tokens.append(("BOOL", val == "true"))
            else:
                tokens.append((kind, val))

        pos = 0

        def parse_value():
            nonlocal pos
            if pos >= len(tokens): return None
            kind, val = tokens[pos]
            if kind in ("STRING", "NUMBER", "BOOL"):
                pos += 1; return val
            elif kind == "LBRACE": return parse_table()
            elif kind == "IDENT":
                pos += 1; return val
            else:
                pos += 1; return None

        def parse_table():
            nonlocal pos
            if pos < len(tokens) and tokens[pos][0] == "LBRACE": pos += 1
            res_dict, arr_list = {}, []
            while pos < len(tokens):
                kind, val = tokens[pos]
                if kind == "RBRACE": pos += 1; break
                if kind == "COMMA": pos += 1; continue
                if kind in ("IDENT", "NUMBER") and (pos + 1 < len(tokens)) and tokens[pos+1][0] == "EQUAL":
                    key = str(val)
                    pos += 2
                    val_obj = parse_value()
                    res_dict[key] = val_obj
                else:
                    val_obj = parse_value()
                    if val_obj is not None: arr_list.append(val_obj)
            if res_dict and arr_list: res_dict["_array"] = arr_list; return res_dict
            elif res_dict: return res_dict
            else: return arr_list

        root = {}
        while pos < len(tokens):
            if tokens[pos][0] in ("IDENT", "NUMBER") and pos + 1 < len(tokens) and tokens[pos+1][0] == "EQUAL":
                k = str(tokens[pos][1]); pos += 2; root[k] = parse_value()
            else: pos += 1
        return root


def deep_find_key(obj, target_keys: list[str]) -> str | None:
    target_keys_lower = [k.lower() for k in target_keys]

    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in target_keys_lower:
                if v is not None:
                    if isinstance(v, list):
                        vals = [str(x).replace("\x00", "").strip() for x in v if x and str(x).replace("\x00", "").strip()]
                        if vals:
                            return ", ".join(vals)
                    elif isinstance(v, (str, int, float)):
                        s_val = str(v).replace("\x00", "").strip()
                        if s_val:
                            return s_val

        for k, v in obj.items():
            res = deep_find_key(v, target_keys)
            if res is not None:
                return res

    elif isinstance(obj, list):
        for item in obj:
            res = deep_find_key(item, target_keys)
            if res is not None:
                return res

    return None


def _determine_time_zone_fact(dt: datetime.datetime | None) -> str:
    if not dt: return "不明"
    hour = dt.hour
    if 4 <= hour < 7: return "早朝・黎明（日の出前後）"
    elif 7 <= hour < 16: return "日中・昼光"
    elif 16 <= hour < 19: return "夕景・黄昏（日の入り前後）"
    else: return "夜間・深夜"


def _extract_exif_data(image_path: Path) -> dict:
    meta = {
        "date_time": "不明", "time_zone_fact": "不明", "camera_model": "不明",
        "lens_model": "不明", "f_number": "不明", "shutter_speed": "不明",
        "iso": "不明", "focal_length": "不明", "caption": None, "copyright": None, "artist": None,
    }
    try:
        with Image.open(image_path) as img:
            exif_raw = img._getexif()
            if not exif_raw: return meta
            exif = {ExifTags.TAGS.get(k, k): v for k, v in exif_raw.items() if k in ExifTags.TAGS}
            dt_str = exif.get("DateTimeOriginal") or exif.get("DateTime")
            if dt_str:
                try:
                    dt = datetime.datetime.strptime(str(dt_str), "%Y:%m:%d %H:%M:%S")
                    meta["date_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                    meta["time_zone_fact"] = _determine_time_zone_fact(dt)
                except Exception: meta["date_time"] = str(dt_str)

            meta["camera_model"] = str(exif.get("Model", "不明")).replace("\x00", "").strip()
            meta["lens_model"] = str(exif.get("LensModel", "不明")).replace("\x00", "").strip()

            if "FNumber" in exif:
                try: meta["f_number"] = f"f/{float(exif['FNumber']):.1f}"
                except Exception: meta["f_number"] = str(exif["FNumber"])
            if "ExposureTime" in exif:
                try:
                    et = float(exif["ExposureTime"])
                    meta["shutter_speed"] = f"1/{int(1/et)}s" if et < 1 else f"{et}s"
                except Exception: meta["shutter_speed"] = str(exif["ExposureTime"])
            if "ISOSpeedRatings" in exif: meta["iso"] = f"ISO {exif['ISOSpeedRatings']}"
            if "FocalLength" in exif:
                try: meta["focal_length"] = f"{int(float(exif['FocalLength']))}mm"
                except Exception: meta["focal_length"] = str(exif["FocalLength"])

            if "ImageDescription" in exif and exif["ImageDescription"]:
                meta["caption"] = str(exif["ImageDescription"]).replace("\x00", "").strip()
            if "Artist" in exif and exif["Artist"]:
                meta["artist"] = str(exif["Artist"]).replace("\x00", "").strip()
            if "Copyright" in exif and exif["Copyright"]:
                meta["copyright"] = str(exif["Copyright"]).replace("\x00", "").strip()
    except Exception: pass
    return meta


def _extract_dop_data(image_path: Path) -> dict:
    dop_meta = {
        "dop_found": False, "rating_str": "なし", "preset_name": "標準/未指定",
        "content_headline": None, "caption": None, "category": None,
        "other_categories": None, "subject_code": None, "keywords": None,
        "byline": None, "copyright": None,
    }
    candidates = [image_path.parent / f"{image_path.name}.dop", image_path.with_suffix(".dop")]
    for dop_path in candidates:
        if dop_path.exists():
            try:
                content = ""
                for enc in ["utf-8", "utf-8-sig", "cp932", "latin-1"]:
                    try:
                        content = dop_path.read_text(encoding=enc)
                        break
                    except Exception: continue
                if not content: continue

                parsed_root = LuaTableParser.parse(content)
                if not parsed_root: continue
                dop_meta["dop_found"] = True

                rank_val = deep_find_key(parsed_root, ["Rank"])
                if rank_val:
                    try:
                        r_int = int(float(rank_val))
                        if r_int > 0:
                            dop_meta["rating_str"] = "★" * r_int + "☆" * (5 - r_int) + f" ({r_int}/5)"
                    except Exception: pass

                dop_meta["preset_name"] = deep_find_key(parsed_root, ["PresetName", "Preset"]) or "標準/未指定"
                dop_meta["content_headline"] = deep_find_key(parsed_root, ["Headline", "contentHeadline", "Title"])
                dop_meta["caption"] = deep_find_key(parsed_root, ["Caption", "Description", "ImageDescription", "user_intent"])
                dop_meta["category"] = deep_find_key(parsed_root, ["Category", "IPTCCategory"])
                dop_meta["other_categories"] = deep_find_key(parsed_root, ["SupplementalCategories", "OtherCategories", "SupplementalCategory"])
                dop_meta["subject_code"] = deep_find_key(parsed_root, ["SubjectCode", "IPTCSubjectCode"])
                dop_meta["keywords"] = deep_find_key(parsed_root, ["Keywords", "IPTCKeywords", "Tags"])
                dop_meta["byline"] = deep_find_key(parsed_root, ["Byline", "Author", "Artist"])
                dop_meta["copyright"] = deep_find_key(parsed_root, ["Copyright", "IPTCCopyright"])
                break
            except Exception: pass
    return dop_meta


def extract_file_metadata(file_path: Path) -> tuple[dict, dict, str]:
    """単一の写真ファイルからEXIFおよび.dopメタデータを高精度に抽出する共通関数"""
    exif_info = _extract_exif_data(file_path)
    dop_info = _extract_dop_data(file_path)

    final_user_intent = dop_info["caption"] or exif_info["caption"] or "なし"

    headline = dop_info["content_headline"] or "なし"
    category = dop_info["category"] or "なし"
    other_cats = dop_info["other_categories"] or "なし"
    subj_code = dop_info["subject_code"] or "なし"
    keywords = dop_info["keywords"] or "なし"
    byline = dop_info["byline"] or exif_info["artist"] or "なし"
    copyright_str = dop_info["copyright"] or exif_info["copyright"] or "なし"

    dop_status_str = f"あり [評価: {dop_info['rating_str']}] [Preset: {dop_info['preset_name']}]" if dop_info['dop_found'] else "なし"

    meta_block = f"""=== メタデータ ===
file_name: {file_path.name}
date_time: {exif_info['date_time']}
time_zone_fact: {exif_info['time_zone_fact']}
camera_model: {exif_info['camera_model']}
lens_model: {exif_info['lens_model']}
f_number: {exif_info['f_number']}
shutter_speed: {exif_info['shutter_speed']}
iso: {exif_info['iso']}
focal_length: {exif_info['focal_length']}
dxo_dop_sidecar: {dop_status_str}
contentHeadline: {headline}
user_intent: {final_user_intent}
Category: {category}
OtherCategories: {other_cats}
SubjectCode: {subj_code}
Keywords: {keywords}
Byline: {byline}
Copyright: {copyright_str}"""

    metadata_dict = {**exif_info, "user_intent": final_user_intent}
    return metadata_dict, dop_info, meta_block


def scan_monthly_folder(target_dir: Path, log_mgr):
    """月別フォルダ内の一括スキャン処理"""
    valid_exts = {".jpg", ".jpeg", ".png", ".heic"}
    targets, skipped = [], []
    for file_path in sorted(target_dir.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in valid_exts:
            if file_path.name.startswith("._") or "_card" in file_path.stem: continue
            file_name = file_path.name
            if log_mgr.is_processed(file_name):
                skipped.append(file_name); continue

            metadata_dict, dop_info, meta_block = extract_file_metadata(file_path)

            targets.append({
                "path": file_path, "name": file_name, "stem": file_path.stem,
                "metadata": metadata_dict, "dop_info": dop_info, "metadata_block": meta_block,
            })
    return targets, skipped