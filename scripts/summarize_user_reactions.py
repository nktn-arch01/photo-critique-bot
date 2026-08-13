#!/usr/bin/env python3
"""LINE user_reaction（いいね／もう少し／いまいち）を集計する（Q5）。

Supabase の Table Editor から critique_logs を JSON/CSV エクスポートして渡す。
API キー不要。プロンプトは自動変更しません。

使い方:
  python3 scripts/summarize_user_reactions.py --input eval/fixtures_q5/sample_reactions.json
  python3 scripts/summarize_user_reactions.py --input dump.csv --md
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from line_reactions import REACTION_VALUES, parse_reaction_label

REACTION_LABELS = {
    "good": "👍 いいね",
    "mixed": "💭 もう少し",
    "weak": "😐 いまいち",
}


def _normalize_reaction(raw: object) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text in REACTION_VALUES:
        return text
    return parse_reaction_label(text)


def _load_rows(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "rows" in data:
            data = data["rows"]
        if not isinstance(data, list):
            raise SystemExit("JSON must be an array of objects (or {rows:[...]})")
        return [r for r in data if isinstance(r, dict)]
    if suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    raise SystemExit(f"unsupported input type: {suffix} (use .json or .csv)")


def summarize(rows: list[dict], *, weak_samples: int = 8) -> dict:
    counts: Counter[str] = Counter()
    missing = 0
    weak_titles: list[dict] = []
    mixed_titles: list[dict] = []

    for row in rows:
        key = _normalize_reaction(
            row.get("user_reaction") or row.get("reaction") or row.get("反応")
        )
        if key is None:
            missing += 1
            continue
        counts[key] += 1
        item = {
            "title": row.get("title") or "",
            "critique_summary": (
                row.get("critique_summary")
                or row.get("CRITIQUE_SUMMARY")
                or ""
            ),
        }
        if key == "weak" and len(weak_titles) < weak_samples:
            weak_titles.append(item)
        if key == "mixed" and len(mixed_titles) < weak_samples:
            mixed_titles.append(item)

    total_reacted = sum(counts.values())
    return {
        "rows_total": len(rows),
        "rows_with_reaction": total_reacted,
        "rows_missing_reaction": missing,
        "counts": {k: counts.get(k, 0) for k in REACTION_VALUES},
        "counts_labeled": {
            REACTION_LABELS[k]: counts.get(k, 0) for k in REACTION_VALUES
        },
        "weak_samples": weak_titles,
        "mixed_samples": mixed_titles,
    }


def _format_text(summary: dict) -> str:
    lines = [
        "=== LINE user_reaction summary (Q5) ===",
        f"rows_total: {summary['rows_total']}",
        f"rows_with_reaction: {summary['rows_with_reaction']}",
        f"rows_missing_reaction: {summary['rows_missing_reaction']}",
        "",
        "counts:",
    ]
    for label, n in summary["counts_labeled"].items():
        lines.append(f"  {label}: {n}")
    lines.append("")
    lines.append("weak samples (いまいち):")
    if not summary["weak_samples"]:
        lines.append("  (none)")
    else:
        for s in summary["weak_samples"]:
            lines.append(f"  - {s['title']}: {s['critique_summary'][:80]}")
    lines.append("")
    lines.append("mixed samples (もう少し):")
    if not summary["mixed_samples"]:
        lines.append("  (none)")
    else:
        for s in summary["mixed_samples"]:
            lines.append(f"  - {s['title']}: {s['critique_summary'][:80]}")
    lines.append("")
    lines.append(
        "Hint: weak/mixed が多い TITLE・CRITIQUE_SUMMARY の傾向を見て、"
        "プロンプトを人手で調整（自動変更なし）。"
    )
    return "\n".join(lines)


def _format_md(summary: dict) -> str:
    lines = [
        "# LINE user_reaction summary (Q5)",
        "",
        f"- rows_total: **{summary['rows_total']}**",
        f"- rows_with_reaction: **{summary['rows_with_reaction']}**",
        f"- rows_missing_reaction: **{summary['rows_missing_reaction']}**",
        "",
        "## Counts",
        "",
        "| reaction | count |",
        "|---|---|",
    ]
    for label, n in summary["counts_labeled"].items():
        lines.append(f"| {label} | {n} |")
    lines.extend(["", "## Weak samples", ""])
    if not summary["weak_samples"]:
        lines.append("(none)")
    else:
        for s in summary["weak_samples"]:
            lines.append(f"- **{s['title']}** — {s['critique_summary']}")
    lines.extend(["", "## Mixed samples", ""])
    if not summary["mixed_samples"]:
        lines.append("(none)")
    else:
        for s in summary["mixed_samples"]:
            lines.append(f"- **{s['title']}** — {s['critique_summary']}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Summarize LINE user_reaction dumps (Q5)")
    ap.add_argument("--input", type=Path, required=True, help="JSON or CSV export")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    path = Path(args.input)
    if not path.is_file():
        raise SystemExit(f"input not found: {path}")
    summary = summarize(_load_rows(path))
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.md:
        print(_format_md(summary))
    else:
        print(_format_text(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
