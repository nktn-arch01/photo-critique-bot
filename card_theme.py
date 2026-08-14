"""カード背景テーマの単一ソース（識別子・パレット・正規化）。

識別子は LINE / Supabase / デスクトップ / カード描画で共通:
  - dark  : 背景ダーク・文字ライト（従来どおり）
  - light : 背景白・文字黒
"""

from __future__ import annotations

CARD_THEME_DARK = "dark"
CARD_THEME_LIGHT = "light"
DEFAULT_CARD_THEME = CARD_THEME_DARK
VALID_CARD_THEMES = frozenset({CARD_THEME_DARK, CARD_THEME_LIGHT})

# 表示名（GUI / LINE メッセージ用）
CARD_THEME_LABELS = {
    CARD_THEME_DARK: "ダーク",
    CARD_THEME_LIGHT: "ライト",
}


def normalize_card_theme(value: str | None) -> str:
    """入力ゆれを dark / light に正規化する。不正値は DEFAULT。"""
    if not value:
        return DEFAULT_CARD_THEME
    v = str(value).strip().lower()
    aliases = {
        "dark": CARD_THEME_DARK,
        "ダーク": CARD_THEME_DARK,
        "darkmode": CARD_THEME_DARK,
        "light": CARD_THEME_LIGHT,
        "ライト": CARD_THEME_LIGHT,
        "lightmode": CARD_THEME_LIGHT,
        "white": CARD_THEME_LIGHT,
    }
    # 日本語ラベルはそのまま比較
    raw = str(value).strip()
    if raw in ("ダーク", "ダークモード"):
        return CARD_THEME_DARK
    if raw in ("ライト", "ライトモード"):
        return CARD_THEME_LIGHT
    return aliases.get(v, DEFAULT_CARD_THEME)


def card_theme_label(theme: str | None) -> str:
    return CARD_THEME_LABELS.get(normalize_card_theme(theme), CARD_THEME_LABELS[DEFAULT_CARD_THEME])


def get_card_palette(theme: str | None) -> dict:
    """テーマ別の描画色辞書を返す。"""
    t = normalize_card_theme(theme)
    if t == CARD_THEME_LIGHT:
        return {
            "theme": CARD_THEME_LIGHT,
            "bg": (255, 255, 255),
            "title": (20, 20, 24),
            "summary": (70, 75, 85),
            "score_label": (90, 95, 105),
            # ★ は二次（Q1）。Gold は残すが彩度を落とす
            "stars": (168, 130, 40),
            "score_val": (90, 95, 105),
            "body": (30, 35, 45),
            "line": (200, 205, 215),
            "logo_outline": (160, 165, 175),
        }
    return {
        "theme": CARD_THEME_DARK,
        "bg": (24, 25, 28),
        "title": (255, 255, 255),
        "summary": (180, 185, 195),
        "score_label": (140, 145, 155),
        "stars": (168, 148, 88),
        "score_val": (160, 165, 175),
        # Ivory 寄りの本文＝言葉を残った光として読む
        "body": (236, 230, 214),
        "line": (60, 64, 72),
        "logo_outline": (70, 74, 82),
    }
