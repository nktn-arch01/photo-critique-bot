#!/usr/bin/env python3
"""Phase D 応答評価ランナー（実 API）。

使い方:
  python3 scripts/phase_d_eval.py --mode both
  python3 scripts/phase_d_eval.py --mode compact --ids P01,P02,P03,P04
  python3 scripts/phase_d_eval.py --dry-run   # 写真の有無と manifest のみ確認
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from critique_engine import generate_critique_openai
from critique_lens import DEFAULT_LENS, get_lens
from critique_parser import parse_critique_text
from generate_critique_card import create_critique_card
from prompt_contracts import PHASE2_FORBID_FIX, PHASE_OUTPUT_TIME_BAN
from scanner import SUPPORTED_IMAGE_SUFFIXES, extract_file_metadata

EVAL_DIR = ROOT / "eval" / "phase_d"
MANIFEST_PATH = EVAL_DIR / "manifest.json"
IMAGES_DIR = EVAL_DIR / "images"
OUT_ROOT = EVAL_DIR / "out"

# 正本は prompt_contracts（オフライン契約と共有）
TIME_BAN = PHASE_OUTPUT_TIME_BAN
FORBID_FIX = PHASE2_FORBID_FIX
CANONICAL_LABELS = [a.label for a in get_lens(DEFAULT_LENS).score_axes]


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _resolve_image(slot: dict) -> Path | None:
    name = slot["filename"]
    stem = Path(name).stem
    direct = IMAGES_DIR / name
    if direct.exists():
        return direct
    for p in IMAGES_DIR.iterdir() if IMAGES_DIR.exists() else []:
        if not p.is_file():
            continue
        if p.stem == stem or p.stem.startswith(slot["id"]):
            if p.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
                return p
    return None


def _auto_checks(critique: str, mode: str) -> dict[str, dict]:
    parsed = parse_critique_text(critique, lens=DEFAULT_LENS)
    labels = list(parsed["scores"].keys())
    text_for_ban = "\n".join(
        [
            parsed.get("title") or "",
            parsed.get("summary") or "",
            parsed.get("point_text") or "",
            parsed.get("body") or "",
            critique,
        ]
    )

    axis_ok = all(lbl in labels for lbl in CANONICAL_LABELS) if mode == "compact" or "■SCORES" in critique else (
        len([k for k in labels if k in CANONICAL_LABELS]) >= 3
    )
    # Phase1 部分を優先して軸チェック
    phase1 = critique.split("\n---\n", 1)[0]
    p1 = parse_critique_text(phase1, lens=DEFAULT_LENS)
    axis_ok = all(lbl in p1["scores"] for lbl in CANONICAL_LABELS)

    hit_time = [w for w in TIME_BAN if w in text_for_ban]
    body = parsed.get("body") or ""
    hit_fix = [w for w in FORBID_FIX if w in body] if mode == "full" else []

    title = p1.get("title") or ""
    # 日本語想定: 文字数（空白除く）
    title_len = len(re.sub(r"\s+", "", title))

    checks = {
        "D-axis-names": {
            "pass": axis_ok,
            "detail": f"scores={labels}",
        },
        "D-time-ban": {
            "pass": not hit_time,
            "detail": f"hits={hit_time or 'none'}",
        },
        "D-title-len": {
            "pass": 1 <= title_len <= 15,
            "detail": f"title={title!r} len={title_len}",
        },
        "D-phase1-struct": {
            "pass": bool(p1.get("has_valid_phase1")),
            "detail": f"has_valid_phase1={p1.get('has_valid_phase1')}",
        },
    }
    if mode == "full":
        checks["D-forbid-fix"] = {
            "pass": not hit_fix,
            "detail": f"hits={hit_fix or 'none'}",
        }
        checks["D-phase2-struct"] = {
            "pass": bool(parsed.get("has_valid_phase2")),
            "detail": f"has_valid_phase2={parsed.get('has_valid_phase2')}",
        }
    return checks


def _human_checklist(mode: str, category: str) -> list[str]:
    rows = [
        "D-role（伴走・編集者口調）",
        "D-score-meaning（アンテナ／純度）",
        "D-title（仮説的・非ラベル）",
        "D-summary（無意識の意図への仮説）",
    ]
    if category == "person":
        rows.append("D-person（しぐさ・視線・物語）")
    else:
        rows.append("D-person（N/A 可）")
    if mode == "full":
        rows.extend(
            [
                "D-exif（心の揺れ／曖昧さの肯定）",
                "D-advice（問いかけで循環）",
            ]
        )
    return rows


def _write_report(out_dir: Path, rows: list[dict], dry_run: bool) -> Path:
    lines = [
        "# Phase D 評価レポート",
        "",
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"- lens: `{DEFAULT_LENS}`",
        f"- dry_run: {dry_run}",
        "",
        "## 合否サマリ（自動）",
        "",
        "| ID | mode | auto_all_pass | notes |",
        "|----|------|---------------|-------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r.get('mode', '-')} | {r.get('auto_all_pass', 'n/a')} | {r.get('status', '')} |"
        )

    lines.extend(["", "## 各スロット", ""])
    for r in rows:
        lines.append(f"### {r['id']} — {r['category']}")
        lines.append("")
        lines.append(f"- filename: `{r.get('filename')}`")
        lines.append(f"- image: `{r.get('image_path', 'MISSING')}`")
        lines.append(f"- intent: {r.get('intent', '')}")
        if r.get("status") == "missing_image":
            lines.append("- **写真未配置**")
            lines.append("")
            continue
        if dry_run:
            lines.append("- dry-run: 写真あり（API 未呼び出し）")
            lines.append("")
            continue
        lines.append(f"- mode: `{r['mode']}`")
        lines.append(f"- critique: `{r.get('critique_file', '')}`")
        lines.append(f"- card: `{r.get('card_file', '')}`")
        lines.append("")
        lines.append("#### 自動チェック")
        lines.append("")
        lines.append("| ID | PASS | detail |")
        lines.append("|----|------|--------|")
        for cid, c in r.get("auto", {}).items():
            lines.append(f"| {cid} | {'PASS' if c['pass'] else 'FAIL'} | {c['detail']} |")
        lines.append("")
        lines.append("#### 人手チェック（記入用）")
        lines.append("")
        for h in r.get("human", []):
            lines.append(f"- [ ] PASS / [ ] FAIL — {h}")
        lines.append("")
        title = r.get("title", "")
        summary = r.get("summary", "")
        lines.append(f"- TITLE: {title}")
        lines.append(f"- SUMMARY: {summary}")
        lines.append("")

    lines.extend(
        [
            "## 判定メモ",
            "",
            "- 合格ライン案: 評価枚数の 75% 以上が auto_all_pass=True かつ人手欠格ゼロ",
            "- 不合格時: docs/PHASE_D_EVAL.md の「不合格時の戻し方」へ",
            "",
        ]
    )
    path = out_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase D evaluation runner")
    parser.add_argument("--mode", choices=["compact", "full", "both"], default="both")
    parser.add_argument("--ids", default="", help="Comma-separated slot ids (default: all present)")
    parser.add_argument("--dry-run", action="store_true", help="Check images/manifest only")
    parser.add_argument("--required-only", action="store_true", help="Only required slots")
    args = parser.parse_args()

    manifest = _load_manifest()
    slots = manifest["slots"]
    if args.required_only:
        slots = [s for s in slots if s.get("required")]
    if args.ids.strip():
        want = {x.strip() for x in args.ids.split(",") if x.strip()}
        slots = [s for s in slots if s["id"] in want]

    if not slots:
        print("No slots selected.", file=sys.stderr)
        return 2

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = OUT_ROOT / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    modes: list[str]
    if args.mode == "both":
        modes = ["compact", "full"]
    else:
        modes = [args.mode]

    rows: list[dict] = []
    missing_required = []

    for slot in slots:
        image = _resolve_image(slot)
        base = {
            "id": slot["id"],
            "category": slot["category"],
            "filename": slot["filename"],
            "intent": slot.get("intent", ""),
            "image_path": str(image) if image else "",
        }
        if image is None:
            base["status"] = "missing_image"
            rows.append(base)
            if slot.get("required"):
                missing_required.append(slot["id"])
            continue

        if args.dry_run:
            base["status"] = "ready"
            rows.append(base)
            continue

        # preferred mode: if both, run preferred first then the other if listed
        run_modes = modes
        if args.mode == "both" and slot.get("preferred_mode") in modes:
            # still run all requested modes; order preferred first
            run_modes = [slot["preferred_mode"]] + [m for m in modes if m != slot["preferred_mode"]]

        for mode in run_modes:
            print(f"[{slot['id']}] mode={mode} image={image.name}", flush=True)
            metadata, dop_info, _metadata_block = extract_file_metadata(image)
            # manifest intent を評価用に優先注入
            if slot.get("intent"):
                metadata = {**(metadata or {}), "user_intent": slot["intent"]}

            critique = generate_critique_openai(
                image_path=image,
                metadata=metadata,
                dop_info=dop_info,
                mode=mode,
                lens=DEFAULT_LENS,
            )
            parsed = parse_critique_text(critique, lens=DEFAULT_LENS)
            auto = _auto_checks(critique, mode)
            auto_all = all(c["pass"] for c in auto.values())

            crit_path = out_dir / f"{slot['id']}_{mode}_critique.txt"
            card_path = out_dir / f"{slot['id']}_{mode}_card.png"
            crit_path.write_text(critique, encoding="utf-8")
            create_critique_card(image, critique, card_path, lens=DEFAULT_LENS)

            rows.append(
                {
                    **base,
                    "mode": mode,
                    "status": "ok",
                    "auto": auto,
                    "auto_all_pass": auto_all,
                    "human": _human_checklist(mode, slot["category"]),
                    "title": parsed.get("title"),
                    "summary": parsed.get("summary"),
                    "critique_file": str(crit_path.relative_to(ROOT)),
                    "card_file": str(card_path.relative_to(ROOT)),
                }
            )

    report = _write_report(out_dir, rows, dry_run=args.dry_run)
    print(f"Report: {report}")

    if missing_required:
        print(f"Missing required images: {', '.join(missing_required)}", file=sys.stderr)
        print(f"Place files under: {IMAGES_DIR}", file=sys.stderr)
        return 1 if not args.dry_run else 1

    if args.dry_run:
        ready = sum(1 for r in rows if r.get("status") == "ready")
        print(f"Dry-run OK: {ready}/{len(rows)} images ready under {IMAGES_DIR}")
        return 0 if ready == len(rows) else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
