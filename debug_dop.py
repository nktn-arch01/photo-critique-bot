import re
from pathlib import Path

# test_input.dop または フォルダ内の .dop ファイルを探す
dop_path = Path("test_input.dop")
if not dop_path.exists():
    dop_files = list(Path(".").glob("*.dop"))
    if dop_files:
        dop_path = dop_files[0]

if dop_path.exists():
    print(f"=== DOPファイル検出: {dop_path.name} ===")
    content = dop_path.read_text(encoding="utf-8", errors="ignore")

    # 1. IPTCブロックの抽出
    print("--- IPTC ブロックの内容 ---")
    iptc_matches = re.findall(r'IPTC\s*=\s*\{([^}]*)\}', content, re.IGNORECASE)
    if iptc_matches:
        for m in iptc_matches:
            print(m.strip())
    else:
        print("  IPTCブロックなし")

    # 2. テキストが設定されているキーの抽出
    print("\n--- 文字列が設定されている主要フィールド ---")
    ignore_keys = {'Software', 'CafID', 'Uuid', 'Name', 'ColorLookupPath', 'OutputICCProfilePath', 'WatermarkImagePath', 'AppliedPresetDisplayName', 'AppliedPresetUniqueName'}
    
    found_any = False
    for match in re.finditer(r'(\w+)\s*=\s*"([^"]+)"', content):
        key, val = match.groups()
        if key not in ignore_keys and val.strip():
            print(f"  [{key}]: {val}")
            found_any = True

    if not found_any:
        print("  テキスト（キャプション・説明等）が空です。")

else:
    print("DOPファイルが見つかりませんでした。")
