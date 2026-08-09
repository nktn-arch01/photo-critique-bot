import re

from critique_lens import DEFAULT_LENS, CritiqueLens, get_lens, score_alias_to_key


# ラベルに空白や（English）があっても拾う
_SCORE_LINE = re.compile(
    r"・\s*(.+?)\s*[:：]\s*([★☆]+)\s*[\(（]\s*([\d\.]+)\s*[/／]\s*5\s*[\)）]"
)


def _normalize_scores(raw_scores: dict, lens: CritiqueLens) -> dict:
    """旧ラベル／別名を正規化し、レンズ定義の軸順で並べる。

    戻り値のキーは表示ラベル（canonical）。各値に key / stars / val を持つ。
    未知ラベルは末尾に元のラベルのまま残す（将来の動的軸の逃げ道）。
    """
    by_key: dict[str, dict] = {}
    unknown: list[tuple[str, dict]] = []

    for label, info in raw_scores.items():
        key = score_alias_to_key(label, lens)
        entry = {
            "key": key or label,
            "stars": info["stars"],
            "val": info["val"],
        }
        if key:
            by_key[key] = entry
        else:
            unknown.append((label, entry))

    ordered: dict[str, dict] = {}
    for axis in lens.score_axes:
        if axis.key in by_key:
            ordered[axis.label] = by_key[axis.key]
    for label, entry in unknown:
        ordered[label] = entry
    return ordered


def parse_critique_text(critique_text: str, lens: str | None = None) -> dict:
    """
    AIが生成した講評テキスト（Phase 1 / Phase 2）を統一的にパース（解析）し、
    扱いやすい辞書データとして返す共通関数。
    """
    lens_def = get_lens(lens)
    data = {
        "title": "写真分析講評",
        "summary": "分析完了",
        "scores": {},
        "point_text": "光と質感が織りなす印象的な情景。",
        "body": "",
        "has_valid_phase1": False,
        "has_valid_phase2": False,
        "lens": lens_def.id,
        "score_disclaimer": lens_def.score_disclaimer,
    }

    if not critique_text:
        return data

    # 1. TITLE 抽出 (表記揺れ吸収)
    title_m = re.search(r"(?:##\s*)?■?\s*TITLE\s*[:：]\s*(.+)", critique_text, re.IGNORECASE)
    if title_m:
        data["title"] = title_m.group(1).strip()

    # 2. SUMMARY 抽出
    summary_m = re.search(r"(?:##\s*)?■?\s*SUMMARY\s*[:：]\s*(.+)", critique_text, re.IGNORECASE)
    if summary_m:
        data["summary"] = summary_m.group(1).strip()

    # 3. SCORES 抽出 → 正規化
    raw_scores: dict[str, dict] = {}
    for m in _SCORE_LINE.finditer(critique_text):
        label, stars, val = m.group(1).strip(), m.group(2), m.group(3)
        raw_scores[label] = {"stars": stars, "val": val}
    data["scores"] = _normalize_scores(raw_scores, lens_def)

    # 4. CRITIQUE_SUMMARY (講評要約) 抽出
    crit_sum_m = re.search(
        r"(?:##\s*)?■?\s*CRITIQUE_SUMMARY\s*[:：]\s*(.+)", critique_text, re.IGNORECASE
    )
    if crit_sum_m:
        data["point_text"] = crit_sum_m.group(1).strip()

    # 5. 本文 (【1】〜【7】) 抽出
    body_m = re.search(r"(##\s*【1[\s\S]*)", critique_text)
    if not body_m:
        body_m = re.search(r"(【1[\.\s][\s\S]*)", critique_text)
    if body_m:
        data["body"] = body_m.group(1).strip()

    # Phase 1 の必須項目（タイトルとスコア）が存在するかチェック
    if title_m and len(data["scores"]) > 0:
        data["has_valid_phase1"] = True

    data["has_valid_phase2"] = bool(data["body"])

    return data


def is_valid_phase2_content(critique_text: str) -> bool:
    """Phase 2 本文がパーサーまたは見出しパターンで検証できるか。"""
    if not critique_text or not critique_text.strip():
        return False
    parsed = parse_critique_text(critique_text)
    if parsed["has_valid_phase2"]:
        return True
    return bool(re.search(r"【1[\.\s]", critique_text))
