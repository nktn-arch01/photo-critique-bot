"""プロンプト／講評出力の契約（審判語・時間帯・人物分岐）。

オフライン回帰テストと Phase D 自動チェックの単一ソース。
モデル変更・プロンプト編集時は、まずここを壊さないこと。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Iterable

from critique_parser import parse_critique_text
from critique_lens import DEFAULT_LENS
from scanner import TIME_ZONE_FACT_BANNED_STEMS

# ---------------------------------------------------------------------------
# Q2: 指示プロンプト側の審判語（復活禁止）
# ---------------------------------------------------------------------------

# 指示文に書いてはいけない語（Wave A5 / 伴走スタンス）
JUDGE_VOCAB_FORBIDDEN_IN_PROMPTS: tuple[str, ...] = (
    "基本評価",
    "確定評価の維持",
    "★評価",
    "プロの写真評論家",
    "短く採点",
)

# Phase2 に必須の伴走／観察フレーミング（いずれか＋確定観察）
COMPANION_REQUIRED_ANY_OF_PHASE2: tuple[str, ...] = (
    "観察スナップショット",
    "事前確定の観察結果",
)
COMPANION_REQUIRED_ALL_OF_PHASE2: tuple[str, ...] = ("確定観察との整合",)

# Phase1 SCORES 行は「採点」ではなくスナップショット
PHASE1_REQUIRED_SCORE_FRAMING: tuple[str, ...] = ("★スナップショット",)
PHASE1_FORBIDDEN_SCORE_FRAMING: tuple[str, ...] = ("★評価",)

# ---------------------------------------------------------------------------
# Q3: 時間帯ラベル（出力禁止）— scanner 禁止語と整合
# ---------------------------------------------------------------------------

# Phase D / プロンプト本文で明示している語（scanner と同一集合のコア）
PHASE_OUTPUT_TIME_BAN: tuple[str, ...] = (
    "朝日",
    "夕日",
    "夕焼け",
    "夕暮れ",
    "夕映え",
    "夕景",
    "夜景",
    "黄昏",
    "早朝",
)

# 朝夕逆転（東なのに夕／西なのに朝）。時間帯禁止と重ねてよい。
EVENING_REVERSAL_STEMS: tuple[str, ...] = (
    "夕暮れ",
    "夕刻",
    "夕方",
    "夕日",
    "夕焼け",
    "夕映え",
    "夕景",
    "黄昏",
)
MORNING_REVERSAL_STEMS: tuple[str, ...] = (
    "朝日",
    "早朝",
)

# Guided が Phase1/Phase2 を差し戻すときの一文。既存 max_retries の中で使う。
# 単語の置換では夕の物語が残るので、観察そのものを書き直させる。
# Phase1 に【1】〜【7】や構図批評を混ぜない（カードはキャッチのまま）。
EAST_WEST_REWRITE_NOTE_PHASE1 = (
    "【再生成】直前のカード文は光の方位の事実と食い違っています。"
    "■TITLE・■SUMMARY・■CRITIQUE_SUMMARY だけを書き直す。【1】〜【7】は出さない。"
    "SUMMARY はキャッチコピーのまま。構図の批評や撮影の助言・テクニックは書かない。"
    "単語だけ言い換えて夕（または朝）の物語を残してはいけない。"
    "『夕暮れ』『夕方』『夕刻』『夕景』『夕映え』『朝日』『早朝』を使わない。"
    "東の空／一日の前半なら、一日の終わりや西の空の光としては書かない。"
)
EAST_WEST_REWRITE_NOTE_PHASE2 = (
    "【再生成】直前の本文は光の方位の事実と食い違っています。"
    "【1】〜【7】の観察を光の方位の事実に合わせて書き直す。"
    "単語だけ言い換えて夕（または朝）の物語を残してはいけない。"
    "『夕暮れ』『夕方』『夕刻』『夕景』『夕映え』『朝日』『早朝』を書かない。"
    "東の空／一日の前半なら、一日の終わりや西の空の光としては書かない。"
)
# テスト・単一 note 経路の既定（Phase1 用。本文の仕事をカードに混ぜない）。
EAST_WEST_REWRITE_NOTE = EAST_WEST_REWRITE_NOTE_PHASE1

# Phase1 プロンプト追加分（「夜の」など）
PHASE1_EXTRA_TIME_BAN: tuple[str, ...] = ("夜の",)

# Full 本文で欠陥示唆を禁ずる語（Phase D FORBID_FIX）
PHASE2_FORBID_FIX: tuple[str, ...] = ("修正", "改善", "失敗", "直す", "直せば")

# ---------------------------------------------------------------------------
# Q3: 人物分岐（出力側）
# ---------------------------------------------------------------------------

PERSON_PRESENCE_STEMS: tuple[str, ...] = ("視線", "しぐさ", "佇まい", "佇む姿")

# 人物なし写真への転用として明示禁止した例（プロンプト禁止例と一致）
NO_PERSON_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "花の佇まい",
    "建物のしぐさ",
    "しぐさのように光を受け止める",
)

# 人物なしでも許す「視線」表現
NO_PERSON_ALLOWED_GAZE_PHRASE = "観る者の視線"

# ---------------------------------------------------------------------------
# Q4: CRITIQUE_SUMMARY は見所＋「もう一度見る／次のシャッター」（N-03 定型は禁止）
# ---------------------------------------------------------------------------

# Phase1 指示に残すこと（2拍）
CRITIQUE_SUMMARY_REQUIRED_BEATS: tuple[str, ...] = (
    "見所",
    "もう一度見る",
    "次のシャッター",
)

# 指示文に「使わない／固定しない」として残すこと（N-03 再発防止）
CRITIQUE_SUMMARY_TEMPLATE_BAN_MUST_APPEAR: tuple[str, ...] = (
    "たのではないでしょうか",
    "あなたは〇〇に惹かれたのでは",
    "みませんか",
)

# 出力側: 見所のあと、往復の開きがあること（いずれか）
CRITIQUE_SUMMARY_OUTPUT_RETURN_ANY_OF: tuple[str, ...] = (
    "もう一度",
    "次に",
    "次の",
    "同じ",
)

# 出力側: この語尾だけで終わるのは N-03 定型
CRITIQUE_SUMMARY_OUTPUT_FORBIDDEN_ENDINGS: tuple[str, ...] = (
    "たのではないでしょうか。",
    "たのではないでしょうか",
    "みませんか。",
    "みませんか？",
)


def assert_time_ban_aligned_with_scanner() -> None:
    """PHASE_OUTPUT_TIME_BAN が scanner 禁止語の部分集合であること。"""
    banned = set(TIME_ZONE_FACT_BANNED_STEMS)
    missing = [w for w in PHASE_OUTPUT_TIME_BAN if w not in banned]
    if missing:
        raise AssertionError(
            f"PHASE_OUTPUT_TIME_BAN not in TIME_ZONE_FACT_BANNED_STEMS: {missing}"
        )


def find_forbidden_stems(text: str, stems: Iterable[str]) -> list[str]:
    return [s for s in stems if s and s in (text or "")]


def check_prompt_judge_vocab(phase1: str, phase2: str, system_role: str = "") -> list[str]:
    """指示プロンプトに審判語が混入していないか。問題があればメッセージ一覧。"""
    errors: list[str] = []
    blob = "\n".join([phase1 or "", phase2 or "", system_role or ""])
    for stem in JUDGE_VOCAB_FORBIDDEN_IN_PROMPTS:
        if stem in blob:
            errors.append(f"forbidden judge vocab in prompts: {stem!r}")
    for stem in PHASE1_FORBIDDEN_SCORE_FRAMING:
        if stem in (phase1 or ""):
            errors.append(f"forbidden Phase1 score framing: {stem!r}")
    for stem in PHASE1_REQUIRED_SCORE_FRAMING:
        if stem not in (phase1 or ""):
            errors.append(f"missing Phase1 score framing: {stem!r}")
    if not any(s in (phase2 or "") for s in COMPANION_REQUIRED_ANY_OF_PHASE2):
        errors.append(
            "Phase2 missing companion framing "
            f"(need one of {COMPANION_REQUIRED_ANY_OF_PHASE2})"
        )
    for stem in COMPANION_REQUIRED_ALL_OF_PHASE2:
        if stem not in (phase2 or ""):
            errors.append(f"Phase2 missing required: {stem!r}")
    return errors


def check_phase1_time_ban_in_prompt(phase1: str) -> list[str]:
    """Phase1 指示に時間帯禁止語リストが残っているか（契約の存在確認）。"""
    errors: list[str] = []
    for stem in PHASE_OUTPUT_TIME_BAN:
        if stem not in (phase1 or ""):
            errors.append(f"Phase1 prompt no longer lists time ban stem: {stem!r}")
    return errors


def _phase1_text_for_ban(critique: str) -> str:
    parsed = parse_critique_text(critique, lens=DEFAULT_LENS)
    return "\n".join(
        [
            parsed.get("title") or "",
            parsed.get("summary") or "",
            parsed.get("point_text") or "",
            critique.split("\n---\n", 1)[0],
        ]
    )


def check_output_time_ban(critique: str) -> dict:
    """出力テキストの時間帯ラベル禁止。"""
    text = _phase1_text_for_ban(critique)
    # Phase1 追加「夜の」も見る（「夜の街」等）。「夜間」「深夜」は scanner 側。
    ban = tuple(PHASE_OUTPUT_TIME_BAN) + tuple(PHASE1_EXTRA_TIME_BAN)
    hits = find_forbidden_stems(text, ban)
    return {"pass": not hits, "hits": hits}


def infer_light_side(light_hint: str) -> str | None:
    """光ヒントから東側（一日の前半）／西側（一日の後半）を読む。否定の『西の空の光ではない』は西に数えない。"""
    hint = light_hint or ""
    east = "東の空から" in hint or "一日の前半" in hint
    west = "西の空から" in hint or "一日の後半" in hint
    if east and not west:
        return "east"
    if west and not east:
        return "west"
    return None


def _text_for_east_west_check(critique: str) -> str:
    """カード欄（TITLE/SUMMARY/CRITIQUE_SUMMARY）と本文を同じ契約で見る。"""
    parsed = parse_critique_text(critique, lens=DEFAULT_LENS)
    return "\n".join(
        [
            parsed.get("title") or "",
            parsed.get("summary") or "",
            parsed.get("point_text") or "",
            parsed.get("body") or "",
            critique or "",
        ]
    )


def check_output_east_west_reversal(critique: str, light_hint: str) -> dict:
    """東の事実なのに夕の語、西の事実なのに朝の語があれば FAIL（カードも本文も、混在も逆転）。"""
    side = infer_light_side(light_hint)
    text = _text_for_east_west_check(critique)
    if side is None:
        return {"pass": True, "side": None, "hits": [], "detail": "no east/west fact"}
    stems = EVENING_REVERSAL_STEMS if side == "east" else MORNING_REVERSAL_STEMS
    hits = find_forbidden_stems(text, stems)
    excerpts: list[str] = []
    for stem in hits:
        idx = text.find(stem)
        if idx >= 0:
            start = max(0, idx - 12)
            excerpts.append(text[start : idx + len(stem) + 12].replace("\n", " "))
    return {
        "pass": not hits,
        "side": side,
        "hits": hits,
        "excerpts": excerpts,
    }


def east_west_phase_accept(light_hint: str) -> Callable[[str], bool] | None:
    """方位事実があるときだけ受理関数を返す。南寄りの高い光などでは None。"""
    if infer_light_side(light_hint) is None:
        return None

    def accept(text: str) -> bool:
        return bool(check_output_east_west_reversal(text, light_hint)["pass"])

    return accept


def check_output_person_present(critique: str) -> dict:
    """人物あり: TITLE または CRITIQUE_SUMMARY に人物観察語があること。"""
    p1 = parse_critique_text(critique.split("\n---\n", 1)[0], lens=DEFAULT_LENS)
    focus = "\n".join([p1.get("title") or "", p1.get("point_text") or ""])
    hits = find_forbidden_stems(focus, PERSON_PRESENCE_STEMS)
    return {"pass": bool(hits), "hits": hits, "detail": focus[:120]}


def check_output_person_absent(critique: str) -> dict:
    """人物なし: 禁止転用例と、観る者以外への佇まい／しぐさ転用を弾く。"""
    text = _phase1_text_for_ban(critique)
    phrase_hits = find_forbidden_stems(text, NO_PERSON_FORBIDDEN_PHRASES)

    # 「観る者の視線」を除いた残りに 佇まい／しぐさ があれば転用疑い
    scrubbed = text.replace(NO_PERSON_ALLOWED_GAZE_PHRASE, "")
    soft_hits = [s for s in ("佇まい", "しぐさ", "佇む姿") if s in scrubbed]
    # 「人物」「人々」「彼女」「彼」の安易な登場（看板キャラ除く簡易）
    person_word_hits = [
        w for w in ("人物", "人々", "彼女", "彼の", "彼は") if w in scrubbed
    ]

    bad = phrase_hits or soft_hits or person_word_hits
    return {
        "pass": not bad,
        "phrase_hits": phrase_hits,
        "soft_hits": soft_hits,
        "person_word_hits": person_word_hits,
    }


def check_output_forbid_fix_in_body(critique: str) -> dict:
    """Full 本文の欠陥示唆語。"""
    parsed = parse_critique_text(critique, lens=DEFAULT_LENS)
    body = parsed.get("body") or ""
    hits = find_forbidden_stems(body, PHASE2_FORBID_FIX)
    return {"pass": not hits, "hits": hits}


_TITLE_WS = re.compile(r"\s+")


def check_phase1_critique_summary_contract(phase1: str) -> list[str]:
    """Q4: Phase1 指示が見所＋往復の2拍で、N-03 定型を禁止していること。"""
    errors: list[str] = []
    text = phase1 or ""
    for stem in CRITIQUE_SUMMARY_REQUIRED_BEATS:
        if stem not in text:
            errors.append(f"Phase1 CRITIQUE_SUMMARY missing beat: {stem!r}")
    for stem in CRITIQUE_SUMMARY_TEMPLATE_BAN_MUST_APPEAR:
        if stem not in text:
            errors.append(
                f"Phase1 CRITIQUE_SUMMARY no longer bans template: {stem!r}"
            )
    return errors


def check_output_critique_summary_beats(critique: str) -> dict:
    """出力の CRITIQUE_SUMMARY が見所だけでなく往復の開きを持ち、定型語尾で終わらないこと。"""
    p1 = parse_critique_text(critique.split("\n---\n", 1)[0], lens=DEFAULT_LENS)
    summary = (p1.get("point_text") or "").strip()
    return_hits = find_forbidden_stems(summary, CRITIQUE_SUMMARY_OUTPUT_RETURN_ANY_OF)
    ending_hits = [
        e for e in CRITIQUE_SUMMARY_OUTPUT_FORBIDDEN_ENDINGS if summary.endswith(e)
    ]
    return {
        "pass": bool(summary) and bool(return_hits) and not ending_hits,
        "summary": summary,
        "return_hits": return_hits,
        "ending_hits": ending_hits,
    }


def check_output_title_len(critique: str, *, max_len: int = 15) -> dict:
    p1 = parse_critique_text(critique.split("\n---\n", 1)[0], lens=DEFAULT_LENS)
    title = p1.get("title") or ""
    title_len = len(_TITLE_WS.sub("", title))
    return {
        "pass": 1 <= title_len <= max_len,
        "title": title,
        "len": title_len,
    }
