#!/usr/bin/env python3
"""Guided 光方位プロンプトの上限つき評価。

既定はオフライン（API 0回）。--live は Phase1 のみ・最大3回・temperature=0・キャッシュ。
合格までプロンプトを自動で書き換え続けない。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_vision import DEFAULT_OPENAI_MODEL
from critique_engine import generate_critique_with_prompts
from critique_lens import normalize_lens
from critique_prompts import get_system_role
from guided_web.guided_privacy import GuidedCritiqueContext, build_guided_phase1_prompt, build_guided_phase2_prompt
from guided_web.light_prompt_variants import VARIANT_IDS, present_light_hint
from prompt_contracts import check_output_east_west_reversal

EVAL_DIR = ROOT / "eval" / "prompt_eval"
FIXTURES = EVAL_DIR / "fixtures"
CACHE_DIR = EVAL_DIR / "cache"
OUT_DIR = EVAL_DIR / "out"

EAST_HINT = (
    "東の空からの低い自然光（一日の前半・ブルーアワー相当。"
    "ガラスのオレンジや青い空があっても西の空の光ではない）"
)
WEST_HINT = (
    "西の空からの低い自然光（一日の後半・ゴールデンアワー相当。"
    "ガラスのオレンジや青い空があっても東の空の光ではない）"
)

_P02_CTX = {
    "image": {
        "image_id": "p02-eval",
        "size": "7728x5152",
        "shot_at": "2025-11-12T05:45:22+09:00",
        "timezone": "Asia/Tokyo",
        "region": "東京",
        "time_band": "夜明け（六）",
        "light_hint": EAST_HINT,
    },
    "camera": {
        "focal_length": "23mm",
        "aperture": "f/5.6",
        "shutter_speed": "1/34s",
        "iso": "ISO 5000",
        "mode": "絞り優先",
        "exposure_compensation": "-1.7 EV",
    },
}


def _offline_rows() -> list[dict]:
    east_pass = (FIXTURES / "east_pass_phase1.txt").read_text(encoding="utf-8")
    east_fail = (FIXTURES / "east_fail_mix_dusk.txt").read_text(encoding="utf-8")
    card_fail = (FIXTURES / "east_fail_card_dusk.txt").read_text(encoding="utf-8")
    body_fail = (FIXTURES / "east_fail_body_coexist.txt").read_text(encoding="utf-8")
    ok = check_output_east_west_reversal(east_pass, EAST_HINT)
    bad = check_output_east_west_reversal(east_fail, EAST_HINT)
    card = check_output_east_west_reversal(card_fail, EAST_HINT)
    body = check_output_east_west_reversal(body_fail, EAST_HINT)
    return [
        {
            "id": "fixture_east_pass",
            "variant": "fixture",
            "pass": ok["pass"],
            "hits": ok.get("hits", []),
            "excerpts": ok.get("excerpts", []),
            "api_calls": 0,
            "cached": False,
        },
        {
            "id": "fixture_east_fail_mix_detected",
            "variant": "fixture",
            "pass": not bad["pass"],
            "hits": bad.get("hits", []),
            "excerpts": bad.get("excerpts", []),
            "api_calls": 0,
            "cached": False,
            "detail": "mixed dusk must be detected as reversal",
        },
        {
            "id": "fixture_east_fail_card_dusk_detected",
            "variant": "fixture",
            "pass": not card["pass"] and "夕暮れ" in (card.get("hits") or []),
            "hits": card.get("hits", []),
            "excerpts": card.get("excerpts", []),
            "api_calls": 0,
            "cached": False,
            "detail": "SUMMARY 夕暮れ is a card reversal",
        },
        {
            "id": "fixture_east_fail_body_coexist_detected",
            "variant": "fixture",
            "pass": not body["pass"] and "夕暮れ" in (body.get("hits") or []),
            "hits": body.get("hits", []),
            "excerpts": body.get("excerpts", []),
            "api_calls": 0,
            "cached": False,
            "detail": "【1】 dusk + east fact coexistence is a reversal",
        },
    ]


def _cache_key(variant: str, prompt: str, image: Path, model: str, temperature: float) -> str:
    digest = hashlib.sha256()
    digest.update(variant.encode())
    digest.update(prompt.encode())
    digest.update(image.read_bytes())
    digest.update(model.encode())
    digest.update(str(temperature).encode())
    return digest.hexdigest()[:32]


def _live_one(
    image: Path,
    variant: str,
    *,
    model: str,
    temperature: float,
) -> tuple[dict, int, bool]:
    ctx = GuidedCritiqueContext.from_api_params(_P02_CTX)
    prompt = build_guided_phase1_prompt(ctx, variant=variant)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(variant, prompt, image, model, temperature)
    cache_path = CACHE_DIR / f"{key}.json"
    if cache_path.is_file():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        text = payload["phase1"]
        calls = 0
        cached = True
    else:
        lens_id = normalize_lens("self")
        text = generate_critique_with_prompts(
            image,
            mode="compact",
            lens=lens_id,
            max_retries=1,
            system_role=get_system_role(lens_id),
            phase1_temperature=temperature,
            model=model,
            build_phase1=lambda: build_guided_phase1_prompt(ctx, variant=variant),
            build_phase2=lambda phase1_text: build_guided_phase2_prompt(
                ctx, phase1_text, variant=variant
            ),
        )
        cache_path.write_text(
            json.dumps({"phase1": text, "variant": variant}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        calls = 1
        cached = False
    hint = present_light_hint(EAST_HINT, variant)
    check = check_output_east_west_reversal(text, hint)
    row = {
        "id": f"live_p02_{variant}",
        "variant": variant,
        "pass": check["pass"],
        "hits": check.get("hits", []),
        "excerpts": check.get("excerpts", []),
        "title": text.split("\n", 1)[0][:80],
        "preview": text[:240].replace("\n", " / "),
        "api_calls": calls,
        "cached": cached,
        "hint": hint,
    }
    return row, calls, cached


def _print_table(rows: list[dict]) -> None:
    print("| id | variant | 朝夕逆転 | hits | API |")
    print("|---|---|---|---|---|")
    for r in rows:
        verdict = "PASS" if r["pass"] else "FAIL"
        hits = ",".join(r.get("hits") or []) or "-"
        api = r.get("api_calls", 0)
        extra = " cache" if r.get("cached") else ""
        print(f"| {r['id']} | {r.get('variant', '-')} | {verdict} | {hits} | {api}{extra} |")
        for ex in r.get("excerpts") or []:
            print(f"  excerpt: {ex}")
        if r.get("preview") and not r["pass"]:
            print(f"  preview: {r['preview']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded Guided light-azimuth eval")
    parser.add_argument("--live", action="store_true", help="Phase1 API (max 3 calls, cache)")
    parser.add_argument("--max-calls", type=int, default=3)
    parser.add_argument("--image", type=Path, default=None)
    parser.add_argument("--model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()
    if args.max_calls > 3:
        print("max-calls is capped at 3", file=sys.stderr)
        args.max_calls = 3

    rows = _offline_rows()
    live_calls = 0
    if args.live:
        image = args.image
        if image is None:
            for cand in (
                ROOT / "eval" / "phase_d" / "images" / "P02_light.jpg",
                ROOT / "eval" / "prompt_eval" / "images" / "P02_light.jpg",
                ROOT / "eval" / "prompt_eval" / "images" / "P02_light.png",
            ):
                if cand.is_file():
                    image = cand
                    break
        if image is None or not image.is_file():
            print("LIVE skipped: no image (pass --image)", file=sys.stderr)
        else:
            for variant in VARIANT_IDS:
                if live_calls >= args.max_calls:
                    break
                row, calls, _cached = _live_one(
                    image, variant, model=args.model, temperature=args.temperature
                )
                live_calls += calls
                rows.append(row)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = OUT_DIR / f"report-{stamp}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    _print_table(rows)
    # offline detector fixtures must all pass; live rows may fail
    offline_ok = all(r["pass"] for r in rows if r["id"].startswith("fixture_"))
    return 0 if offline_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
