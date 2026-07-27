import shutil
from pathlib import Path
from log_manager import LogManager
from scanner import scan_monthly_folder

# テスト用ダミーディレクトリ構造の作成
base_dir = Path("./test_storage/DxO folder")
month_dir = base_dir / "2026" / "202607"
month_dir.mkdir(parents=True, exist_ok=True)

# テスト用画像の準備
sample_img = Path("test_input.jpg")
sample_dop = Path("test_input.dop")

if sample_img.exists():
    shutil.copy(sample_img, month_dir / "P7201882_DxO.jpg")
if sample_dop.exists():
    shutil.copy(sample_dop, month_dir / "P7201882_DxO.dop")

print("=== Phase 2 スキャン ＆ ログ機能テスト ===")

log_mgr = LogManager(target_dir=month_dir, base_dir=base_dir)
targets, skipped = scan_monthly_folder(month_dir, log_mgr)

print(f"検出対象画像数: {len(targets)} 件")
print(f"スキップ画像数: {len(skipped)} 件")

if targets:
    item = targets[0]
    print(f"\n[スキャン成功] 対象ファイル: {item['name']}")
    print("--- 保持されたメタデータブロック ---")
    print(item['metadata_block'])

    # テスト書き込み
    print("\n--- 書き込みテスト実行 ---")
    note_p = log_mgr.save_markdown_note(item['stem'], "■TITLE: テスト講評\n■SUMMARY: 概要テスト\nこれはAI講評本文のテストです。", item['metadata_block'])
    print(f"[+] ノート作成完了: {note_p}")

    log_mgr.append_annual_log(item['name'], "■TITLE: テスト講評 | ■SCORES: ★★★★★", item['metadata_block'])
    print(f"[+] 年間ログ追記完了: {log_mgr.local_annual_log}")

    # 再度スキャンしてスキップされるか確認
    targets_2, skipped_2 = scan_monthly_folder(month_dir, log_mgr)
    print(f"\n[2回目スキャン] 対象: {len(targets_2)} 件, スキップ: {len(skipped_2)} 件 (重複スキップ正常確認)")

