import argparse
import sys
import traceback
from pathlib import Path
from scanner import scan_monthly_folder
from critique_engine import generate_critique
from log_manager import DesktopLogManager
from generate_critique_card import create_critique_card

def main():
    parser = argparse.ArgumentParser(description="月別フォルダ一括写真分析バッチ")
    parser.add_argument("--dir", required=True, help="対象の月別フォルダパス (例: ./202607)")
    args = parser.parse_args()

    target_dir = Path(args.dir)
    if not target_dir.exists() or not target_dir.is_dir():
        print(f"❌ ディレクトリが存在しません: {target_dir}")
        sys.exit(1)

    log_mgr = DesktopLogManager(target_dir)
    targets, skipped = scan_monthly_folder(target_dir, log_mgr)

    print(f"==========================================")
    print(f" 写真講評バッチ開始: {target_dir.name}")
    print(f"==========================================")
    print(f"[スキャン結果] 未処理: {len(targets)} 件 / スキップ(処理済み): {len(skipped)} 件\n")

    for idx, item in enumerate(targets, 1):
        print(f"------------------------------------------")
        print(f"[{idx}/{len(targets)}] 処理中: {item['name']}")
        print(f"------------------------------------------")
        
        try:
            # Step 1: AI講評の生成
            print("  [1/3] AI講評生成中 (CritiqueEngine)...")
            critique_text = generate_critique(
                image_path=item["path"],
                metadata=item["metadata"],
                dop_info=item["dop_info"], mode="full"
            )

            # Step 2: 講評カード画像 (PNG) の生成
            print("  [2/3] 講評カード画像生成中...")
            card_path = log_mgr.get_card_output_path(item["name"])
            create_critique_card(
                image_path=item["path"],
                critique_text=critique_text,
                output_card_path=card_path
            )

            # Step 3: Markdownノート & 月間/年間テキストログの保存 (メタデータ付き)
            print("  [3/3] Markdownノート書き出し & 月間/年間ログ集約...")
            log_mgr.save_analysis_result(
                file_name=item["name"],
                metadata_block=item["metadata_block"],
                critique_text=critique_text
            )
            print(f"  [SUCCESS] 完了: {item['name']}\n")

        except Exception as e:
            print(f"  ❌ 処理エラー ({item['name']}): {e}\n")
            traceback.print_exc()

    print(f"==========================================")
    print(f" バッチ完了")
    print(f"==========================================")

if __name__ == "__main__":
    main()
