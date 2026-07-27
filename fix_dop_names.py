import sys
from pathlib import Path

def fix_dop_filenames(target_dir_str: str):
    target_dir = Path(target_dir_str)
    if not target_dir.exists() or not target_dir.is_dir():
        print("エラー: 有効なフォルダではありません。")
        return

    # 1. 隠しファイル（._ で始まるファイル等）を除外してJPGをスキャン
    jpg_files = [
        f for f in target_dir.iterdir() 
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in [".jpg", ".jpeg"]
    ]
    
    prefix_map = {}
    for jpg in jpg_files:
        if len(jpg.name) >= 8:
            prefix = jpg.name[:8]
            prefix_map[prefix] = jpg.stem

    # 2. 隠しファイルを除外して.dopをスキャン
    dop_files = [
        f for f in target_dir.iterdir() 
        if f.is_file() and not f.name.startswith(".") and f.name.lower().endswith(".dop")
    ]
    
    renamed_count = 0
    error_count = 0

    for dop in dop_files:
        if len(dop.name) >= 8:
            prefix = dop.name[:8]
            if prefix in prefix_map:
                new_stem = prefix_map[prefix]
                new_dop_path = dop.parent / f"{new_stem}.dop"
                
                if dop != new_dop_path:
                    try:
                        dop.rename(new_dop_path)
                        renamed_count += 1
                    except Exception as e:
                        print(f"⚠️ スキップ ({dop.name}): {e}")
                        error_count += 1

    print(f"対象フォルダ: {target_dir.name}\n書き換え完了: {renamed_count} 件 (エラー/スキップ: {error_count} 件)")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        fix_dop_filenames(sys.argv[1])
    else:
        print("フォルダパスが指定されていません。")
