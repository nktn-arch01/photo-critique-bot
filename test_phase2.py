import shutil
from pathlib import Path

from log_manager import DesktopLogManager
from scanner import scan_monthly_folder

base_dir = Path("./test_storage/DxO folder")
month_dir = base_dir / "2026" / "202607"
month_dir.mkdir(parents=True, exist_ok=True)

sample_img = Path("test_input.jpg")
sample_dop = Path("test_input.dop")

if sample_img.exists():
    shutil.copy(sample_img, month_dir / "P7201882_DxO.jpg")
if sample_dop.exists():
    shutil.copy(sample_dop, month_dir / "P7201882_DxO.dop")

print("=== スキャン ＆ ログ機能テスト (DesktopLogManager) ===")

log_mgr = DesktopLogManager(target_dir=month_dir)
targets, skipped = scan_monthly_folder(month_dir, log_mgr)

print(f"検出対象画像数: {len(targets)} 件")
print(f"スキップ画像数: {len(skipped)} 件")

if targets:
    item = targets[0]
    print(f"\n[スキャン成功] 対象ファイル: {item['name']}")
    print("--- 保持されたメタデータブロック ---")
    print(item["metadata_block"])

    print("\n--- 書き込みテスト実行 ---")
    dummy_critique = "■TITLE: テスト講評\n■SUMMARY: 概要テスト\n■SCORES:\n・構図・構成  : ★★★☆☆ (3/5)\n\n■CRITIQUE_SUMMARY: テスト要約"
    log_mgr.save_analysis_result(item["name"], item["metadata_block"], dummy_critique)
    print(f"[+] ノート保存: {log_mgr.notes_dir / (item['stem'] + '.md')}")

    targets_2, skipped_2 = scan_monthly_folder(month_dir, log_mgr)
    print(f"\n[2回目スキャン] 対象: {len(targets_2)} 件, スキップ: {len(skipped_2)} 件")
