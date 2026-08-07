import re

def parse_critique_text(critique_text: str) -> dict:
    """
    AIが生成した講評テキスト（Phase 1 / Phase 2）を統一的にパース（解析）し、
    扱いやすい辞書データとして返す共通関数。
    """
    data = {
        "title": "写真分析講評",
        "summary": "分析完了",
        "scores": {},
        "point_text": "光と質感が織りなす印象的な情景。",
        "body": "",
        "has_valid_phase1": False,
        "has_valid_phase2": False,
    }

    if not critique_text:
        return data

    # 1. TITLE 抽出 (表記揺れ吸収)
    title_m = re.search(r'(?:##\s*)?■?\s*TITLE\s*[:：]\s*(.+)', critique_text, re.IGNORECASE)
    if title_m:
        data["title"] = title_m.group(1).strip()

    # 2. SUMMARY 抽出
    summary_m = re.search(r'(?:##\s*)?■?\s*SUMMARY\s*[:：]\s*(.+)', critique_text, re.IGNORECASE)
    if summary_m:
        data["summary"] = summary_m.group(1).strip()

    # 3. SCORES 抽出 (全角・半角カッコやスラッシュの表記揺れに対応)
    score_pattern = re.compile(r'・\s*([^:\s：]+)\s*[:：]\s*([★☆]+)\s*[\(（]\s*([\d\.]+)\s*[/／]\s*5\s*[\)）]')
    for m in score_pattern.finditer(critique_text):
        label, stars, val = m.group(1), m.group(2), m.group(3)
        data["scores"][label] = {"stars": stars, "val": val}

    # 4. CRITIQUE_SUMMARY (講評要約) 抽出
    crit_sum_m = re.search(r'(?:##\s*)?■?\s*CRITIQUE_SUMMARY\s*[:：]\s*(.+)', critique_text, re.IGNORECASE)
    if crit_sum_m:
        data["point_text"] = crit_sum_m.group(1).strip()

    # 5. 本文 (【1】〜【7】) 抽出
    body_m = re.search(r'(##\s*【1[\s\S]*)', critique_text)
    if not body_m:
        body_m = re.search(r'(【1[\.\s][\s\S]*)', critique_text)
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