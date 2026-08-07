"""
API キー・ネットワーク不要の回帰テスト一式。
push 前: python3 test_offline_suite.py
"""

from pathlib import Path
import tempfile

from critique_parser import parse_critique_text, is_valid_phase2_content
from line_messaging import split_full_critique_for_line
from log_manager import DesktopLogManager
from privacy_utils import storage_path_from_card_url

PHASE1_SAMPLE = """
■TITLE: 試験タイトル
■SUMMARY: キャッチ
■SCORES:
・構図・構成  : ★★★☆☆ (3/5)
・光・色彩    : ★★★★☆ (4/5)
■CRITIQUE_SUMMARY: 要約文です。
"""

PHASE2_SAMPLE = """
## 【1. 情景】
one
## 【4. EXIF】
four
## 【6. SNS】
six
## 【7. タグ】
#t
"""


def test_parser_phase1():
    p = parse_critique_text(PHASE1_SAMPLE)
    assert p["has_valid_phase1"]
    assert p["title"] == "試験タイトル"
    assert len(p["scores"]) >= 2


def test_parser_phase2():
    assert is_valid_phase2_content(PHASE2_SAMPLE)
    p = parse_critique_text(PHASE2_SAMPLE)
    assert p["has_valid_phase2"]


def test_log_manager_processed_filename():
    td = Path(tempfile.mkdtemp())
    mgr = DesktopLogManager(td)
    mgr.status_file_path.write_text(
        "[PROCESSED] 2026-01-01 12:00:00 P1234.jpg\n"
        "[PROCESSED] 2026-01-01 12:00:01 P123.jpg\n",
        encoding="utf-8",
    )
    assert mgr.is_processed("P123.jpg") is True
    assert mgr.is_processed("P1234.jpg") is True
    assert mgr.is_processed("P12.jpg") is False


def test_line_full_split_four_parts():
    combined = PHASE1_SAMPLE + "\n---\n" + PHASE2_SAMPLE
    parts = split_full_critique_for_line(combined)
    assert len(parts) == 4
    assert "■TITLE" in parts[0]
    assert parts[1].startswith("## 【1.")
    assert "## 【4." in parts[2]
    assert parts[3].startswith("## 【6.")


def test_storage_path_from_card_url():
    pub = "https://xxx.supabase.co/storage/v1/object/public/critique-cards/abc123/msg_card.png"
    assert storage_path_from_card_url(pub) == "abc123/msg_card.png"
    signed = (
        "https://xxx.supabase.co/storage/v1/object/sign/critique-cards/"
        "abc123/msg_card.png?token=eyJ"
    )
    assert storage_path_from_card_url(signed) == "abc123/msg_card.png"
    assert storage_path_from_card_url("") is None


def run_all():
    test_parser_phase1()
    test_parser_phase2()
    test_log_manager_processed_filename()
    test_line_full_split_four_parts()
    test_storage_path_from_card_url()
    print("test_offline_suite: OK")


if __name__ == "__main__":
    run_all()
