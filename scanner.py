import datetime
import json
import re
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ExifTags

# デスクトップ GUI / CLI / スキャナー共通の対応拡張子
SUPPORTED_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".heic", ".heif"})

_heif_registered = False


def ensure_heif_support() -> None:
    """HEIC/HEIF 読み込み（pillow-heif がある場合のみ）。"""
    global _heif_registered
    if _heif_registered:
        return
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except ImportError:
        pass
    _heif_registered = True


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
                return None  # 構文エラー防止: 不正なトークンを無理に消費しない

        def parse_table():
            nonlocal pos
            if pos < len(tokens) and tokens[pos][0] == "LBRACE": pos += 1
            res_dict, arr_list = {}, []
            while pos < len(tokens):
                kind, val = tokens[pos]
                if kind == "RBRACE": pos += 1; break
                if kind == "COMMA": pos += 1; continue
                if kind in ("IDENT", "STRING", "NUMBER") and (pos + 1 < len(tokens)) and tokens[pos+1][0] == "EQUAL":
                    key = str(val)
                    pos += 2
                    val_obj = parse_value()
                    res_dict[key] = val_obj
                else:
                    val_obj = parse_value()
                    if val_obj is not None:
                        arr_list.append(val_obj)
                    else:
                        pos += 1  # 無限ループ防止のための安全進展
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


def _default_exif_meta() -> dict:
    return {
        "date_time": "不明", "time_zone_fact": "不明", "camera_model": "不明",
        "lens_model": "不明", "f_number": "不明", "shutter_speed": "不明",
        "iso": "不明", "focal_length": "不明", "caption": None, "copyright": None, "artist": None,
    }


