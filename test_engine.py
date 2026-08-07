import os
from pathlib import Path

from critique_engine import generate_critique_openai
from critique_parser import parse_critique_text
from scanner import extract_file_metadata

if not os.environ.get("OPENAI_API_KEY") and not (Path.home() / ".openai_api_key").exists():
    print("[-] OPENAI_API_KEY または ~/.openai_api_key が未設定です。")
    raise SystemExit(1)

test_file = Path("test_input.jpg")
if not test_file.exists():
    print("[-] test_input.jpg が見つかりません。")
    raise SystemExit(1)

print("=== OpenAI compact 単体テスト (Phase 1) ===")

exif_meta, dop_info, _ = extract_file_metadata(test_file)
critique_text = generate_critique_openai(
    test_file,
    metadata=exif_meta,
    dop_info=dop_info,
    mode="compact",
)
parsed = parse_critique_text(critique_text)

print("\n[+] パース完了")
print("----------------------------------------")
print("■ TITLE   :", parsed["title"])
print("■ SUMMARY :", parsed["summary"])
print("■ SCORES  :", parsed["scores"])
print("■ SUMMARY :", parsed["point_text"][:120])
print("----------------------------------------")
