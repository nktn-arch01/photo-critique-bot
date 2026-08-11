#!/usr/bin/env python3
"""Mac 手動確認用の最小フィクスチャを作る.

Usage:
  python3 prepare_mac_manual_fixtures.py
  python3 prepare_mac_manual_fixtures.py --root ~/Desktop/LuminaManualCheck

作成物（運用方針どおり）:
  {root}/OM202608/                 短絡・月（XX 接頭辞）
  {root}/OM202608/OM20260815_旅行/ 短絡・イベント
  {root}/2026/202608/              Works 月（痕跡）
  {root}/2026/202608/_subdir_only/ L4 案内確認用（直下対象外）
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def _jpeg(path: Path, color: tuple[int, int, int], label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (320, 240), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle((20, 20, 300, 220), outline=(255, 255, 255), width=3)
    draw.text((40, 100), label, fill=(255, 255, 255))
    img.save(path, "JPEG", quality=90)


def prepare(root: Path) -> None:
    month = root / "OM202608"
    event = month / "OM20260815_旅行"
    works = root / "2026" / "202608"
    buried = works / "_subdir_only"

    _jpeg(month / "sample_a.jpg", (30, 60, 90), "OM month A")
    _jpeg(month / "sample_b.jpg", (90, 40, 40), "OM month B")
    _jpeg(month / "sample_c.jpg", (40, 90, 50), "OM month C")
    _jpeg(event / "trip_a.jpg", (70, 50, 110), "event A")
    _jpeg(event / "trip_b.jpg", (20, 80, 80), "event B")

    _jpeg(works / "W1_dev.jpg", (50, 50, 50), "works W1_dev")
    _jpeg(works / "W2.jpg", (80, 80, 30), "works W2 sooc")
    _jpeg(buried / "buried.jpg", (10, 10, 10), "subdir only")

    print("作成完了:")
    print(f"  短絡・月:     {month}")
    print(f"  短絡・イベント: {event}")
    print(f"  Works 月:     {works}")
    print(f"  L4 サブ:     {buried}")
    print()
    print("次: LuminaShortlist.command を起動し、docs/R1A_MAC_MANUAL_CHECKLIST.md を順に確認。")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mac 手動確認用フィクスチャ作成")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home() / "Desktop" / "LuminaManualCheck",
        help="出力ルート（既定: ~/Desktop/LuminaManualCheck）",
    )
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    prepare(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