def _apply_datetime_to_meta(meta: dict, dt_str: str | None) -> None:
    if not dt_str:
        return
    try:
        dt = datetime.datetime.strptime(str(dt_str).strip(), "%Y:%m:%d %H:%M:%S")
        meta["date_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        meta["time_zone_fact"] = _determine_time_zone_fact(dt)
    except Exception:
        meta["date_time"] = str(dt_str).strip()


def _extract_exif_via_exiftool(image_path: Path) -> dict | None:
    """exiftool -json -n（規則12 第一候補）。未インストール時は None。"""
    if not shutil.which("exiftool"):
        return None
    try:
        proc = subprocess.run(
            ["exiftool", "-json", "-n", str(image_path)],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        tags = json.loads(proc.stdout)[0]
    except Exception:
        return None

    meta = _default_exif_meta()
    _apply_datetime_to_meta(
        meta,
        tags.get("DateTimeOriginal") or tags.get("CreateDate") or tags.get("ModifyDate"),
    )

    model = tags.get("Model") or tags.get("CameraModelName")
    if model:
        meta["camera_model"] = str(model).replace("\x00", "").strip()

    lens = tags.get("LensModel") or tags.get("Lens") or tags.get("LensID")
    if lens:
        meta["lens_model"] = str(lens).replace("\x00", "").strip()

    if tags.get("FNumber") is not None:
        try:
            meta["f_number"] = f"f/{float(tags['FNumber']):.1f}"
        except Exception:
            meta["f_number"] = str(tags["FNumber"])

    if tags.get("ExposureTime") is not None:
        try:
            et = float(tags["ExposureTime"])
            if et <= 0:
                meta["shutter_speed"] = str(tags["ExposureTime"])
            elif et < 1:
                meta["shutter_speed"] = f"1/{int(round(1 / et))}s"
            else:
                meta["shutter_speed"] = f"{et}s"
        except Exception:
            meta["shutter_speed"] = str(tags["ExposureTime"])

    if tags.get("ISO") is not None:
        meta["iso"] = f"ISO {tags['ISO']}"

    if tags.get("FocalLength") is not None:
        try:
            meta["focal_length"] = f"{int(float(tags['FocalLength']))}mm"
        except Exception:
            meta["focal_length"] = str(tags["FocalLength"])

    for tag, key in (
        ("ImageDescription", "caption"),
        ("Description", "caption"),
        ("Artist", "artist"),
        ("Copyright", "copyright"),
    ):
        val = tags.get(tag)
        if val and not meta.get(key):
            meta[key] = str(val).replace("\x00", "").strip()

    return meta


def _extract_exif_via_pil(image_path: Path) -> dict:
    meta = _default_exif_meta()
    try:
        ensure_heif_support()
        with Image.open(image_path) as img:
            exif_raw = img._getexif()
            if not exif_raw:
                return meta
            exif = {ExifTags.TAGS.get(k, k): v for k, v in exif_raw.items() if k in ExifTags.TAGS}
            _apply_datetime_to_meta(
                meta,
                exif.get("DateTimeOriginal") or exif.get("DateTime"),
            )

            meta["camera_model"] = str(exif.get("Model", "不明")).replace("\x00", "").strip()
            meta["lens_model"] = str(exif.get("LensModel", "不明")).replace("\x00", "").strip()

            if "FNumber" in exif:
                try:
                    meta["f_number"] = f"f/{float(exif['FNumber']):.1f}"
                except Exception:
                    meta["f_number"] = str(exif["FNumber"])
            if "ExposureTime" in exif:
                try:
                    et = float(exif["ExposureTime"])
                    if et <= 0:
                        meta["shutter_speed"] = str(exif["ExposureTime"])
                    elif et < 1:
                        meta["shutter_speed"] = f"1/{int(round(1 / et))}s"
                    else:
                        meta["shutter_speed"] = f"{et}s"
                except Exception:
                    meta["shutter_speed"] = str(exif["ExposureTime"])
            if "ISOSpeedRatings" in exif:
                meta["iso"] = f"ISO {exif['ISOSpeedRatings']}"
            if "FocalLength" in exif:
                try:
                    meta["focal_length"] = f"{int(float(exif['FocalLength']))}mm"
                except Exception:
                    meta["focal_length"] = str(exif["FocalLength"])

            if "ImageDescription" in exif and exif["ImageDescription"]:
                meta["caption"] = str(exif["ImageDescription"]).replace("\x00", "").strip()
            if "Artist" in exif and exif["Artist"]:
                meta["artist"] = str(exif["Artist"]).replace("\x00", "").strip()
            if "Copyright" in exif and exif["Copyright"]:
                meta["copyright"] = str(exif["Copyright"]).replace("\x00", "").strip()
    except Exception:
        pass
    return meta


def _merge_exif_meta(primary: dict | None, fallback: dict) -> dict:
    """primary（exiftool）を優先し、欠損項目のみ fallback（PIL）で補完。"""

    def _missing(val) -> bool:
        if val is None:
            return True
        if val == "不明":
            return True
        return isinstance(val, str) and not str(val).strip()

    out = _default_exif_meta()
    for key in out:
        val = primary.get(key) if primary else None
        if _missing(val):
            val = fallback.get(key)
        if not _missing(val):
            out[key] = val
    return out


def _extract_exif_data(image_path: Path) -> dict:
    exif_tool = _extract_exif_via_exiftool(image_path)
    pil_meta = _extract_exif_via_pil(image_path)
    return _merge_exif_meta(exif_tool, pil_meta)


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

                dop_meta["dop_found"] = True

                # --- 1. テキストからの直接正規表現抽出 (確実・最優先) ---
                # 評価 (Rating / Rank)
                m_rate = re.search(r'(?:Rating|Rank|StarRating)\s*=\s*(\d+)', content)
                if m_rate:
                    try:
                        r_int = int(m_rate.group(1))
                        if r_int > 0:
                            dop_meta["rating_str"] = "★" * r_int + "☆" * (5 - r_int) + f" ({r_int}/5)"
                    except Exception: pass

                # プリセット名 (AppliedPresetDisplayName)
                m_preset = re.search(r'(?:AppliedPresetDisplayName|PresetName|AppliedPresetUniqueName)\s*=\s*"([^"]+)"', content)
                if m_preset:
                    dop_meta["preset_name"] = m_preset.group(1).strip()

                # 撮影意図・コメント (contentDescription)
                m_cap = re.search(r'(?:contentDescription|Caption|Description|ImageDescription)\s*=\s*"([^"]*)"', content)
                if m_cap and m_cap.group(1).strip():
                    dop_meta["caption"] = m_cap.group(1).strip()

                # 見出し (contentHeadline)
                m_head = re.search(r'(?:contentHeadline|Headline|Title)\s*=\s*"([^"]*)"', content)
                if m_head and m_head.group(1).strip():
                    dop_meta["content_headline"] = m_head.group(1).strip()

                # カテゴリー (Category)
                m_cat = re.search(r'(?:IPTCCategory|Category)\s*=\s*"([^"]*)"', content)
                if m_cat and m_cat.group(1).strip():
                    dop_meta["category"] = m_cat.group(1).strip()

                # --- 2. Lua テーブルパースによる二次深層レスキュー ---
                try:
                    parsed_root = LuaTableParser.parse(content)
                    if parsed_root:
                        if dop_meta["rating_str"] == "なし":
                            rank_val = deep_find_key(parsed_root, ["Rating", "Rank", "StarRating"])
                            if rank_val:
                                r_int = int(float(rank_val))
                                if r_int > 0:
                                    dop_meta["rating_str"] = "★" * r_int + "☆" * (5 - r_int) + f" ({r_int}/5)"

                        if dop_meta["preset_name"] == "標準/未指定":
                            preset_val = deep_find_key(parsed_root, ["AppliedPresetDisplayName", "PresetName", "Preset"])
                            if preset_val: dop_meta["preset_name"] = preset_val

                        if not dop_meta["caption"]:
                            dop_meta["caption"] = deep_find_key(parsed_root, ["contentDescription", "Caption", "Description", "ImageDescription", "user_intent"])

                        if not dop_meta["content_headline"]:
                            dop_meta["content_headline"] = deep_find_key(parsed_root, ["contentHeadline", "Headline", "Title"])

                        dop_meta["other_categories"] = deep_find_key(parsed_root, ["SupplementalCategories", "OtherCategories", "SupplementalCategory"])
                        dop_meta["subject_code"] = deep_find_key(parsed_root, ["SubjectCode", "IPTCSubjectCode"])
                        dop_meta["keywords"] = deep_find_key(parsed_root, ["Keywords", "IPTCKeywords", "Tags"])
                        dop_meta["byline"] = deep_find_key(parsed_root, ["Byline", "Author", "Artist"])
                        dop_meta["copyright"] = deep_find_key(parsed_root, ["Copyright", "IPTCCopyright"])
                except Exception:
                    pass  # Luaパースで例外が起きても、上記1で抽出したデータは保護される

                break
            except Exception: pass
    return dop_meta


def extract_file_metadata(file_path: Path) -> tuple[dict, dict, str]:
    """単一の写真ファイルからEXIFおよび.dopメタデータを高精度に抽出する共通関数"""
    ensure_heif_support()
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
    valid_exts = SUPPORTED_IMAGE_SUFFIXES
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