#!/usr/bin/env python3
"""JPEG Rating / Description の書き込み・再読取ラウンドトリップ検証.

DxO PhotoLab 上の見え方はオーナー手動（docs/IPTC_SYNC_VERIFICATION.md）。
このスクリプトは exiftool によるファイル側の可読・可写を確認する。

Usage:
  python3 scripts/iptc_sync_verify.py
  python3 scripts/iptc_sync_verify.py --jpeg /path/to/file.jpg --rating 3 --description '[M2] test'
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# R1′-A で短絡バッチが書く想定のタグ一式（単一ソース候補）
WRITE_RATING_TAGS = (
    "-Rating={rating}",
    "-XMP:Rating={rating}",
    "-RatingPercent={percent}",
)
WRITE_DESCRIPTION_TAGS = (
    "-ImageDescription={desc}",
    "-XMP-dc:Description={desc}",
    "-IPTC:Caption-Abstract={desc}",
)

READ_TAGS = (
    "Rating",
    "XMP:Rating",
    "RatingPercent",
    "ImageDescription",
    "XMP-dc:Description",
    "IPTC:Caption-Abstract",
)


def require_exiftool() -> str:
    path = shutil.which("exiftool")
    if not path:
        raise SystemExit("exiftool が見つかりません。インストールしてから再実行してください。")
    return path


def rating_to_percent(rating: int) -> int:
    """0–5 → ざっくり RatingPercent（Microsoft 互換の目安）。"""
    return max(0, min(100, int(round(rating * 20))))


def write_rating_description(jpeg: Path, rating: int, description: str) -> None:
    exiftool = require_exiftool()
    percent = rating_to_percent(rating)
    cmd = [exiftool, "-overwrite_original"]
    for tmpl in WRITE_RATING_TAGS:
        cmd.append(tmpl.format(rating=rating, percent=percent))
    for tmpl in WRITE_DESCRIPTION_TAGS:
        cmd.append(tmpl.format(desc=description))
    cmd.append(str(jpeg))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"exiftool write failed: {proc.stderr or proc.stdout}")


def read_tags(jpeg: Path) -> dict[str, str]:
    exiftool = require_exiftool()
    args = [exiftool, "-json", "-s"]
    for tag in READ_TAGS:
        args.append(f"-{tag}")
    args.append(str(jpeg))
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"exiftool read failed: {proc.stderr or proc.stdout}")
    data = json.loads(proc.stdout)[0]
    data.pop("SourceFile", None)
    return {k: str(v) for k, v in data.items()}


def make_sample_jpeg(path: Path) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (96, 64), (30, 90, 140)).save(path, "JPEG", quality=90)


def verify_roundtrip(jpeg: Path, rating: int, description: str) -> dict:
    write_rating_description(jpeg, rating, description)
    got = read_tags(jpeg)
    rating_ok = any(
        got.get(k) == str(rating) for k in ("Rating", "XMP:Rating") if got.get(k) is not None
    ) or got.get("Rating") == str(rating)
    # exiftool -json may collapse to Rating only
    if not rating_ok and got.get("Rating") == str(rating):
        rating_ok = True
    desc_values = [
        got.get("ImageDescription"),
        got.get("Description"),
        got.get("Caption-Abstract"),
    ]
    desc_ok = any(v == description for v in desc_values if v)
    return {
        "jpeg": str(jpeg),
        "expected_rating": rating,
        "expected_description": description,
        "read_tags": got,
        "rating_ok": bool(rating_ok or got.get("Rating") == str(rating)),
        "description_ok": desc_ok,
        "passed": bool((rating_ok or got.get("Rating") == str(rating)) and desc_ok),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jpeg", type=Path, help="既存 JPEG。省略時は一時サンプルを作成")
    parser.add_argument("--rating", type=int, default=3, choices=range(0, 6))
    parser.add_argument(
        "--description",
        default="[M2] IPTC sync verify\n[M3] diversity note",
        help="書き込む説明文",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("eval/iptc_sync/roundtrip_result.json"),
        help="結果 JSON の出力先",
    )
    parser.add_argument(
        "--prepare-dxo",
        action="store_true",
        help=(
            "DxO 手動検証用に、書き込み済み JPEG を eval/iptc_sync/dxo_probe/ に残す。"
            "--jpeg 指定時はそのコピー、未指定時はサンプルを作成する。"
        ),
    )
    args = parser.parse_args()

    require_exiftool()

    tmp_dir = None
    prepare_dir = Path("eval/iptc_sync/dxo_probe")

    if args.prepare_dxo:
        prepare_dir.mkdir(parents=True, exist_ok=True)
        if args.jpeg:
            if not args.jpeg.is_file():
                print(f"file not found: {args.jpeg}", file=sys.stderr)
                return 2
            jpeg = prepare_dir / args.jpeg.name
            shutil.copy2(args.jpeg, jpeg)
        else:
            jpeg = prepare_dir / "dxo_probe_sample.jpg"
            make_sample_jpeg(jpeg)
        result = verify_roundtrip(jpeg, args.rating, args.description)
        args.out_json = Path("eval/iptc_sync/dxo_prepare_result.json")
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"\nWrote {args.out_json}")
        print(f"\n=== DxO で開くフォルダ ===\n{jpeg.resolve().parent}")
        print(f"対象ファイル: {jpeg.resolve()}")
        print(f"期待 Rating: {args.rating}")
        print(f"期待 説明:\n{args.description}")
        print(
            "\n次: docs/IPTC_SYNC_VERIFICATION.md の「B. DxO 手順（詳細）」に進んでください。"
        )
        return 0 if result["passed"] else 1

    if args.jpeg:
        jpeg = args.jpeg
        if not jpeg.is_file():
            print(f"file not found: {jpeg}", file=sys.stderr)
            return 2
        # 破壊を避けるためコピーして検証
        tmp_dir = tempfile.TemporaryDirectory(prefix="iptc_sync_")
        work = Path(tmp_dir.name) / jpeg.name
        shutil.copy2(jpeg, work)
        jpeg = work
    else:
        out_dir = Path("eval/iptc_sync")
        out_dir.mkdir(parents=True, exist_ok=True)
        jpeg = out_dir / "roundtrip_sample.jpg"
        make_sample_jpeg(jpeg)

    result = verify_roundtrip(jpeg, args.rating, args.description)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nWrote {args.out_json}")
    if tmp_dir:
        tmp_dir.cleanup()

    if not result["passed"]:
        print("ROUNDTRIP FAILED", file=sys.stderr)
        return 1
    print("ROUNDTRIP PASSED (file-level). DxO UI confirmation is still owner-manual.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
