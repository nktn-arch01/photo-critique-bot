from pathlib import Path
from metadata_extractor import extract_jpeg_metadata, format_metadata_block

test_file = Path("test_input.jpg")

if test_file.exists():
    data = extract_jpeg_metadata(test_file)
    print("=== 全抽出データ ===")
    print(format_metadata_block(data))
else:
    print("テスト用画像 test_input.jpg が見つかりません。")
