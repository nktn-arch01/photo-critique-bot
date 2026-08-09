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
            "眼差しの輪郭 (Contours of the Eyes)",
            (
                "眼差しの輪郭 (Contours of the Eyes)",
                "眼差しの輪郭",
                "Contours of the Eyes",
                "空間の切り取り",
                "空間の切り取り（Framing）",
                "Framing",
                "構図・構成",
                "構図",
            ),
            # 観測可能な枠取り証拠のみ（心の推測は禁止）。軸を直交させるため「光」「物語」は別軸へ。
            "観察対象: 枠内/枠外の選択、線・形・シルエット、視線誘導、余白の設計。"
            "アンカー: ★1=切り取りの意図が弱い ★3=枠と導線が明確 ★5=枠取りが一枚の主軸。"
            "禁止: 撮影者の心情の推測だけで点数を上げない。",
        ),
        _axis(
            "sensitivity",
            "光の情動 (Emotion of Light)",
            (
                "光の情動 (Emotion of Light)",
                "光の情動",
                "Emotion of Light",
                "光への感受性",
                "光への感受性（Sensitivity）",
                "Sensitivity",
                "光・色彩",
                "光",
            ),
            "観察対象: 光の方向、反射、ハイライト/シャドウのグラデーション、質感の立ち方。"
            "アンカー: ★1=光の特徴が弱い ★3=方向と質感がはっきり読める ★5=光の振る舞いが一枚の主軸。"
            "禁止: 時間帯ラベルや「美しい光」など抽象語だけで加点しない。",
        ),
        _axis(
            "story",
            "物語の気配 (Signs of the Story)",
            (
                "物語の気配 (Signs of the Story)",
                "物語の気配",
                "Signs of the Story",
                "情景への投影",
                "情景への投影（Story）",
                "Story",
                "ストーリー",
            ),
            "観察対象: 画面に実際にあるしぐさ・配置・痕跡・関係性から読める「前後の時間」や気配。"
            "人物がいない場合は物・空間の関係からのみ評価し、人物を仮定しない。"
            "アンカー: ★1=気配が薄い ★3=一瞬の前後が想像できる ★5=物語の起点が一枚の主軸。"
            "禁止: 写真にない人物・出来事の創作。",
        ),
        _axis(
            "technical",
            "表現の意識 (Awareness of Expression)",
            (
                "表現の意識 (Awareness of Expression)",
                "表現の意識",
                "Awareness of Expression",
                "道具との対話",
                "道具との対話（Technical）",
                "Technical",
                "技術・露出",
                "技術",
            ),
            "観察対象: 露出の振り（ハイキー/ローキー等）、被写界深度、静止/ブレなど「選択の痕跡」として読める効果。"
            "アンカー: ★1=選択の痕跡が弱い ★3=露出やボケ等の選択が読める ★5=その選択が一枚の主軸。"
            "禁止: 機材名や設定値の正しさ採点。数値の是非ではなく表現への効きを見る。",
        ),
        _axis(
            "sense",
            "感性の兆し（Signs of sensibility）",
            (
                "感性の兆し（Signs of sensibility）",
                "感性の兆し",
                "Signs of sensibility",
                "内なる感性の純度",
                "内なる感性の純度（Sense）",
                "眼差しの純度",
                "Sense",
                "独自・世界観",
                "独自",
            ),
            "観察対象: 定型から外れた視点の偏り、モチーフの選び方、曖昧さの残し方、反復しそうなこだわりの痕跡。"
            "アンカー: ★1=一般的な見栄え中心 ★3=独自の偏りが一つ明確 ★5=視点のこだわりが画面を支配。"
            "禁止: 他軸（枠・光・物語・技術）の言い換えだけで高得点にしない。",
        ),
    ),
    score_disclaimer="",  # N-01: 免責文は出さない
    score_definition_rule=(
        "■SCORES は技術の出来栄え採点ではない。"
        "各項目にはカード用の「表示名」（日英併記のラベル）と、AIだけが使う「深層基準」がある。"
        "深層基準・アンカー・禁止事項の文言はユーザー／カード／SCORES行に絶対に出さない。"
        "採点は写真上の観察可能な証拠のみ。撮影者の内心の推測だけでは上げない。"
        "★は深層基準のアンカー（★1/★3/★5）に最も近い整数を選ぶ。迷ったら低い方へ（過大評価禁止）。"
        "5軸はできるだけ独立に採点する（同じ理由で複数軸を★5にしない）。"
        "人物がいない写真で story を盛らない。存在しない要素は創作せず低めに付ける。"
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
