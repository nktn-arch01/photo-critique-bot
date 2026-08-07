from pathlib import Path

from scanner import extract_file_metadata

test_file = Path("test_input.jpg")

if test_file.exists():
    _, _, meta_block = extract_file_metadata(test_file)
    print("=== 全抽出データ (scanner.py) ===")
    print(meta_block)
else:
    print("テスト用画像 test_input.jpg が見つかりません。")
