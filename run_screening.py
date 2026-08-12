#!/usr/bin/env python3
"""スクリーニング CLI（講評バッチ analyze_folder / app_gui とは別導線）.

公式入口（Wave 3）。旧 ``run_shortlist.py`` は互換ラッパ。

Usage:
  python3 run_screening.py --dir /path/to/202608
  python3 run_screening.py --dir /path/to/20260810_京都旅行 --dry-run
  python3 run_screening.py --dir /path/to/202608 --stages m1
  python3 run_screening.py --dir /path/to/202608 --stages m1,m2,m3 --out-json /tmp/copy.json

監査ログは自動で {dir}/_lumina/sessions/{id}.json に保存される。
Ctrl+C で中断（可能な段境界・枚単位で停止）。
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

from screening_pipeline import PipelineConfig, PipelineProgress, ScreeningPipeline, parse_stages


def main() -> int:
    parser = argparse.ArgumentParser(description="Lumina Notes スクリーニング (M1→M2→M3)")
    parser.add_argument(
        "--dir",
        required=True,
        type=Path,
        help="月 YYYYMM またはイベント YYYYMMDD_名前 フォルダ",
    )
    parser.add_argument(
        "--stages",
        default="all",
        help="実行段: all または m1,m2,m3 のカンマ区切り",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="メタ書き込みなし（判定のみ）",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        help="結果 JSON の追加コピー先（本体は unit/_lumina/sessions/ に自動保存）",
    )
    parser.add_argument(
        "--no-session",
        action="store_true",
        help="_lumina/sessions への監査ログ保存を行わない",
    )
    args = parser.parse_args()

    target = args.dir
    if not target.is_dir():
        print(f"ディレクトリがありません: {target}", file=sys.stderr)
        return 2

    try:
        run_m1, run_m2, run_m3 = parse_stages(args.stages)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    def on_progress(p: PipelineProgress) -> None:
        extra = ""
        if p.current is not None and p.total is not None:
            extra = f" ({p.current}/{p.total})"
        print(f"[{p.stage}] {p.message}{extra}", flush=True)

    pipeline = ScreeningPipeline(
        PipelineConfig(
            write=not args.dry_run,
            run_m1=run_m1,
            run_m2=run_m2,
            run_m3=run_m3,
            persist_session=not args.no_session,
        ),
        on_progress=on_progress,
    )

    def _handle_sigint(signum, frame) -> None:  # noqa: ARG001
        print("\n中断要求を受け付けました。段の区切り／枚処理の直後に停止します…", flush=True)
        pipeline.request_cancel()

    signal.signal(signal.SIGINT, _handle_sigint)

    print("==========================================")
    print(" Lumina Notes スクリーニング")
    print(f" 対象: {target}")
    print(f" 段: {'m1' if run_m1 else ''}{' m2' if run_m2 else ''}{' m3' if run_m3 else ''}".strip())
    print(f" 書き込み: {'OFF (dry-run)' if args.dry_run else 'ON'}")
    print("==========================================")

    try:
        result = pipeline.run_on_dir(target)
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2

    print("------------------------------------------")
    print(f" status: {result.status}")
    print(f" session: {result.session_id}")
    if result.session_path:
        print(f" session_path: {result.session_path}")
    print(f" jpeg_count: {result.jpeg_count}")
    print(f" counts_hint: {result.counts_by_rating_hint()}")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
