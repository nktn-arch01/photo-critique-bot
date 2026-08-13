#!/usr/bin/env python3
"""H3 差分（DxO 前後 Rating）を集計してプロンプト改善の材料にする（Q5）。

使い方:
  # 月フォルダ（配下の _lumina/sessions を探索）
  python3 scripts/summarize_h3_deltas.py --dir ~/OM2026/OM202606

  # セッション JSON を直接
  python3 scripts/summarize_h3_deltas.py --sessions eval/fixtures_q5/sample_session_with_h3.json

  # Markdown 出力
  python3 scripts/summarize_h3_deltas.py --dir ~/OM2026/OM202606 --md

自動でプロンプトは書き換えません。遷移の多いパターンを見て人手で調整します。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _iter_session_paths(dir_path: Path | None, sessions: list[Path]) -> list[Path]:
    found: list[Path] = []
    for s in sessions:
        p = Path(s)
        if p.is_file():
            found.append(p)
    if dir_path is not None:
        root = Path(dir_path)
        if not root.exists():
            raise SystemExit(f"dir not found: {root}")
        found.extend(sorted(root.rglob("_lumina/sessions/*.json")))
        # 直下 sessions も（テスト用）
        found.extend(sorted(root.glob("*.json")))
    # 重複除去（順序維持）
    seen: set[Path] = set()
    out: list[Path] = []
    for p in found:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        out.append(rp)
    return out


def _load_delta(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[skip] {path}: {e}", file=sys.stderr)
        return None
    delta = doc.get("h3_delta")
    if not isinstance(delta, dict):
        return None
    if delta.get("purpose") and delta.get("purpose") != "judgment_improvement":
        return None
    return delta


def summarize(paths: list[Path]) -> dict:
    transitions: Counter[str] = Counter()
    changed_total = 0
    sessions_with_delta = 0
    sample_changes: list[dict] = []

    for path in paths:
        delta = _load_delta(path)
        if delta is None:
            continue
        sessions_with_delta += 1
        changed_total += int(delta.get("changed_count") or 0)
        for k, v in (delta.get("transitions") or {}).items():
            transitions[str(k)] += int(v)
        for ch in delta.get("changes") or []:
            if len(sample_changes) >= 20:
                break
            sample_changes.append(
                {
                    "session": path.name,
                    "file_name": ch.get("file_name"),
                    "before_rating": ch.get("before_rating"),
                    "after_rating": ch.get("after_rating"),
                    "before_blocks": ch.get("before_blocks") or {},
                    "after_blocks": ch.get("after_blocks") or {},
                }
            )

    return {
        "sessions_scanned": len(paths),
        "sessions_with_h3_delta": sessions_with_delta,
        "changed_total": changed_total,
        "transitions": dict(sorted(transitions.items(), key=lambda kv: (-kv[1], kv[0]))),
        "sample_changes": sample_changes,
    }


def _format_text(summary: dict) -> str:
    lines = [
        "=== H3 delta summary (Q5) ===",
        f"sessions_scanned: {summary['sessions_scanned']}",
        f"sessions_with_h3_delta: {summary['sessions_with_h3_delta']}",
        f"changed_total: {summary['changed_total']}",
        "",
        "transitions (human corrected Rating):",
    ]
    if not summary["transitions"]:
        lines.append("  (none)")
    else:
        for k, v in summary["transitions"].items():
            lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("sample changes (up to 20):")
    if not summary["sample_changes"]:
        lines.append("  (none)")
    else:
        for ch in summary["sample_changes"]:
            lines.append(
                f"  - {ch['session']} / {ch['file_name']}: "
                f"{ch['before_rating']}->{ch['after_rating']} "
                f"blocks={ch['before_blocks']}->{ch['after_blocks']}"
            )
    lines.append("")
    lines.append(
        "Hint: 多い遷移（例 2->4）は M2/M3 の閾値や説明文の見直し候補。"
        "自動ではプロンプトを変えません。"
    )
    return "\n".join(lines)


def _format_md(summary: dict) -> str:
    lines = [
        "# H3 delta summary (Q5)",
        "",
        f"- sessions_scanned: **{summary['sessions_scanned']}**",
        f"- sessions_with_h3_delta: **{summary['sessions_with_h3_delta']}**",
        f"- changed_total: **{summary['changed_total']}**",
        "",
        "## Transitions",
        "",
        "| before->after | count |",
        "|---|---|",
    ]
    if not summary["transitions"]:
        lines.append("| (none) | 0 |")
    else:
        for k, v in summary["transitions"].items():
            lines.append(f"| `{k}` | {v} |")
    lines.extend(["", "## Sample changes", ""])
    if not summary["sample_changes"]:
        lines.append("(none)")
    else:
        for ch in summary["sample_changes"]:
            lines.append(
                f"- `{ch['session']}` / `{ch['file_name']}`: "
                f"{ch['before_rating']}→{ch['after_rating']}"
            )
    lines.extend(
        [
            "",
            "_自動でプロンプトは書き換えません。多い遷移を見て人手で調整してください。_",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Summarize H3 deltas for prompt improvement (Q5)")
    ap.add_argument("--dir", type=Path, help="Library folder to search for _lumina/sessions")
    ap.add_argument(
        "--sessions",
        type=Path,
        nargs="*",
        default=[],
        help="Session JSON files",
    )
    ap.add_argument("--md", action="store_true", help="Markdown output")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args(argv)

    if args.dir is None and not args.sessions:
        ap.error("need --dir and/or --sessions")

    paths = _iter_session_paths(args.dir, list(args.sessions or []))
    summary = summarize(paths)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.md:
        print(_format_md(summary))
    else:
        print(_format_text(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
