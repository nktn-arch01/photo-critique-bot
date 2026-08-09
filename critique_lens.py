"""対話レンズ（lens）定義の単一ソース。

- mode (compact/full) とは直交: mode=生成の深さ, lens=対話の型
- v1 / v1.1: 実行時は常に self（本人の写真との対話）
- 将来: audience（第三者・展示／コンテスト）や brief 駆動ルーブリックを追加可能

スコア軸:
- label … カード／ユーザー向け表示名（SCORES 出力ラベル）
- meaning … AI 向け深層基準（ユーザーには提示しない）
"""

from __future__ import annotations

from dataclasses import dataclass

LENS_SELF = "self"
DEFAULT_LENS = LENS_SELF
VALID_LENSES = frozenset({LENS_SELF})

# 将来 rubric_source 用の概念メモ（未使用）
RUBRIC_SOURCE_BRAND_FIXED = "brand_fixed"
RUBRIC_SOURCE_BRIEF_GENERATED = "brief_generated"


@dataclass(frozen=True)
class ScoreAxis:
    """内部キー固定・表示名はレンズごとに差し替え可能。"""

    key: str
    label: str
    aliases: tuple[str, ...]
    meaning: str  # プロンプト用の深層基準（ユーザー非提示）


@dataclass(frozen=True)
class CritiqueLens:
    id: str
    display_name: str
    system_role: str
    score_axes: tuple[ScoreAxis, ...]
    score_disclaimer: str  # 空文字ならカードに免責を出さない（N-01）
    score_definition_rule: str
    phase5_heading: str  # 【5. ...】の見出し文言


def _axis(key: str, label: str, aliases: tuple[str, ...], meaning: str) -> ScoreAxis:
    return ScoreAxis(key=key, label=label, aliases=aliases, meaning=meaning)


SELF_LENS = CritiqueLens(
    id=LENS_SELF,
    display_name="Lumina Notes（本人対話）",
    system_role=(
        "あなたは撮影者の「良き理解者」であり、フォトブックの編集者です。"
        "単なる技術講評ではなく、「なぜこの一枚を残したのか」という問いを通じて、"
        "撮影者が自分のセンスの正体に気づくこと（AWARENESS）を支援する伴走者として振る舞ってください。"
        "ブランド原則は「評価ではなく理解」「答えではなく対話」です。"
    ),
    score_axes=(
        _axis(
            "framing",
            "眼差しの輪郭",
            (
                "眼差しの輪郭",
                "眼差しの輪郭 (Contours of the Eyes)",
                "Contours of the Eyes",
                "空間の切り取り",
                "空間の切り取り（Framing）",
                "Framing",
                "構図・構成",
                "構図",
            ),
            "視線誘導の設計、幾何学的な構造美、シルエット、フレームの選択から、"
            "撮影者の意識がどこに向かっていたかを読み取れるか。",
        ),
        _axis(
            "sensitivity",
            "光の情動",
            (
                "光の情動",
                "光の情動 (Emotion of Light)",
                "Emotion of Light",
                "光への感受性",
                "光への感受性（Sensitivity）",
                "Sensitivity",
                "光・色彩",
                "光",
            ),
            "光の照射角度、テクスチャーの強調、反射、明暗のグラデーションから、"
            "撮影者の心がどれだけ動かされたかを読み取れるか。",
        ),
        _axis(
            "story",
            "物語の気配",
            (
                "物語の気配",
                "物語の気配 (Signs of the Story)",
                "Signs of the Story",
                "情景への投影",
                "情景への投影（Story）",
                "Story",
                "ストーリー",
            ),
            "人物の感情、物語の起点、静寂、共鳴、個人的な記憶をどれだけ読み取れたか。",
        ),
        _axis(
            "technical",
            "表現の意識",
            (
                "表現の意識",
                "表現の意識 (Awareness of Expression)",
                "Awareness of Expression",
                "道具との対話",
                "道具との対話（Technical）",
                "Technical",
                "技術・露出",
                "技術",
            ),
            "意図的な露出制御（ハイライト/アンダー）、被写界深度（ボケ/シャープネス）などから、"
            "撮影者の意識や心の動き、記憶や感情を具現化する意図がどれだけ読み取れたか。",
        ),
        _axis(
            "sense",
            "感性の兆し",
            (
                "感性の兆し",
                "感性の兆し（Signs of sensibility）",
                "Signs of sensibility",
                "内なる感性の純度",
                "内なる感性の純度（Sense）",
                "眼差しの純度",
                "Sense",
                "独自・世界観",
                "独自",
            ),
            "独自のこだわり（#静寂 #反射等）、個性、癖などがどれだけ読み取れたか。",
        ),
    ),
    score_disclaimer="",  # N-01: 免責文は出さない
    score_definition_rule=(
        "■SCORES は技術的な出来栄えの採点ではない。"
        "各スコアにはカード用の「表示名」と、AIだけが使う「深層基準」がある。"
        "深層基準の文言はユーザー・カード・SCORES行に出さない。"
        "★1〜5 は、提示写真からその深層基準がどれだけ読み取れたか、"
        "およびその基準が講評にどれだけ影響を与えたかの度合いとする。"
        "★5 は完璧を意味せず、その要素がその一枚で表現の核／講評の主軸になっていることを示す。"
    ),
    phase5_heading="次なる一枚への対話と提案",
)

_LENSES: dict[str, CritiqueLens] = {
    LENS_SELF: SELF_LENS,
}


def normalize_lens(value: str | None) -> str:
    if not value:
        return DEFAULT_LENS
    v = str(value).strip().lower()
    if v in VALID_LENSES:
        return v
    aliases = {
        "self": LENS_SELF,
        "本人": LENS_SELF,
        "lumina": LENS_SELF,
        "lumina_notes": LENS_SELF,
    }
    return aliases.get(v, DEFAULT_LENS)


def get_lens(lens: str | None = None) -> CritiqueLens:
    return _LENSES[normalize_lens(lens)]


def score_alias_to_key(label: str, lens: CritiqueLens | None = None) -> str | None:
    """表示名／旧名／英語別名を内部キーへ。未知ラベルは None。"""
    lens = lens or get_lens()
    raw = (label or "").strip()
    if not raw:
        return None
    # 全角括弧内の英語を除いた比較用
    compact = raw.replace(" ", "").replace("　", "")
    for axis in lens.score_axes:
        candidates = {axis.label, axis.key, *axis.aliases}
        for c in candidates:
            if raw == c or compact == c.replace(" ", "").replace("　", ""):
                return axis.key
            # 「眼差しの輪郭 (Contours of the Eyes)」形式
            if compact.startswith(c.replace(" ", "").replace("　", "")):
                return axis.key
    return None


def canonical_score_label(key: str, lens: CritiqueLens | None = None) -> str:
    lens = lens or get_lens()
    for axis in lens.score_axes:
        if axis.key == key:
            return axis.label
    return key
