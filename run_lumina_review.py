#!/usr/bin/env python3
"""Works Lumina Review CLI（スクリーニング run_screening / 講評 analyze_folder とは別導線）.

公式入口（Wave 3）。旧 ``run_trace_works.py`` 互換ラッパは削除済み。

Usage:
  python3 run_lumina_review.py --dir /path/to/Works/202608
  python3 run_lumina_review.py --dir /path/to/Works --force
  python3 run_lumina_review.py --dir /path/to/Works --mode compact --theme light

本アプリは Works へファイルをコピーしません。DxO 等が置いた JPEG を読むだけです。
同一 stem では ``{stem}_dev.jpg`` を優先します。
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from card_theme import DEFAULT_CARD_THEME
from lumina_review import ReviewConfig, ReviewProgress, LuminaReviewRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Lumina Notes Works Lumina Review（カード／ノート／ログ）")
    parser.add_argument(
        "--dir",
        required=True,
        type=Path,
        help="Works（または確定 JPEG が入ったフォルダ）。コピーはしません。",
    )
    parser.add_argument(
        "--mode",
        default="full",
        choices=["compact", "full"],
        help="講評モード（既定: full）",
    )
    parser.add_argument(
        "--theme",
        default=DEFAULT_CARD_THEME,
        choices=["dark", "light"],
        help="カード背景テーマ",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="処理済みでも上書き",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        help="結果 JSON の出力先",
    )
    args = parser.parse_args()

    target = args.dir
    if not target.is_dir():
        print(f"ディレクトリがありません: {target}", file=sys.stderr)
        return 2

    def on_progress(p: ReviewProgress) -> None:
        extra = ""
        if p.current is not None and p.total is not None:
            extra = f" ({p.current}/{p.total})"
        print(f"[review/{p.stage}] {p.message}{extra}", flush=True)

    runner = LuminaReviewRunner(
        ReviewConfig(
            mode=args.mode,
            force_overwrite=args.force,
            card_theme=args.theme,
            pixel_priority=True,
        ),
        on_progress=on_progress,
    )

    def _handle_sigint(signum, frame) -> None:  # noqa: ARG001
        print("\n中断要求を受け付けました。現在の枚の直後に停止します…", flush=True)
        runner.request_cancel()

    signal.signal(signal.SIGINT, _handle_sigint)

    print("==========================================")
    print(" Lumina Notes Works Lumina Review")
    print(f" 対象: {target}")
    print(f" mode: {args.mode} / theme: {args.theme}")
    print(f" overwrite: {'ON' if args.force else 'OFF'}")
    print(" コピー: しない（既存 JPEG のみ）")
    print("==========================================")

    result = runner.run(target)

    print("------------------------------------------")
    print(f" status: {result.status}")
    print(f" targets: {result.targets_found}")
    print(f" processed: {result.processed}")
    print(f" skipped: {result.skipped}")
    print(f" errors: {result.errors}")
    if result.error:
        print(f" error: {result.error}")
    print("==========================================")

    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {args.out_json}")

    if result.status == "cancelled":
        return 130
    if result.status == "failed":
        return 1
    if result.errors and result.processed == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
