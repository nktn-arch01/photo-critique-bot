"""critique_parser の回帰防止用ミニテスト（python test_critique_parser.py）。"""

from critique_parser import parse_critique_text, is_valid_phase2_content

PHASE1_SAMPLE = """
■TITLE: 試験タイトル
■SUMMARY: キャッチ
■SCORES:
・構図・構成  : ★★★☆☆ (3/5)
・光・色彩    : ★★★★☆ (4/5)
■CRITIQUE_SUMMARY: 要約文です。
"""

PHASE2_SAMPLE = """
## 【1. 情景・空気感とストーリー性】
本文1

## 【7. 自動タグ】
#tag
"""


def test_phase1():
    p = parse_critique_text(PHASE1_SAMPLE)
    assert p["has_valid_phase1"]
    assert p["title"] == "試験タイトル"
    assert len(p["scores"]) >= 2


def test_phase2():
    assert is_valid_phase2_content(PHASE2_SAMPLE)
    p = parse_critique_text(PHASE2_SAMPLE)
    assert p["has_valid_phase2"]
    assert "【1." in p["body"]


def test_processed_status_not_confused():
    """ファイル名部分一致の誤判定は log_manager 側（別テスト）。"""
    combined = PHASE1_SAMPLE + "\n---\n" + PHASE2_SAMPLE
    p = parse_critique_text(combined)
    assert p["has_valid_phase1"]
    assert p["has_valid_phase2"]


if __name__ == "__main__":
    test_phase1()
    test_phase2()
    test_processed_status_not_confused()
    print("test_critique_parser: OK")
