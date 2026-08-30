"""地域・タイムゾーン・時間帯 → 講評プロンプト用の光の手掛かり。

UI の不定時法ラベル（夜明け／夕暮れ／夜 等）は画面表示用。
プロンプトへはそのラベルをそのまま入れず、禁止語を含まない光の事実へ変換する（規則5）。
"""

from __future__ import annotations

from guided_futei_time import FUTEI_DAY_BANDS, FUTEI_NIGHT_BAND

# 不定時法ラベル → 光の手掛かり（TIME_ZONE_FACT_BANNED_STEMS を含めない）。
LIGHT_PHYSICS_BY_BAND: dict[str, str] = {
    "夜明け（六）": "地平線付近の低角度の自然光。青みから金みへの変化と長い影が起きやすい",
    "朝方（五）": "太陽高度はまだ低め。横からの光と長めの影が起きやすい",
    "午前（四）": "太陽高度が上がり始め、影が短くなり始める自然光",
    "正午（九）": "太陽高度が高め。短い影と強い直射が起きやすい（日陰・室内はこの限りではない）",
    "午後（八）": "太陽が下り始め、影が伸び始める自然光",
    "夕方（七）": "低角度の自然光。コントラストと色温度の変化が起きやすい",
    "夕暮れ（六）": "日没前後の低照度。空のグラデーションと長い影が起きやすい",
    FUTEI_NIGHT_BAND: "低照度。自然光より人工光・室内光が主になりやすい",
    "不明": "光の手掛かりなし。画面に見える光・色・影だけを読む",
}

LIGHT_HINT_USAGE_RULE = (
    "地域・タイムゾーン・光の手掛かりは「その土地・その時刻に起きやすい光」の背景知識です。"
    "画面の光・色・影が手掛かりと食い違うときは画面を優先してください（室内・逆光・日陰・人工光）。"
    "観光地名の列挙や撮影者の住所推測はしない。"
    "手掛かりを『朝日』『夕日』『夕焼け』『夕暮れ』『夕映え』『夕景』『夜景』『黄昏』『早朝』『夜の』"
    "などの単語で出力にしないこと。"
)

_MISSING = frozenset({"", "なし", "不明", "None"})


def _clean(val: object) -> str:
    if val is None:
        return ""
    text = str(val).replace("\x00", "").strip()
    return "" if (not text or text in _MISSING) else text


def light_physics_hint(
    time_band: str | None,
    *,
    fallback_clock_fact: str | None = None,
) -> str:
    """不定時法ラベルを光の手掛かりへ。未知・欠損は時計帯ファクト、それも無ければ不明文。"""
    band = (time_band or "").replace("\x00", "").strip()
    if band in LIGHT_PHYSICS_BY_BAND:
        return LIGHT_PHYSICS_BY_BAND[band]
    fact = _clean(fallback_clock_fact)
    if fact:
        return fact
    return LIGHT_PHYSICS_BY_BAND["不明"]


def format_place_and_light_facts(
    *,
    timezone: str | None = None,
    region: str | None = None,
    time_band: str | None = None,
    time_zone_fact: str | None = None,
    shot_at: str | None = None,
    include_shot_at: bool = False,
) -> str:
    """プロンプトのファクト行。生の time_band ラベルは出さない。"""
    lines: list[str] = []
    if include_shot_at:
        when = _clean(shot_at)
        if when:
            lines.append(f"- 撮影日時: {when}")
    tz = _clean(timezone)
    if tz:
        lines.append(f"- タイムゾーン: {tz}")
    place = _clean(region)
    if place:
        lines.append(f"- 地域（都市レベル）: {place}")
    lines.append(
        "- 光の手掛かり（視覚ラベルではない）: "
        + light_physics_hint(time_band, fallback_clock_fact=time_zone_fact)
    )
    return "\n".join(lines)


def assert_physics_map_complete() -> None:
    """テスト用: 全バンドに対応があり、値に禁止語を混ぜない。"""
    from scanner import TIME_ZONE_FACT_BANNED_STEMS

    expected = set(FUTEI_DAY_BANDS) | {FUTEI_NIGHT_BAND, "不明"}
    missing = expected - set(LIGHT_PHYSICS_BY_BAND)
    if missing:
        raise AssertionError(f"LIGHT_PHYSICS_BY_BAND missing: {sorted(missing)}")
    for band, physics in LIGHT_PHYSICS_BY_BAND.items():
        for stem in TIME_ZONE_FACT_BANNED_STEMS:
            if stem in physics:
                raise AssertionError(
                    f"light physics for {band!r} contains banned stem {stem!r}: {physics!r}"
                )
        if band != "不明" and band in physics:
            raise AssertionError(
                f"light physics for {band!r} still contains the UI label: {physics!r}"
            )
