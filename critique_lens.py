"""対話レンズ（lens）定義の単一ソース。

- mode (compact/full) とは直交: mode=生成の深さ, lens=対話の型
- v1 / v1.1: 実行時は常に self（本人の写真との対話）
- 将来: audience（第三者・展示／コンテスト）や brief 駆動ルーブリックを追加可能
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
    meaning: str  # プロンプト用の深層基準


@dataclass(frozen=True)
class CritiqueLens:
    id: str
    display_name: str
    system_role: str
    score_axes: tuple[ScoreAxis, ...]
    score_disclaimer: str
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
            "空間の切り取り",
            ("空間の切り取り", "空間の切り取り（Framing）", "Framing", "構図・構成", "構図"),
            "視線誘導の設計、幾何学的な構造美、シルエットの活用など、画面を構造化した際のアンテナの強さ。",
        ),
        _axis(
            "sensitivity",
            "光への感受性",
            ("光への感受性", "光への感受性（Sensitivity）", "Sensitivity", "光・色彩", "光"),
            "光の照射角度、テクスチャーの強調、反射の美学など、微細な光の質感に対する鋭敏さ。",
        ),
        _axis(
            "story",
            "情景への投影",
            ("情景への投影", "情景への投影（Story）", "Story", "ストーリー"),
            "人物のしぐさから生まれる一瞬のドラマ、静寂の余韻、撮影者が「光を共有した」と実感した瞬間の投影度。",
        ),
        _axis(
            "technical",
            "道具との対話",
            ("道具との対話", "道具との対話（Technical）", "Technical", "技術・露出", "技術"),
            "意図的な露出制御（眩しさの維持や深いアンダー）、被写界深度による主題の分離など、設定を表現の言葉として使いこなした度合い。",
        ),
        _axis(
            "sense",
            "内なる感性の純度",
            (
                "内なる感性の純度",
                "内なる感性の純度（Sense）",
                "眼差しの純度",
                "Sense",
                "独自・世界観",
                "独自",
            ),
            "他の誰でもない独自のこだわりや、曖昧さ（ブレ・ボケ）をあえて残した表現の純度。",
        ),
    ),
    score_disclaimer="これは良し悪しを測る点数ではなく、あなたの眼差しを記した目盛りである",
    score_definition_rule=(
        "■SCORES は技術的な出来栄えの採点ではない。"
        "撮影者の「感性のアンテナ」がどの要素に強く向いていたかを示す「熱量や純度（感度）」として 1〜5 を算出すること。"
        "★5 は完璧を意味せず、その要素がその一枚で表現の核となっていることを示す。"
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
            # 「空間の切り取り（Framing）」形式
            if compact.startswith(c.replace(" ", "").replace("　", "")):
                return axis.key
    return None


def canonical_score_label(key: str, lens: CritiqueLens | None = None) -> str:
    lens = lens or get_lens()
    for axis in lens.score_axes:
        if axis.key == key:
            return axis.label
    return key
