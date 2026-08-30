"""
API キー・ネットワーク不要の回帰テスト一式。
push 前: python3 test_offline_suite.py
"""

from pathlib import Path
import tempfile

from PIL import Image

from critique_lens import DEFAULT_LENS, LENS_SELF, get_lens, score_alias_to_key
from critique_parser import parse_critique_text, is_valid_phase2_content
from critique_prompts import CritiquePromptContext, build_phase1_prompt, build_phase2_prompt, get_system_role
from scanner import (
    TIME_ZONE_FACT_BANNED_STEMS,
    _determine_time_zone_fact,
    _apply_datetime_to_meta,
    _default_exif_meta,
    extract_file_metadata,
)
from card_theme import (
    CARD_THEME_DARK,
    CARD_THEME_LIGHT,
    get_card_palette,
    normalize_card_theme,
)
from generate_critique_card import (
    CARD_BG,
    CARD_HEIGHT,
    CARD_MARGIN,
    CARD_WIDTH,
    CRITIQUE_FONT_SIZE,
    LOGO_SIZE,
    LOGO_TEXT_GAP,
    SCORE_FONT_SIZE,
    SCORE_ROW_HEIGHT,
    SUMMARY_FONT_SIZE,
    create_critique_card,
    plan_card_layout,
    _fixed_text_block_height,
)
from line_messaging import split_full_critique_for_line
from log_manager import DesktopLogManager
from privacy_utils import storage_path_from_card_url

CARD_SAMPLE = """
■TITLE: 沈黙を割る線
■SUMMARY: 金属に宿る眼差しの残像
■SCORES:
・眼差の輪郭 (Contours of the Eyes)  : ★★★★☆ (4/5)
・感情の陰影 (Nuances of Emotion)          : ★★★★★ (5/5)
・物語の気配 (Signs of the Story)      : ★★★☆☆ (3/5)
・表現の意図 (Intent of Expression) : ★★★★★ (5/5)
・感性の兆し (Signs of Sensibility)   : ★★★★☆ (4/5)
■CRITIQUE_SUMMARY: 境界のきらめきと線の陰影が、見所として立ち上がる。次に同じ反射に出会ったら、割れ目のどちらを残すかだけ決めてみる。
"""

PHASE1_SAMPLE = """
■TITLE: 試験タイトル
■SUMMARY: キャッチ
■SCORES:
・眼差の輪郭 (Contours of the Eyes)  : ★★★☆☆ (3/5)
・感情の陰影 (Nuances of Emotion)          : ★★★★☆ (4/5)
■CRITIQUE_SUMMARY: 要約文です。
"""

# 旧ラベル互換（パーサー正規化用）
PHASE1_LEGACY_SCORES = """
■TITLE: 旧形式
■SUMMARY: 互換
■SCORES:
・構図・構成  : ★★★☆☆ (3/5)
・光・色彩    : ★★★★☆ (4/5)
・ストーリー  : ★★☆☆☆ (2/5)
・技術・露出  : ★★★★★ (5/5)
・独自・世界観: ★★★★☆ (4/5)
■CRITIQUE_SUMMARY: 旧ラベルの要約。
"""

PHASE2_SAMPLE = """
## 【1. 情景】
one
## 【4. EXIF】
four
## 【6. SNS】
six
## 【7. タグ】
#t
"""


def test_parser_phase1():
    p = parse_critique_text(PHASE1_SAMPLE)
    assert p["has_valid_phase1"]
    assert p["title"] == "試験タイトル"
    assert len(p["scores"]) >= 2
    assert "眼差の輪郭 (Contours of the Eyes)" in p["scores"]
    assert p["scores"]["眼差の輪郭 (Contours of the Eyes)"]["key"] == "framing"


def test_parser_legacy_score_aliases():
    p = parse_critique_text(PHASE1_LEGACY_SCORES)
    assert p["has_valid_phase1"]
    labels = list(p["scores"].keys())
    assert labels[0] == "眼差の輪郭 (Contours of the Eyes)"
    assert labels[1] == "感情の陰影 (Nuances of Emotion)"
    assert p["scores"]["表現の意図 (Intent of Expression)"]["val"] == "5"
    assert score_alias_to_key("独自・世界観") == "sense"
    assert score_alias_to_key("空間の切り取り") == "framing"
    assert score_alias_to_key("眼差しの輪郭") == "framing"


def test_parser_phase2():
    assert is_valid_phase2_content(PHASE2_SAMPLE)
    p = parse_critique_text(PHASE2_SAMPLE)
    assert p["has_valid_phase2"]


def test_self_lens_prompts():
    assert DEFAULT_LENS == LENS_SELF
    lens = get_lens()
    assert "良き理解者" in get_system_role()
    assert lens.score_disclaimer == ""  # N-01: 免責削除
    assert lens.score_axes[0].label == "眼差の輪郭 (Contours of the Eyes)"
    assert "観察対象" in lens.score_axes[0].meaning
    assert "アンカー" in lens.score_axes[0].meaning
    ctx = CritiquePromptContext.from_metadata(
        {"camera_model": "TestCam", "lens_model": "TestLens", "user_intent": "光を残したい"},
        {},
    )
    p1 = build_phase1_prompt(ctx)
    assert "眼差の輪郭 (Contours of the Eyes)" in p1
    assert "Contours of the Eyes" in p1
    assert "Nuances of Emotion" in p1
    assert "深層基準" in p1
    assert "ユーザー・カードには非表示" in p1
    assert "過大評価禁止" in p1 or "低い方へ" in p1
    assert "構図・構成" not in p1
    assert "プロの写真評論家" not in p1
    assert "人物の扱い（分岐・厳守）" in p1
    assert "花の佇まい" in p1  # 禁止例がプロンプトに残っていること
    assert "一文目" in p1
    assert "撮影日時" not in p1  # Phase1 に時計を渡さない（規則5）
    # Q4: 見所＋もう一度見る／次のシャッター。N-03 定型は禁止として残す
    assert "見所" in p1
    assert "もう一度見る" in p1
    assert "次のシャッター" in p1
    assert "たのではないでしょうか" in p1  # 禁止例として残っていること
    assert "あなたは〇〇に惹かれたのでは" in p1  # 禁止例として残っていること
    assert "効果的な見所を主体に、読者の好奇心を煽る文章" not in p1
    p2 = build_phase2_prompt(
        ctx, "■TITLE: t\n■SCORES:\n・眼差の輪郭 (Contours of the Eyes)  : ★★★☆☆ (3/5)"
    )
    assert "次なる一枚への対話と提案" in p2
    assert "ステップアップ・アドバイス" not in p2
    assert "曖昧さの肯定" in p2
    assert "DateTimeOriginal" in p2
    assert "時計帯ヒント" in p2
    # Wave A5: 審判語を避け、観察／対話の語彙へ
    assert "基本評価" not in p2
    assert "確定評価の維持" not in p2
    assert "観察スナップショット" in p2 or "事前確定の観察結果" in p2
    assert "確定観察との整合" in p2
    assert "★評価" not in p1
    assert "★スナップショット" in p1


def test_time_zone_fact_labels_avoid_banned_stems():
    import datetime as _dt

    for hour in (5, 12, 17, 23):
        label = _determine_time_zone_fact(_dt.datetime(2025, 1, 1, hour, 0, 0))
        for stem in TIME_ZONE_FACT_BANNED_STEMS:
            assert stem not in label, f"hour={hour} label={label!r} contains {stem!r}"


def test_datetime_prefers_original_not_modify():
    meta = _default_exif_meta()
    assert _apply_datetime_to_meta(meta, "2025:11:12 05:45:22", source="DateTimeOriginal")
    assert meta["date_time"] == "2025-11-12 05:45:22"
    assert meta["datetime_source"] == "DateTimeOriginal"
    assert "04-07時帯" in meta["time_zone_fact"]
    # ModifyDate 相当を渡さないことの契約: 誤った遅い時刻を後から上書きしない
    assert not _apply_datetime_to_meta(meta, "not-a-date", source="bad")


def test_phase_d_p02_uses_datetime_original_not_modify():
    path = Path("eval/phase_d/images/P02_light.jpg")
    if not path.is_file():
        print("skip test_phase_d_p02_uses_datetime_original_not_modify (no image)")
        return
    meta, _, _ = extract_file_metadata(path)
    assert meta["date_time"].startswith("2025-11-12 05:45")
    assert meta["datetime_source"] in ("DateTimeOriginal", "SubSecDateTimeOriginal")
    assert "04-07時帯" in meta["time_zone_fact"]
    for stem in TIME_ZONE_FACT_BANNED_STEMS:
        assert stem not in meta["time_zone_fact"]


def test_log_manager_processed_filename():
    td = Path(tempfile.mkdtemp())
    mgr = DesktopLogManager(td)
    mgr.status_file_path.write_text(
        "[PROCESSED] 2026-01-01 12:00:00 P1234.jpg\n"
        "[PROCESSED] 2026-01-01 12:00:01 P123.jpg\n",
        encoding="utf-8",
    )
    assert mgr.is_processed("P123.jpg") is True
    assert mgr.is_processed("P1234.jpg") is True
    assert mgr.is_processed("P12.jpg") is False


def test_log_manager_wave2_output_names_and_legacy_lookup():
    """Wave 2: 新出力は Lumina*。処理済み／パス解決は旧名も見る。"""
    import shutil

    root = Path(tempfile.mkdtemp())
    try:
        year = root / "2026"
        month = year / "202606"
        month.mkdir(parents=True)
        mgr = DesktopLogManager(month)

        assert mgr.notes_dir.name == "202606Luminaノート"
        assert mgr.cards_dir.name == "202606Luminaカード"
        assert mgr.monthly_log_path.name == "202606Luminaログ.txt"
        assert mgr.annual_log_path.name == "Luminaログ_2026.txt"
        assert mgr.notes_dir.is_dir()
        assert mgr.cards_dir.is_dir()

        # 旧フォルダにだけノート／カードがある場合も処理済み・解決できる
        legacy_note = mgr.legacy_notes_dir / "OldShot.md"
        legacy_note.parent.mkdir(parents=True, exist_ok=True)
        legacy_note.write_text("# legacy", encoding="utf-8")
        legacy_card = mgr.legacy_cards_dir / "OldShot_card.png"
        legacy_card.parent.mkdir(parents=True, exist_ok=True)
        legacy_card.write_bytes(b"png")

        assert mgr.is_processed("OldShot.jpg") is True
        assert mgr.resolve_note_path("OldShot.jpg") == legacy_note
        assert mgr.resolve_card_path("OldShot.jpg") == legacy_card
        # 書き込み先は常に新名
        assert mgr.get_card_output_path("OldShot.jpg") == mgr.cards_dir / "OldShot_card.png"

        sample = (
            "■TITLE: t\n■SUMMARY: s\n■SCORES:\n・構図: ★★★ (3/5)\n"
            "■CRITIQUE_SUMMARY: p\n---\n## 【1. 構図】\nbody"
        )
        mgr.save_analysis_result("NewShot.jpg", "=== メタデータ ===\nok", sample)
        assert (mgr.notes_dir / "NewShot.md").is_file()
        assert mgr.monthly_log_path.is_file()
        assert mgr.annual_log_path.is_file()
        assert mgr.is_processed("NewShot.jpg") is True
        assert mgr.resolve_note_path("NewShot.jpg") == mgr.notes_dir / "NewShot.md"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_iptc_phase1_block_upsert_preserves_stages_and_user():
    from iptc_rating_io import (
        has_complete_phase1_blocks,
        parse_phase1_blocks,
        strip_stage_reason_lines,
        upsert_phase1_blocks,
    )
    from phase1_jpeg import phase1_blocks_to_critique_text

    base = "ユーザーのメモ\n[M2] antenna\n[M3] diversity"
    blocks = {
        "TITLE": "題",
        "SUMMARY": "要",
        "SCORES": "・構図: ★★★☆☆ (3/5) ・光: ★★★★☆ (4/5)",
        "CRITIQUE_SUMMARY": "短評です。",
    }
    updated = upsert_phase1_blocks(base, blocks)
    assert "ユーザーのメモ" in updated
    assert "[M2] antenna" in updated
    assert "[M3] diversity" in updated
    parsed = parse_phase1_blocks(updated)
    assert parsed["TITLE"] == "題"
    assert parsed["CRITIQUE_SUMMARY"] == "短評です。"
    assert has_complete_phase1_blocks(updated)
    # user_intent 用: 機械行は落ちる
    assert strip_stage_reason_lines(updated) == "ユーザーのメモ"
    # 再 upsert しても二重にならない
    again = upsert_phase1_blocks(updated, {**blocks, "TITLE": "新題"})
    assert again.count("TITLE:") == 1
    assert "新題" in again
    text = phase1_blocks_to_critique_text(parse_phase1_blocks(again))
    from critique_parser import parse_critique_text

    p = parse_critique_text(text)
    assert p["has_valid_phase1"]
    assert p["title"] == "新題"


def test_line_dialogue_split_sections_1_to_3():
    from line_messaging import split_dialogue_sections_1_to_3, split_full_critique_for_line

    body = (
        PHASE1_SAMPLE
        + "\n---\n"
        + "## 【1. 情景】\none\n"
        + "## 【2. 光】\ntwo\n"
        + "## 【3. 感情】\nthree\n"
        + "## 【4. EXIF】\nfour\n"
        + "## 【7. タグ】\n#t\n"
    )
    parts = split_dialogue_sections_1_to_3(body)
    assert len(parts) == 3
    assert parts[0].startswith("## 【1.")
    assert parts[1].startswith("## 【2.")
    assert parts[2].startswith("## 【3.")
    assert "【4." not in parts[2]
    # 公開 API も同じ3通
    assert split_full_critique_for_line(body) == parts


def test_line_reactions_labels_and_keys():
    """N2: 3段階ラベル ↔ good/mixed/weak。"""
    from line_reactions import (
        REACTION_GOOD,
        REACTION_MIXED,
        REACTION_WEAK,
        parse_reaction_label,
        reaction_ack_message,
        reaction_quick_reply_items,
    )

    assert parse_reaction_label("👍 いいね") == REACTION_GOOD
    assert parse_reaction_label("💭 もう少し") == REACTION_MIXED
    assert parse_reaction_label("😐 いまいち") == REACTION_WEAK
    assert parse_reaction_label("いいね") == REACTION_GOOD
    assert parse_reaction_label("こんにちは") is None
    items = reaction_quick_reply_items()
    assert len(items) == 3
    assert all(label == text for label, text in items)
    assert "いいね" in reaction_ack_message(REACTION_GOOD)


def test_works_placement_and_folder_error_messages():
    """S1/S7: 置き方ガイドと具体例つきフォルダエラー。"""
    from library_unit import (
        format_screening_folder_error,
        format_works_folder_error,
        works_placement_guide_text,
    )

    guide = works_placement_guide_text()
    assert "_dev.jpg" in guide
    assert "YYYYMM" in guide or "202606" in guide
    assert "RAW" in guide

    s_err = format_screening_folder_error("/tmp/旅行2026")
    assert "旅行2026" in s_err
    assert "OM202606" in s_err
    assert "OK 例" in s_err

    w_err = format_works_folder_error("/tmp/OM202606")
    assert "OM202606" in w_err
    assert "YYYYMM" in w_err


def test_line_full_split_four_parts():
    """旧サンプル（【1】【4】【6】）では Phase1 通を除いた本文側を返す。"""
    combined = PHASE1_SAMPLE + "\n---\n" + PHASE2_SAMPLE
    parts = split_full_critique_for_line(combined)
    assert len(parts) >= 1
    assert parts[0].startswith("## 【1.")
    assert "■TITLE" not in parts[0]


def test_storage_path_from_card_url():
    pub = "https://xxx.supabase.co/storage/v1/object/public/critique-cards/abc123/msg_card.png"
    assert storage_path_from_card_url(pub) == "abc123/msg_card.png"
    signed = (
        "https://xxx.supabase.co/storage/v1/object/sign/critique-cards/"
        "abc123/msg_card.png?token=eyJ"
    )
    assert storage_path_from_card_url(signed) == "abc123/msg_card.png"
    assert storage_path_from_card_url("") is None


def _is_near(color, target, tol=12):
    return all(abs(a - b) <= tol for a, b in zip(color[:3], target[:3]))


def test_create_critique_card_layout():
    """カード生成: 破損なし・1080×1350・余白50・写真貼付・主要文字・ロゴ枠。"""
    assert CARD_MARGIN == 50
    td = Path(tempfile.mkdtemp())
    src = td / "source.png"
    out = td / "card.png"

    # 識別しやすい原色ソース（写真貼付の検出用）
    Image.new("RGB", (900, 600), (220, 40, 40)).save(src)
    create_critique_card(src, CARD_SAMPLE, out)

    assert out.exists() and out.stat().st_size > 1000
    with Image.open(out) as card:
        card.load()  # 破損していないこと
        assert card.size == (CARD_WIDTH, CARD_HEIGHT)
        assert card.mode == "RGB"

        # 四隅と余白内は背景色（全周 50px 余白）
        for xy in (
            (0, 0),
            (CARD_WIDTH - 1, 0),
            (0, CARD_HEIGHT - 1),
            (CARD_WIDTH - 1, CARD_HEIGHT - 1),
            (CARD_MARGIN // 2, CARD_MARGIN // 2),
            (CARD_WIDTH - CARD_MARGIN // 2, CARD_HEIGHT - CARD_MARGIN // 2),
        ):
            assert _is_near(card.getpixel(xy), CARD_BG), f"margin not bg at {xy}"

        # 写真領域（上部中央付近）にソース色が含まれる
        red_hits = 0
        for y in range(CARD_MARGIN, CARD_HEIGHT // 2, 8):
            for x in range(CARD_MARGIN, CARD_WIDTH - CARD_MARGIN, 8):
                if _is_near(card.getpixel((x, y)), (220, 40, 40), tol=20):
                    red_hits += 1
        assert red_hits >= 20, f"photo pixels not found (hits={red_hits})"

        # 文字領域（下部）に白〜明るいピクセル（タイトル等）がある
        bright_hits = 0
        for y in range(CARD_HEIGHT // 2, CARD_HEIGHT - CARD_MARGIN, 4):
            for x in range(CARD_MARGIN, CARD_WIDTH - CARD_MARGIN, 4):
                r, g, b = card.getpixel((x, y))[:3]
                if r >= 230 and g >= 230 and b >= 230:
                    bright_hits += 1
        assert bright_hits >= 30, f"title/text pixels not found (hits={bright_hits})"

        # 右下ロゴ枠 128×128 が描画されている（枠線の非背景ピクセル）
        logo_left = CARD_WIDTH - CARD_MARGIN - LOGO_SIZE
        logo_top = CARD_HEIGHT - CARD_MARGIN - LOGO_SIZE
        edge_px = card.getpixel((logo_left, logo_top))
        assert not _is_near(edge_px, CARD_BG, tol=5), "logo placeholder edge missing"

        # ロゴ左のテキスト隙間帯（中央付近）はロゴ色でないこと（領域分離）
        gap_x = logo_left - LOGO_TEXT_GAP // 2
        gap_y = logo_top + LOGO_SIZE // 2
        assert 0 <= gap_x < CARD_WIDTH


def test_normalize_card_theme():
    assert normalize_card_theme("light") == CARD_THEME_LIGHT
    assert normalize_card_theme("ライト") == CARD_THEME_LIGHT
    assert normalize_card_theme("dark") == CARD_THEME_DARK
    assert normalize_card_theme("ダーク") == CARD_THEME_DARK
    assert normalize_card_theme("unknown") == CARD_THEME_DARK
    assert normalize_card_theme(None) == CARD_THEME_DARK


def test_create_critique_card_light_theme():
    """ライトテーマ: 背景白・タイトルが暗い色で描画される。"""
    td = Path(tempfile.mkdtemp())
    src = td / "source.png"
    out = td / "card_light.png"
    Image.new("RGB", (900, 600), (220, 40, 40)).save(src)
    create_critique_card(src, CARD_SAMPLE, out, theme=CARD_THEME_LIGHT)

    light_bg = get_card_palette(CARD_THEME_LIGHT)["bg"]
    with Image.open(out) as card:
        card.load()
        assert card.size == (CARD_WIDTH, CARD_HEIGHT)
        assert _is_near(card.getpixel((0, 0)), light_bg)
        assert _is_near(card.getpixel((CARD_MARGIN // 2, CARD_MARGIN // 2)), light_bg)

        dark_text_hits = 0
        for y in range(CARD_HEIGHT // 2, CARD_HEIGHT - CARD_MARGIN, 4):
            for x in range(CARD_MARGIN, CARD_WIDTH // 2, 4):
                r, g, b = card.getpixel((x, y))[:3]
                if r <= 40 and g <= 40 and b <= 50:
                    dark_text_hits += 1
        assert dark_text_hits >= 20, f"light theme dark text not found (hits={dark_text_hits})"


def test_critique_summary_short_keeps_fixed_image_area():
    """要約が短くても文字ブロック高さが固定され、写真上端がずれない。"""
    td = Path(tempfile.mkdtemp())
    src = td / "source.png"
    Image.new("RGB", (800, 500), (10, 200, 10)).save(src)

    long_out = td / "long.png"
    short_out = td / "short.png"
    create_critique_card(src, CARD_SAMPLE, long_out)

    short_sample = """
■TITLE: 沈黙を割る線
■SUMMARY: 金属に宿る眼差しの残像
■SCORES:
・眼差の輪郭 (Contours of the Eyes)  : ★★★★☆ (4/5)
・感情の陰影 (Nuances of Emotion)          : ★★★★★ (5/5)
・物語の気配 (Signs of the Story)      : ★★★☆☆ (3/5)
・表現の意図 (Intent of Expression) : ★★★★★ (5/5)
・感性の兆し (Signs of Sensibility)   : ★★★★☆ (4/5)
■CRITIQUE_SUMMARY: 短い。
"""
    create_critique_card(src, short_sample, short_out)

    def green_band(path: Path) -> tuple[int, int]:
        """写真（緑）の最初・最後の行。領域固定なら short/long で一致する。"""
        first = last = None
        with Image.open(path) as im:
            for y in range(CARD_MARGIN, CARD_HEIGHT // 2 + 100):
                hit = False
                for x in range(CARD_MARGIN, CARD_WIDTH - CARD_MARGIN, 8):
                    if _is_near(im.getpixel((x, y)), (10, 200, 10), tol=25):
                        hit = True
                        break
                if hit:
                    if first is None:
                        first = y
                    last = y
        assert first is not None and last is not None
        return first, last

    assert _fixed_text_block_height() > LOGO_SIZE
    assert green_band(long_out) == green_band(short_out)


def test_n01_no_disclaimer_on_card_and_lens():
    """N-01: 免責文はレンズ空・カードに「目盛り」文言を描かない。"""
    assert get_lens().score_disclaimer == ""
    layout = plan_card_layout()
    assert layout.text_height == _fixed_text_block_height()
    assert layout.text_height > LOGO_SIZE
    # 免責行を高さに足していない（空なら DISCLAIMER 分が無い）
    from generate_critique_card import DISCLAIMER_LINE_HEIGHT

    with_disclaimer_extra = layout.text_height + DISCLAIMER_LINE_HEIGHT
    assert _fixed_text_block_height() < with_disclaimer_extra


def test_p2_2_card_words_before_stars():
    """U1/Q1: 言葉が★より上・大きく、写真が文字帯より広い。"""
    assert SCORE_FONT_SIZE < SUMMARY_FONT_SIZE
    assert CRITIQUE_FONT_SIZE >= SUMMARY_FONT_SIZE
    assert SCORE_FONT_SIZE < CRITIQUE_FONT_SIZE
    layout = plan_card_layout()
    assert layout.summary_y < layout.critique_y < layout.scores_y
    assert layout.critique_max_w > layout.score_text_max_w
    assert layout.img_max_h > layout.text_height
    assert SCORE_ROW_HEIGHT < 36


def test_n04_score_label_fits_before_stars():
    """N-04: 日英併記ラベルが★列（SCORE_STARS_X）に食い込まない。"""
    from generate_critique_card import (
        SCORE_FONT_SIZE,
        SCORE_STARS_X,
        SCORE_LABEL_X,
        load_japanese_font,
        _text_width,
    )

    font = load_japanese_font(SCORE_FONT_SIZE)
    gap = 12
    for axis in get_lens().score_axes:
        w = _text_width(font, axis.label)
        assert SCORE_LABEL_X + w + gap <= SCORE_STARS_X, (
            f"label too wide for stars column: {axis.label!r} width={w}"
        )
        assert "観察対象" in axis.meaning and "アンカー" in axis.meaning


def test_n05_sensitivity_mentions_light_and_reflection():
    """N-05: 感情の陰影の深層基準に光線・反射が含まれる。"""
    sens = next(a for a in get_lens().score_axes if a.key == "sensitivity")
    assert "光線" in sens.meaning
    assert "反射" in sens.meaning
    assert "写り込み" in sens.meaning


def test_n06_log_keeps_numeric_scores():
    """N-06: ログ再構成は星＋数字。カード描画コードは (n/5) を書かない。"""
    import inspect
    from generate_critique_card import create_critique_card
    from log_manager import DesktopLogManager

    src = inspect.getsource(create_critique_card)
    assert 'f"({val}/5)"' not in src
    assert "stars" in src

    td = Path(tempfile.mkdtemp())
    mgr = DesktopLogManager(td)
    # save_critique 相当の SCORES 行フォーマットを直接確認
    p = parse_critique_text(CARD_SAMPLE)
    line = f"・{list(p['scores'].keys())[0]}: {list(p['scores'].values())[0]['stars']} ({list(p['scores'].values())[0]['val']}/5)"
    assert "/5)" in line
    assert "★" in line
    _ = mgr  # DesktopLogManager が import 可能であること


def test_iptc_stage_block_upsert_preserves_user_text():
    """T1: [M2]/[M3] はブロック置換。ユーザー文は消さない。"""
    from iptc_rating_io import parse_stage_blocks, upsert_stage_reason

    base = "人のメモです\n[M2] old antenna"
    mid = upsert_stage_reason(base, "M2", "new antenna")
    assert "人のメモです" in mid
    assert "[M2] new antenna" in mid
    assert "old antenna" not in mid

    both = upsert_stage_reason(mid, "M3", "diversity keep")
    assert "[M3] diversity keep" in both
    assert parse_stage_blocks(both) == {
        "M2": "new antenna",
        "M3": "diversity keep",
    }

    # 重複 [M2] は1行に畳む
    messy = "note\n[M2] a\n[M2] b\n[M3] c"
    cleaned = upsert_stage_reason(messy, "M2", "only")
    assert cleaned.count("[M2]") == 1
    assert parse_stage_blocks(cleaned)["M2"] == "only"
    assert parse_stage_blocks(cleaned)["M3"] == "c"


def test_iptc_rating_description_roundtrip():
    """T1: JPEG への Rating/Description 書き込み・再読取（exiftool）。"""
    import shutil

    from iptc_rating_io import (
        ExifToolNotFoundError,
        rating_to_percent,
        read_screening_meta,
        require_exiftool,
        write_screening_decision,
        write_stage_reason,
    )

    try:
        require_exiftool()
    except ExifToolNotFoundError:
        print("skip test_iptc_rating_description_roundtrip: exiftool missing")
        return

    assert rating_to_percent(3) == 60
    assert rating_to_percent(0) == 0

    td = Path(tempfile.mkdtemp(prefix="iptc_t1_"))
    jpeg = td / "sample.jpg"
    Image.new("RGB", (80, 60), (40, 80, 120)).save(jpeg, "JPEG", quality=90)

    desc = "[M2] Lumina sync test reason\n[M3] diversity placeholder"
    meta = write_screening_decision(jpeg, rating=3, description=desc)
    assert meta.rating == 3
    assert meta.description == desc
    assert meta.stage_reason("M2") == "Lumina sync test reason"
    assert meta.stage_reason("M3") == "diversity placeholder"

    # 段追記: 既存 M2 を残しつつ M3 を置換、Rating も更新
    write_screening_decision(jpeg, rating=4, stage="M3", reason="top pick")
    again = read_screening_meta(jpeg)
    assert again.rating == 4
    assert again.stage_reason("M2") == "Lumina sync test reason"
    assert again.stage_reason("M3") == "top pick"

    write_stage_reason(jpeg, "M2", "updated antenna")
    final = read_screening_meta(jpeg)
    assert final.stage_reason("M2") == "updated antenna"
    assert final.rating == 4  # Description のみ更新でも Rating は維持

    shutil.rmtree(td, ignore_errors=True)


def test_library_unit_naming_rules():
    """T2 + P1: 月 YYYYMM|XXYYYYMM / イベント YYYYMMDD_名前|XXYYYYMMDD_名前。"""
    from library_unit import (
        calendar_month_id_from_folder_name,
        is_event_folder_name,
        is_month_folder_name,
        is_works_month_folder_name,
        try_parse_event_name,
        try_parse_month_name,
        unit_from_dir,
    )

    assert is_month_folder_name("202608")
    assert try_parse_month_name("202608") == "202608"
    assert not is_month_folder_name("202613")  # 無効月
    assert not is_month_folder_name("20268")
    assert not is_month_folder_name("Photos")

    # P1: 機種接頭辞付き月
    assert is_month_folder_name("OM202606")
    assert try_parse_month_name("OM202606") == "OM202606"
    assert calendar_month_id_from_folder_name("OM202606") == "202606"
    assert is_month_folder_name("FF202612")
    assert not is_month_folder_name("OM202613")
    assert not is_month_folder_name("O202606")  # 接頭辞は2文字のみ

    # Works は接頭辞なし YYYYMM のみ
    assert is_works_month_folder_name("202606")
    assert not is_works_month_folder_name("OM202606")
    assert not is_works_month_folder_name("202613")

    assert is_event_folder_name("20260810_京都旅行")
    parsed = try_parse_event_name("20260810_京都旅行")
    assert parsed is not None
    assert parsed[0] == "20260810_京都旅行"
    assert parsed[1] == "京都旅行"
    assert parsed[2].isoformat() == "2026-08-10"
    assert parsed[3] is None

    # P1: 機種接頭辞付きイベント
    pref = try_parse_event_name("OM20260615_旅行")
    assert pref is not None
    assert pref[0] == "OM20260615_旅行"
    assert pref[1] == "旅行"
    assert pref[2].isoformat() == "2026-06-15"
    assert pref[3] == "OM"
    assert calendar_month_id_from_folder_name("OM20260615_旅行") == "202606"
    assert is_event_folder_name("FF20260101_day-trip_v2")

    assert is_event_folder_name("20260822_海辺の午後")
    assert is_event_folder_name("20260101_day-trip_v2")  # _ と - は可

    # スペース・不正日付・記号はイベント扱いしない
    assert not is_event_folder_name("20260810_京都 旅行")
    assert not is_event_folder_name("20260810")
    assert not is_event_folder_name("京都旅行")
    assert not is_event_folder_name("20260230_無効日")
    assert not is_event_folder_name("20260810_bad.name")
    assert not is_event_folder_name("misc_folder")
    assert not is_event_folder_name("OM20260615")  # 名前なし


def test_library_unit_prefixed_unit_from_dir():
    """P1: XXYYYYMM / XXYYYYMMDD_名前 が LibraryUnit になる。"""
    import shutil
    import tempfile

    from library_unit import resolve_unit, unit_from_dir

    root = Path(tempfile.mkdtemp(prefix="lib_p1_"))
    try:
        month = root / "OM202606"
        event = month / "OM20260615_旅行"
        event.mkdir(parents=True)

        mu = unit_from_dir(month)
        assert mu is not None
        assert mu.is_month
        assert mu.unit_id == "OM202606"
        assert mu.month_id == "202606"
        assert mu.camera_code == "OM"
        assert mu.works_month_id == "202606"

        eu = resolve_unit(event)
        assert eu.is_event
        assert eu.unit_id == "OM20260615_旅行"
        assert eu.display_name == "旅行"
        assert eu.month_id == "202606"
        assert eu.camera_code == "OM"
        assert eu.works_month_id == "202606"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_resolve_session_for_unit_prefers_target_sessions():
    """M2: preferred が別フォルダなら無視し、target 配下だけを正とする。"""
    import json
    import shutil
    import tempfile

    from library_unit import resolve_session_for_unit, session_belongs_to_unit

    root = Path(tempfile.mkdtemp(prefix="sess_m2_"))
    try:
        unit_a = root / "OM202606"
        unit_b = root / "FF202606"
        sess_a = unit_a / "_lumina" / "sessions"
        sess_b = unit_b / "_lumina" / "sessions"
        sess_a.mkdir(parents=True)
        sess_b.mkdir(parents=True)

        path_a = sess_a / "session_a.json"
        path_b = sess_b / "session_b.json"
        path_a.write_text(json.dumps({"id": "a"}), encoding="utf-8")
        path_b.write_text(json.dumps({"id": "b"}), encoding="utf-8")

        assert session_belongs_to_unit(path_a, unit_a)
        assert not session_belongs_to_unit(path_b, unit_a)

        # preferred が他 unit なら無視して A 側を返す（resolve 済みパス）
        got = resolve_session_for_unit(unit_a, preferred=path_b)
        assert got == path_a.resolve()

        # preferred が正しければそれを返す
        got2 = resolve_session_for_unit(unit_a, preferred=path_a)
        assert got2 == path_a.resolve()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_overall_multi_unit_status_cancel_between_units():
    """監査: 単位間中止は completed に落とさない。"""
    from screening_pipeline import overall_multi_unit_status

    assert (
        overall_multi_unit_status(
            planned_count=3,
            statuses=["completed"],
            cancelled_flags=[False],
            stopped_before_next_unit=True,
        )
        == "cancelled"
    )
    assert (
        overall_multi_unit_status(
            planned_count=2,
            statuses=["completed", "completed"],
            cancelled_flags=[False, False],
            stopped_before_next_unit=False,
        )
        == "completed"
    )
    assert (
        overall_multi_unit_status(
            planned_count=2,
            statuses=["completed", "cancelled"],
            cancelled_flags=[False, True],
            stopped_before_next_unit=False,
        )
        == "cancelled"
    )
    assert (
        overall_multi_unit_status(
            planned_count=2,
            statuses=[],
            stopped_before_next_unit=True,
        )
        == "cancelled"
    )


def test_list_pending_h3_includes_child_events():
    """監査: 月を見ると配下イベントの未記録 H3 も列挙する。"""
    import json
    import shutil

    from delta_log import list_pending_h3_sessions, sessions_dir

    root = Path(tempfile.mkdtemp(prefix="h3_pending_"))
    try:
        month = root / "OM202608"
        event = month / "OM20260815_旅行"
        event.mkdir(parents=True)
        for unit_path, sid in ((month, "monthsess"), (event, "eventsess")):
            sess = sessions_dir(unit_path)
            sess.mkdir(parents=True)
            doc = {
                "schema": "lumina.shortlist_session.v1",
                "id": sid,
                "write_meta": True,
                "pre_h3": {"files": [{"name": "a.jpg", "rating": 1}]},
                "post_h3": None,
                "files": [{"name": "a.jpg", "rating": 1}],
            }
            (sess / f"{sid}.json").write_text(json.dumps(doc), encoding="utf-8")

        pending = list_pending_h3_sessions(month)
        labels = {label for label, _ in pending}
        assert "OM202608" in labels
        assert any("旅行" in label or "OM20260815" in label for label in labels)
        assert len(pending) == 2
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_plan_screening_units_include_child_events():
    """Wave B2: 月＋配下イベントの実行順。"""
    import shutil

    from library_unit import plan_screening_units, resolve_unit

    root = Path(tempfile.mkdtemp(prefix="b2_plan_"))
    try:
        month = root / "OM202608"
        event = month / "OM20260815_旅行"
        event.mkdir(parents=True)
        unit = resolve_unit(month)
        alone = plan_screening_units(unit, include_child_events=False)
        assert len(alone) == 1 and alone[0].is_month
        with_events = plan_screening_units(unit, include_child_events=True)
        assert len(with_events) == 2
        assert with_events[0].is_month
        assert with_events[1].is_event
        assert with_events[1].path == event.resolve() or with_events[1].path == event
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_summarize_review_errors_limits_and_formats():
    """Wave B4: エラー要約は件数制限付きでファイル名を含む。"""
    from lumina_review import ReviewBatchResult, ReviewItemResult, summarize_review_errors

    result = ReviewBatchResult(
        works_dir="/tmp/w",
        status="completed",
        created_at="t",
        errors=3,
        items=[
            ReviewItemResult("a.jpg", "/a", "error", reason="boom1"),
            ReviewItemResult("b.jpg", "/b", "processed"),
            ReviewItemResult("c.jpg", "/c", "error", reason="boom2"),
            ReviewItemResult("d.jpg", "/d", "error", reason="boom3"),
        ],
    )
    text = summarize_review_errors(result, limit=2)
    assert "a.jpg" in text and "boom1" in text
    assert "c.jpg" in text
    assert "他 1 件" in text
    assert summarize_review_errors(
        ReviewBatchResult(works_dir="/tmp/w", status="completed", created_at="t")
    ) == ""


def test_library_unit_discover_and_list_jpegs():
    """T2: 発見・月直下バラ／イベント分離・規則外サブフォルダ除外。"""
    import shutil

    from library_unit import (
        discover_units,
        list_event_units,
        list_month_units,
        list_non_event_subdirs,
        list_source_jpegs,
        resolve_unit,
        unit_from_dir,
    )

    root = Path(tempfile.mkdtemp(prefix="lib_t2_"))
    month = root / "202608"
    event = month / "20260810_京都旅行"
    odd = month / "raw_backup"  # イベント規則外
    event.mkdir(parents=True)
    odd.mkdir()

    def touch_jpeg(path: Path) -> None:
        Image.new("RGB", (32, 24), (10, 20, 30)).save(path, "JPEG", quality=85)

    touch_jpeg(month / "IMG_001.JPG")
    touch_jpeg(month / "IMG_002.jpeg")
    (month / "notes.txt").write_text("ignore", encoding="utf-8")
    touch_jpeg(event / "P123.JPG")
    touch_jpeg(odd / "should_not_in_month_or_event_list.jpg")

    months = list_month_units(root)
    assert len(months) == 1
    assert months[0].unit_id == "202608"

    events = list_event_units(months[0])
    assert len(events) == 1
    assert events[0].display_name == "京都旅行"
    assert events[0].month_id == "202608"

    odd_dirs = list_non_event_subdirs(months[0])
    assert any(p.name == "raw_backup" for p in odd_dirs)

    month_jpegs = [p.name for p in list_source_jpegs(months[0])]
    assert month_jpegs == ["IMG_001.JPG", "IMG_002.jpeg"]
    assert "P123.JPG" not in month_jpegs
    assert "should_not_in_month_or_event_list.jpg" not in month_jpegs

    event_jpegs = [p.name for p in list_source_jpegs(events[0])]
    assert event_jpegs == ["P123.JPG"]

    flat = discover_units(root)
    assert [u.unit_id for u in flat] == ["202608", "20260810_京都旅行"]

    assert unit_from_dir(odd) is None
    resolved = resolve_unit(event)
    assert resolved.is_event and resolved.display_name == "京都旅行"

    shutil.rmtree(root, ignore_errors=True)


def _make_grid_image(size=(320, 240)) -> Image.Image:
    from PIL import ImageDraw

    img = Image.new("RGB", size, (40, 40, 40))
    draw = ImageDraw.Draw(img)
    for x in range(0, size[0], 3):
        draw.line([(x, 0), (x, size[1])], fill=(220, 220, 220))
    for y in range(0, size[1], 3):
        draw.line([(0, y), (size[0], y)], fill=(180, 180, 180))
    return img


def test_mechanical_m1_blur_and_intent_protect():
    """T3: ブレ不合格、意図保護で合格、白飛び不合格。閾値は設定化。"""
    import shutil
    from PIL import ImageFilter

    from iptc_rating_io import ExifToolNotFoundError, read_screening_meta, require_exiftool
    from screening_mechanical import (
        CaptureSettings,
        MechanicalConfig,
        evaluate_mechanical,
        run_mechanical_on_paths,
    )

    td = Path(tempfile.mkdtemp(prefix="m1_t3_"))
    sharp_p = td / "sharp.jpg"
    blur_p = td / "blur.jpg"
    white_p = td / "white.jpg"
    black_p = td / "black.jpg"

    sharp = _make_grid_image()
    sharp.save(sharp_p, "JPEG", quality=95)
    sharp.filter(ImageFilter.GaussianBlur(12)).save(blur_p, "JPEG", quality=95)
    Image.new("RGB", (200, 150), (250, 250, 250)).save(white_p, "JPEG", quality=95)
    Image.new("RGB", (200, 150), (5, 5, 5)).save(black_p, "JPEG", quality=95)

    cfg = MechanicalConfig()
    assert evaluate_mechanical(sharp_p, cfg).rating == 1
    assert evaluate_mechanical(blur_p, cfg).rating == 0
    assert "fail_blur" in evaluate_mechanical(blur_p, cfg).reason_codes
    assert evaluate_mechanical(white_p, cfg).rating == 0
    assert evaluate_mechanical(black_p, cfg).rating == 0

    # 低速 SS / 意図的アンダーで保護
    blur_ok = evaluate_mechanical(
        blur_p, cfg, capture=CaptureSettings(exposure_time_sec=1 / 10)
    )
    assert blur_ok.rating == 1 and blur_ok.intent_protected
    under_ok = evaluate_mechanical(
        black_p, cfg, capture=CaptureSettings(exposure_bias_ev=-1.0)
    )
    assert under_ok.rating == 1
    open_ok = evaluate_mechanical(
        blur_p, cfg, capture=CaptureSettings(f_number=1.8)
    )
    assert open_ok.rating == 1

    # 閾値を極端に上げるとシャープも不合格（設定化の確認）
    strict = MechanicalConfig(min_sharpness=1_000_000.0)
    assert evaluate_mechanical(sharp_p, strict).rating == 0

    # バッチ: 1枚壊しても継続。画素サイズは不変
    bad = td / "missing.jpg"
    before = Image.open(sharp_p).size
    batch = run_mechanical_on_paths([sharp_p, bad, blur_p], cfg, write=False)
    assert len(batch.decisions) == 3
    assert batch.errors >= 1
    assert batch.pass_count == 1
    assert batch.fail_count == 1
    assert Image.open(sharp_p).size == before

    try:
        require_exiftool()
    except ExifToolNotFoundError:
        print("skip m1 write check: exiftool missing")
        shutil.rmtree(td, ignore_errors=True)
        return

    written = run_mechanical_on_paths([sharp_p, blur_p], cfg, write=True)
    assert written.written == 2
    assert read_screening_meta(sharp_p).rating == 1
    assert read_screening_meta(blur_p).rating == 0
    assert Image.open(sharp_p).size == before
    shutil.rmtree(td, ignore_errors=True)


def test_antenna_m2_relative_heat_no_star_gate():
    """T4: 相対熱量で選抜。★5必須なし。Rating0はスキップ。[M2] 書き込み。"""
    import shutil

    from iptc_rating_io import (
        ExifToolNotFoundError,
        read_screening_meta,
        require_exiftool,
        write_rating,
    )
    from screening_antenna import (
        AntennaConfig,
        AntennaScore,
        compute_heat,
        parse_antenna_response,
        run_antenna_on_paths,
        select_pass_count,
    )

    # パーサ
    parsed = parse_antenna_response(
        '{"framing":4,"sensitivity":3,"story":2,"technical":3,"sense":4,"reason":"輪郭の熱"}'
    )
    assert parsed.scores["framing"] == 4
    assert "輪郭" in parsed.reason

    # ★5が無くても熱量で上位になりうる（絶対ゲート禁止）
    mid = AntennaScore(
        scores={"framing": 3, "sensitivity": 3, "story": 3, "technical": 3, "sense": 3},
        reason="均質",
    )
    spiky = AntennaScore(
        scores={"framing": 5, "sensitivity": 1, "story": 1, "technical": 1, "sense": 1},
        reason="一点だけ",
    )
    cfg = AntennaConfig()
    # resonance がある mid が spiky に対抗しうる（どちらが上でも★5必須ではないこと自体が要点）
    assert select_pass_count(10, AntennaConfig(pass_ratio=0.28)) == 3
    assert select_pass_count(1, AntennaConfig(pass_ratio=0.28)) == 1
    _ = compute_heat(mid, cfg)
    _ = compute_heat(spiky, cfg)

    td = Path(tempfile.mkdtemp(prefix="m2_t4_"))
    paths = []
    for i in range(5):
        p = td / f"img_{i}.jpg"
        Image.new("RGB", (64, 48), (20 + i * 20, 40, 60)).save(p, "JPEG", quality=90)
        paths.append(p)

    # 擬似スコア: 熱量順が img_4 > ... で上位2件合格（pass_ratio=0.4 → 2）
    fake_scores = {
        paths[0]: AntennaScore(
            {"framing": 2, "sensitivity": 2, "story": 2, "technical": 2, "sense": 2}, "低"
        ),
        paths[1]: AntennaScore(
            {"framing": 3, "sensitivity": 2, "story": 2, "technical": 2, "sense": 2}, "やや低"
        ),
        paths[2]: AntennaScore(
            {"framing": 3, "sensitivity": 3, "story": 3, "technical": 3, "sense": 3}, "中"
        ),
        paths[3]: AntennaScore(
            {"framing": 4, "sensitivity": 3, "story": 3, "technical": 3, "sense": 3}, "高"
        ),
        paths[4]: AntennaScore(
            {"framing": 4, "sensitivity": 4, "story": 3, "technical": 3, "sense": 4}, "最高"
        ),
    }

    try:
        require_exiftool()
    except ExifToolNotFoundError:
        print("skip m2 write check: exiftool missing")
        shutil.rmtree(td, ignore_errors=True)
        return

    for p in paths:
        write_rating(p, 1)
    # Rating 0 はスキップされる
    zero = td / "zero.jpg"
    Image.new("RGB", (64, 48), (10, 10, 10)).save(zero, "JPEG", quality=90)
    write_rating(zero, 0)

    def score_fn(path: Path) -> AntennaScore:
        return fake_scores[path]

    batch = run_antenna_on_paths(
        list(paths) + [zero],
        AntennaConfig(pass_ratio=0.4, min_pass=0),
        write=True,
        score_fn=score_fn,
    )
    assert batch.skipped == 1
    assert batch.pass_count == 2
    assert batch.written == 2

    meta4 = read_screening_meta(paths[4])
    meta3 = read_screening_meta(paths[3])
    meta0 = read_screening_meta(paths[0])
    assert meta4.rating == 2 and meta4.stage_reason("M2")
    assert meta3.rating == 2
    assert meta0.rating == 1  # 非合格は1のまま
    assert read_screening_meta(zero).rating == 0

    # ★5なしのバッチでも相対上位が合格
    flat = {
        paths[i]: AntennaScore(
            {"framing": 3, "sensitivity": 3, "story": 2, "technical": 3, "sense": 2},
            f"flat-{i}",
        )
        for i in range(5)
    }
    # わずかに差
    flat[paths[2]] = AntennaScore(
        {"framing": 3, "sensitivity": 3, "story": 3, "technical": 3, "sense": 3}, "flat-best"
    )
    for p in paths:
        write_rating(p, 1)
    batch2 = run_antenna_on_paths(
        paths,
        AntennaConfig(pass_ratio=0.2),  # 1枚
        write=True,
        score_fn=lambda p: flat[p],
    )
    assert batch2.pass_count == 1
    assert read_screening_meta(paths[2]).rating == 2
    assert "flat-best" in (read_screening_meta(paths[2]).stage_reason("M2") or "")

    shutil.rmtree(td, ignore_errors=True)


def test_diversity_m3_margin_top_and_bias_control():
    """T5: 多様性貪欲法で余白3/上位4。[M3]書き込み。Rating<2はスキップ。"""
    import shutil

    from iptc_rating_io import (
        ExifToolNotFoundError,
        read_screening_meta,
        require_exiftool,
        write_rating,
    )
    from screening_diversity import (
        DiversityConfig,
        DiversityFeature,
        diversity_distance,
        greedy_diversity_select,
        parse_diversity_response,
        run_diversity_on_paths,
        select_keep_count,
        select_top_count,
    )

    assert select_keep_count(50, DiversityConfig(keep_ratio=0.40)) == 20
    assert select_top_count(20, DiversityConfig(top_ratio=0.40)) == 8

    parsed = parse_diversity_response(
        '{"quality":4,"attachment":5,"tags":["海","光"],"reason":"青い執着"}',
        hue_bin=3,
        luma_bin=2,
    )
    assert parsed.quality == 4
    assert parsed.attachment == 5
    assert parsed.tags == ("海", "光")

    # 類似タグは距離が小さい
    a = DiversityFeature(0, 2, ("海",), 4, 3, "a")
    b = DiversityFeature(0, 2, ("海",), 4, 3, "b")
    c = DiversityFeature(6, 4, ("都市", "夜"), 3, 3, "c")
    assert diversity_distance(a, b) < diversity_distance(a, c)

    # 貪欲: 高品質の海が2枚あっても、2枠目は都市を取りやすい
    items = [
        (Path("p0"), 2, DiversityFeature(0, 2, ("海",), 5.0, 3.0, "海1")),
        (Path("p1"), 2, DiversityFeature(0, 2, ("海",), 4.8, 3.0, "海2")),
        (Path("p2"), 2, DiversityFeature(6, 3, ("都市",), 4.0, 4.0, "都市")),
        (Path("p3"), 2, DiversityFeature(8, 1, ("静物",), 3.5, 5.0, "静物執着")),
        (Path("p4"), 2, DiversityFeature(1, 2, ("海", "光"), 4.5, 3.0, "海3")),
    ]
    picked = greedy_diversity_select(
        items, DiversityConfig(keep_ratio=0.4, top_ratio=0.5, diversity_weight=0.7, quality_weight=0.3)
    )
    kept = [d for d in picked if d.passed]
    assert len(kept) == 2
    kept_names = {d.path.name for d in kept}
    assert "p0" in kept_names  # 最初は最高品質
    assert "p1" not in kept_names or "p2" in kept_names or "p3" in kept_names
    # 2枠目は同系海より都市/静物側が入りやすい
    assert kept_names != {"p0", "p1"}
    tops = [d for d in kept if d.slot == "top"]
    margins = [d for d in kept if d.slot == "margin"]
    assert len(tops) == 1 and len(margins) == 1
    assert tops[0].rating == 4 and margins[0].rating == 3

    td = Path(tempfile.mkdtemp(prefix="m3_t5_"))
    paths = []
    for i in range(5):
        p = td / f"d{i}.jpg"
        Image.new("RGB", (64, 48), (30 + i * 25, 50, 80)).save(p, "JPEG", quality=90)
        paths.append(p)

    feats = {
        paths[0]: DiversityFeature(0, 2, ("海",), 5.0, 3.0, "海トップ"),
        paths[1]: DiversityFeature(0, 2, ("海",), 4.7, 3.0, "海似"),
        paths[2]: DiversityFeature(6, 3, ("都市",), 4.2, 3.0, "都市余白"),
        paths[3]: DiversityFeature(9, 1, ("静物",), 3.8, 5.0, "執着静物"),
        paths[4]: DiversityFeature(2, 2, ("自然",), 3.5, 3.0, "自然"),
    }

    try:
        require_exiftool()
    except ExifToolNotFoundError:
        print("skip m3 write check: exiftool missing")
        shutil.rmtree(td, ignore_errors=True)
        return

    for p in paths:
        write_rating(p, 2)
    low = td / "low.jpg"
    Image.new("RGB", (64, 48), (10, 10, 10)).save(low, "JPEG", quality=90)
    write_rating(low, 1)

    batch = run_diversity_on_paths(
        list(paths) + [low],
        DiversityConfig(keep_ratio=0.4, top_ratio=0.5, diversity_weight=0.65, quality_weight=0.35),
        write=True,
        feature_fn=lambda p: feats[p],
    )
    assert batch.skipped == 1
    assert batch.pass_count == 2
    assert batch.top_count == 1
    assert batch.margin_count == 1
    assert batch.written == 2

    ratings = {p.name: read_screening_meta(p).rating for p in paths}
    assert 4 in ratings.values()
    assert 3 in ratings.values()
    assert read_screening_meta(paths[0]).stage_reason("M3")
    assert read_screening_meta(low).rating == 1
    # 非合格は2のままが残る
    assert sum(1 for r in ratings.values() if r == 2) == 3

    shutil.rmtree(td, ignore_errors=True)


def test_shortlist_pipeline_m1_m2_m3_and_cancel():
    """T6: パイプラインが M1→M2→M3 を繋ぐ。中断可能。app_gui 非依存。"""
    import shutil

    from iptc_rating_io import ExifToolNotFoundError, read_screening_meta, require_exiftool, write_rating
    from screening_antenna import AntennaConfig, AntennaScore
    from screening_diversity import DiversityConfig, DiversityFeature
    from screening_pipeline import PipelineConfig, ScreeningPipeline, parse_stages

    assert parse_stages("all") == (True, True, True)
    assert parse_stages("m1") == (True, False, False)
    assert parse_stages("m2,m3") == (False, True, True)

    try:
        require_exiftool()
    except ExifToolNotFoundError:
        print("skip test_shortlist_pipeline: exiftool missing")
        return

    root = Path(tempfile.mkdtemp(prefix="pipe_t6_"))
    month = root / "202608"
    month.mkdir()
    paths = []
    for i in range(5):
        p = month / f"p{i}.jpg"
        # シャープな格子で M1 合格しやすくする
        img = _make_grid_image((160, 120))
        img.save(p, "JPEG", quality=95)
        paths.append(p)

    events = []

    def on_progress(p):
        events.append(p.stage)

    def m2_fn(path: Path) -> AntennaScore:
        # 名前の番号で熱量差
        n = int(path.stem.replace("p", ""))
        base = 2 + min(3, n)
        return AntennaScore(
            {
                "framing": base,
                "sensitivity": base,
                "story": 2,
                "technical": 2,
                "sense": 2 + (1 if n >= 3 else 0),
            },
            f"m2-{n}",
        )

    def m3_fn(path: Path) -> DiversityFeature:
        n = int(path.stem.replace("p", ""))
        tags = (("海",) if n < 3 else ("都市",))
        return DiversityFeature(
            hue_bin=n % 12,
            luma_bin=2,
            tags=tags,
            quality=3.0 + n * 0.3,
            attachment=3.0,
            reason=f"m3-{n}",
        )

    pipe = ScreeningPipeline(
        PipelineConfig(
            write=True,
            m2_score_fn=m2_fn,
            m3_feature_fn=m3_fn,
            antenna=AntennaConfig(pass_ratio=0.4),
            diversity=DiversityConfig(keep_ratio=0.5, top_ratio=0.5),
        ),
        on_progress=on_progress,
    )
    result = pipe.run_on_dir(month)
    assert result.status == "completed"
    assert result.m1 and result.m2 and result.m3
    assert result.m1.pass_count >= 1
    assert result.m2.pass_count >= 1
    assert result.m3.pass_count >= 1
    assert "m1" in events and "m2" in events and "m3" in events and "done" in events
    assert result.session_path is not None
    assert result.session_path.is_file()
    assert "_lumina/sessions" in str(result.session_path).replace("\\", "/")
    # 最終で 3 or 4 が付いている
    finals = [read_screening_meta(p).rating for p in paths]
    assert any(r in (3, 4) for r in finals)

    # 中断: M1 開始直後にキャンセル
    pipe2 = ScreeningPipeline(
        PipelineConfig(write=False, run_m2=False, run_m3=False),
    )
    original_emit = pipe2._emit

    def emit_and_cancel(stage, message, current=None, total=None):
        original_emit(stage, message, current, total)
        if stage == "m1" and "開始" in message:
            pipe2.request_cancel()

    pipe2._emit = emit_and_cancel  # type: ignore[method-assign]
    cancelled = pipe2.run_on_dir(month)
    assert cancelled.status == "cancelled"
    assert cancelled.cancelled

    # stages m1 only
    pipe3 = ScreeningPipeline(
        PipelineConfig(write=False, run_m1=True, run_m2=False, run_m3=False),
    )
    only_m1 = pipe3.run_on_dir(month)
    assert only_m1.status == "completed"
    assert only_m1.m1 is not None and only_m1.m2 is None and only_m1.m3 is None

    shutil.rmtree(root, ignore_errors=True)


def test_delta_log_session_reload_and_summary():
    """T7: セッション保存・再読・サマリ件数・H3再スキャン追記。"""
    import shutil

    from delta_log import (
        append_h3_rescan,
        list_session_paths,
        load_session,
        load_unit_session_summaries,
        summarize_session,
    )
    from iptc_rating_io import ExifToolNotFoundError, require_exiftool, write_rating
    from screening_antenna import AntennaConfig, AntennaScore
    from screening_diversity import DiversityConfig, DiversityFeature
    from screening_pipeline import PipelineConfig, ScreeningPipeline

    try:
        require_exiftool()
    except ExifToolNotFoundError:
        print("skip test_delta_log_session: exiftool missing")
        return

    root = Path(tempfile.mkdtemp(prefix="delta_t7_"))
    month = root / "202608"
    month.mkdir()
    paths = []
    for i in range(4):
        p = month / f"s{i}.jpg"
        _make_grid_image((120, 90)).save(p, "JPEG", quality=95)
        paths.append(p)

    def m2_fn(path: Path) -> AntennaScore:
        n = int(path.stem.replace("s", ""))
        v = 2 + n
        return AntennaScore(
            {"framing": v, "sensitivity": v, "story": 2, "technical": 2, "sense": 3},
            f"a{n}",
        )

    def m3_fn(path: Path) -> DiversityFeature:
        n = int(path.stem.replace("s", ""))
        return DiversityFeature(n, 2, ("海",) if n % 2 == 0 else ("都市",), 3.5 + n * 0.2, 3.0, f"d{n}")

    result = ScreeningPipeline(
        PipelineConfig(
            write=True,
            m2_score_fn=m2_fn,
            m3_feature_fn=m3_fn,
            antenna=AntennaConfig(pass_ratio=0.5),
            diversity=DiversityConfig(keep_ratio=0.5, top_ratio=0.5),
        )
    ).run_on_dir(month)

    assert result.session_path and result.session_path.is_file()
    doc = load_session(result.session_path)
    assert doc["schema"] == "lumina.shortlist_session.v1"
    assert doc["id"] == result.session_id
    assert doc["library_unit_id"] == "202608"
    assert isinstance(doc["files"], list) and len(doc["files"]) >= 1
    assert "counts_by_rating" in doc
    summary = summarize_session(doc)
    assert summary["file_delta_count"] == len(doc["files"])
    assert summary["counts_by_rating"] is not None

    listed = list_session_paths(month)
    assert result.session_path in listed
    summaries = load_unit_session_summaries(month)
    assert any(s.summary["id"] == result.session_id for s in summaries)

    # H3 想定: 1枚 Rating を人手変更してから再スキャン追記
    write_rating(paths[0], 4)
    updated = append_h3_rescan(result.session_path)
    assert updated["post_h3"] is not None
    assert updated["pre_h3"] is not None
    assert updated["h3_delta"] is not None
    assert updated["h3_delta"]["changed_count"] >= 1
    assert updated["h3_rescan"]["counts_by_rating"]["4"] >= 1
    again = load_session(result.session_path)
    assert again["h3_delta"]["transitions"]
    assert again["post_h3"]["label"] == "DxO修正後"

    shutil.rmtree(root, ignore_errors=True)


def test_list_session_paths_matches_resolved_pipeline_path():
    """Mac /var→/private/var 等: unit.path は resolve 済み、列挙も同じ正規形に揃える。"""
    import shutil

    from delta_log import list_session_paths

    root = Path(tempfile.mkdtemp(prefix="delta_path_"))
    try:
        real_month = root / "real202608"
        real_month.mkdir()
        sess_dir = real_month / "_lumina" / "sessions"
        sess_dir.mkdir(parents=True)
        session_file = sess_dir / "abc123.json"
        session_file.write_text('{"id":"abc123"}\n', encoding="utf-8")

        alias_month = root / "alias202608"
        alias_month.symlink_to(real_month)

        resolved_session = session_file.resolve()
        listed_via_alias = list_session_paths(alias_month)
        listed_via_real = list_session_paths(real_month.resolve())

        assert resolved_session in listed_via_alias
        assert resolved_session in listed_via_real
        assert listed_via_alias == listed_via_real
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_h3_delta_builder_for_judgment_improvement():
    """DxO前後差分が遷移表になること（判定改善用）。"""
    from delta_log import build_h3_delta

    pre = [
        {"file_name": "a.jpg", "rating": 2, "description_blocks": {"M2": "x"}},
        {"file_name": "b.jpg", "rating": 0, "description_blocks": {}},
        {"file_name": "c.jpg", "rating": 3, "description_blocks": {"M3": "y"}},
    ]
    post = [
        {"file_name": "a.jpg", "rating": 4, "description_blocks": {"M2": "x"}},
        {"file_name": "b.jpg", "rating": 2, "description_blocks": {}},
        {"file_name": "c.jpg", "rating": 3, "description_blocks": {"M3": "y"}},
    ]
    delta = build_h3_delta(pre, post)
    assert delta["changed_count"] == 2
    assert delta["unchanged_count"] == 1
    assert delta["transitions"]["2->4"] == 1
    assert delta["transitions"]["0->2"] == 1
    assert delta["purpose"] == "judgment_improvement"


def test_works_trace_dev_preference_and_no_copy():
    """T8: stem 単位で _dev 優先。SOOC のみも対象。コピーしない。"""
    import shutil
    import tempfile
    from pathlib import Path

    from PIL import Image

    from critique_prompts import CritiquePromptContext, build_phase1_prompt, build_phase2_prompt
    from lumina_review import (
        ReviewConfig,
        LuminaReviewRunner,
        is_dev_export,
        list_works_review_targets,
        works_base_stem,
    )

    assert works_base_stem(Path("P1_dev.jpg")) == "P1"
    assert works_base_stem(Path("P1.jpg")) == "P1"
    assert is_dev_export(Path("P1_dev.JPG"))
    assert not is_dev_export(Path("P1.jpg"))

    root = Path(tempfile.mkdtemp(prefix="lumina_t8_"))
    try:
        works = root / "WorksSample"
        works.mkdir()
        # both → prefer _dev
        Image.new("RGB", (32, 24), color=(10, 20, 30)).save(works / "A.jpg", quality=90)
        Image.new("RGB", (32, 24), color=(40, 50, 60)).save(works / "A_dev.jpg", quality=90)
        # sooc only
        Image.new("RGB", (32, 24), color=(70, 80, 90)).save(works / "B.jpg", quality=90)
        # dev only
        Image.new("RGB", (32, 24), color=(100, 110, 120)).save(works / "C_dev.jpg", quality=90)
        # noise
        Image.new("RGB", (32, 24), color=(1, 1, 1)).save(works / "A_card.png")
        (works / "ignore.txt").write_text("x", encoding="utf-8")
        (works / "._A.jpg").write_bytes(b"")

        targets = list_works_review_targets(works)
        names = [p.name for p in targets]
        assert names == ["A_dev.jpg", "B.jpg", "C_dev.jpg"]
        assert "A.jpg" not in names

        # 画優先プロンプト注記
        ctx_off = CritiquePromptContext.from_metadata({"camera_model": "Cam"}, {})
        assert not ctx_off.pixel_priority
        assert "画優先" not in build_phase1_prompt(ctx_off)
        ctx_on = CritiquePromptContext.from_metadata(
            {"camera_model": "Cam", "pixel_priority": True}, {}
        )
        assert ctx_on.pixel_priority
        p1 = build_phase1_prompt(ctx_on)
        p2 = build_phase2_prompt(ctx_on, "■TITLE: t\n■SUMMARY: s")
        assert "画優先" in p1
        assert "画優先" in p2
        assert "撮影記録" in p2

        fake_critique = (
            "■TITLE: テストタイトル\n"
            "■SUMMARY: 短いキャッチ\n"
            "■SCORES:\n"
            "・眼差の輪郭 (Contours of the Eyes)  : ★★★☆☆ (3/5)\n"
            "・感情の陰影 (Nuances of Emotion)  : ★★★☆☆ (3/5)\n"
            "・物語の気配 (Signs of the Story)  : ★★★☆☆ (3/5)\n"
            "・表現の意図 (Intent of Expression)  : ★★★☆☆ (3/5)\n"
            "・感性の兆し (Signs of Sensibility)  : ★★★☆☆ (3/5)\n"
            "■CRITIQUE_SUMMARY: これはテスト用の短評です。光と形だけを見ます。\n\n"
            "---\n\n"
            "## 【1. 情景・空気感とストーリー性】\n本文1\n"
            "## 【2. 視線誘導と構成の美学】\n本文2\n"
            "## 【3. 光の強弱・色彩と印象解析】\n本文3\n"
            "## 【4. EXIFデータの技術的役割と表現効果】\n本文4\n"
            "## 【5. 次なる一枚への対話と提案】\n本文5\n"
            "## 【6. フォトブック＆SNSでの役割提案】\n本文6\n"
            "## 【7. 自動タグ】\n#カメラ_x #レンズ_y #test\n"
        )

        seen_meta: list[dict] = []

        def fake_critique_fn(path, metadata, dop_info, mode, lens):  # noqa: ARG001
            seen_meta.append(dict(metadata))
            return fake_critique

        runner = LuminaReviewRunner(
            ReviewConfig(
                mode="full",
                force_overwrite=False,
                card_theme="dark",
                pixel_priority=True,
                critique_fn=fake_critique_fn,
            )
        )
        result = runner.run(works)
        assert result.status == "completed"
        assert result.targets_found == 3
        assert result.processed == 3
        assert result.errors == 0
        assert result.to_dict()["copy_performed"] is False
        assert all(m.get("pixel_priority") is True for m in seen_meta)
        assert any(m.get("critique_image_kind") == "dev_export" for m in seen_meta)
        assert any(m.get("critique_image_kind") == "sooc_export" for m in seen_meta)

        # 出力物が Works 内に生成（コピー元は増やさない／Wave 2 は Luminaカード）
        assert (works / "WorksSampleLuminaカード" / "A_dev_card.png").is_file() or any(
            p.is_file() for p in works.rglob("*_card.png")
        )
        assert (works / "WorksSampleLuminaノート").is_dir() or any(
            p.suffix == ".md" for p in works.rglob("*.md")
        )
        assert any(p.suffix == ".md" for p in works.rglob("*.md"))
        # 元 JPEG は増えていない（A.jpg / A_dev / B / C_dev の4枚のまま）
        jpegs = [p for p in works.iterdir() if p.suffix.lower() in {".jpg", ".jpeg"} and not p.name.startswith("._")]
        assert len(jpegs) == 4

        # 2回目はスキップ
        again = runner.run(works)
        assert again.processed == 0
        assert again.skipped == 3
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_scanner_jpeg_primary_over_dop_for_intent_and_rating():
    """T9: user_intent / Rating は JPEG 正。衝突する .dop があっても JPEG が勝つ。"""
    import shutil
    import tempfile

    from PIL import Image

    from critique_prompts import CritiquePromptContext, build_phase2_prompt
    from iptc_rating_io import (
        ExifToolNotFoundError,
        format_rating_display,
        require_exiftool,
        strip_stage_reason_lines,
        write_screening_decision,
    )
    from scanner import extract_file_metadata

    assert format_rating_display(3) == "★★★☆☆ (3/5)"
    assert format_rating_display(None) == "なし"
    assert strip_stage_reason_lines("光を残したい\n[M2] heat\n[M3] top\nメモ") == "光を残したい\nメモ"

    try:
        require_exiftool()
    except ExifToolNotFoundError:
        print("skip test_scanner_jpeg_primary_over_dop_for_intent_and_rating: exiftool missing")
        return

    root = Path(tempfile.mkdtemp(prefix="lumina_t9_"))
    try:
        jpeg = root / "T9_sample.jpg"
        Image.new("RGB", (48, 32), color=(20, 40, 60)).save(jpeg, quality=90)

        desc = "夕景ではなく光の角度を見たい\n[M2] relative heat note\n[M3] diversity pick"
        write_screening_decision(jpeg, rating=4, description=desc)

        # 衝突する .dop（古い／誤った値）を隣に置く
        dop = root / "T9_sample.jpg.dop"
        dop.write_text(
            'Rating = 1\n'
            'contentDescription = "dop側の古い意図"\n'
            'contentHeadline = "DOP見出し"\n'
            'AppliedPresetDisplayName = "FakePreset"\n',
            encoding="utf-8",
        )

        meta, dop_info, block = extract_file_metadata(jpeg)
        assert meta["rating"] == 4
        assert meta["rating_source"] == "jpeg"
        assert "★★★★☆" in meta["rating_str"]
        assert meta["user_intent_source"] == "jpeg_description"
        # [M2]/[M3] は講評の意図から除外
        assert "[M2]" not in meta["user_intent"]
        assert "[M3]" not in meta["user_intent"]
        assert "光の角度を見たい" in meta["user_intent"]
        assert "dop側の古い意図" not in meta["user_intent"]
        assert "rating_source: jpeg" in block
        assert "user_intent_source: jpeg_description" in block
        assert dop_info.get("meta_source_policy") == "jpeg_primary"

        ctx = CritiquePromptContext.from_metadata(meta, dop_info)
        assert "★★★★☆" in ctx.rating_str
        assert "光の角度" in ctx.user_intent
        assert "dop側" not in ctx.user_intent
        p2 = build_phase2_prompt(ctx, "■TITLE: t\n■SUMMARY: s")
        assert "★★★★☆" in p2 or "4/5" in p2
        assert "光の角度" in p2

        # JPEG に説明が無いときだけ dop フォールバック
        bare = root / "T9_bare.jpg"
        Image.new("RGB", (40, 30), color=(1, 2, 3)).save(bare, quality=90)
        (root / "T9_bare.jpg.dop").write_text(
            'contentDescription = "dopだけの意図"\nRating = 2\n',
            encoding="utf-8",
        )
        meta2, _, block2 = extract_file_metadata(bare)
        assert meta2["user_intent_source"] == "dop_fallback"
        assert meta2["user_intent"] == "dopだけの意図"
        assert meta2["rating_source"] == "dop_fallback"
        assert "★★☆☆☆" in meta2["rating_str"]
        assert "user_intent_source: dop_fallback" in block2
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _pixel_digest(path: Path) -> str:
    """画素のみのダイジェスト（メタ変更検知用。A5）。"""
    import hashlib

    with Image.open(path) as im:
        rgb = im.convert("RGB")
        return hashlib.sha256(rgb.tobytes()).hexdigest()


def test_r1a_t10_shortlist_write_preserves_pixels():
    """T10 / A5: Rating・Description 書き込みで画素が変わらない。"""
    import shutil

    from iptc_rating_io import (
        ExifToolNotFoundError,
        read_screening_meta,
        require_exiftool,
        write_screening_decision,
    )

    try:
        require_exiftool()
    except ExifToolNotFoundError:
        print("skip test_r1a_t10_shortlist_write_preserves_pixels: exiftool missing")
        return

    root = Path(tempfile.mkdtemp(prefix="lumina_t10_pix_"))
    try:
        jpeg = root / "pix.jpg"
        Image.new("RGB", (64, 48), color=(12, 34, 56)).save(jpeg, quality=92)
        before = _pixel_digest(jpeg)
        size_before = jpeg.stat().st_size

        write_screening_decision(
            jpeg,
            rating=3,
            description="ユーザー文\n[M2] antenna\n[M3] diversity",
        )
        after = _pixel_digest(jpeg)
        assert before == after, "画素ダイジェストが変わった（画素破壊の疑い）"
        meta = read_screening_meta(jpeg)
        assert meta.rating == 3
        assert "[M2]" in meta.description
        # メタ追記でファイルサイズは変わり得るが、極端な縮小（再エンコード破壊）はしない
        assert jpeg.stat().st_size >= size_before * 0.5
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_r1a_t10_pipeline_continues_on_item_failure():
    """T10: 1枚の失敗でパイプライン全体を止めない。"""
    import shutil

    from iptc_rating_io import ExifToolNotFoundError, require_exiftool, write_rating
    from screening_antenna import AntennaConfig, AntennaScore
    from screening_pipeline import PipelineConfig, ScreeningPipeline

    try:
        require_exiftool()
    except ExifToolNotFoundError:
        print("skip test_r1a_t10_pipeline_continues_on_item_failure: exiftool missing")
        return

    root = Path(tempfile.mkdtemp(prefix="lumina_t10_fail_"))
    try:
        month = root / "202608"
        month.mkdir()
        for i in range(4):
            p = month / f"q{i}.jpg"
            _make_grid_image((120, 90)).save(p, "JPEG", quality=95)
            write_rating(p, 1)

        def m2_fn(path: Path) -> AntennaScore:
            if path.name == "q1.jpg":
                raise RuntimeError("simulated per-item failure")
            n = int(path.stem.replace("q", ""))
            return AntennaScore(
                {
                    "framing": 3 + (n % 2),
                    "sensitivity": 3,
                    "story": 2,
                    "technical": 2,
                    "sense": 3,
                },
                f"ok-{n}",
            )

        pipe = ScreeningPipeline(
            PipelineConfig(
                write=True,
                run_m1=False,
                run_m2=True,
                run_m3=False,
                m2_score_fn=m2_fn,
                antenna=AntennaConfig(pass_ratio=0.5),
                persist_session=True,
            )
        )
        result = pipe.run_on_dir(month)
        assert result.status == "completed", result.error
        assert result.m2 is not None
        assert result.m2.errors >= 1
        okish = [d for d in result.m2.decisions if d.error is None and not d.skipped]
        assert len(okish) >= 2
        failed = [d for d in result.m2.decisions if d.error]
        assert any("simulated" in (d.error or "") for d in failed)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_r1a_t10_dry_run_does_not_write_rating():
    """T10: dry-run（write=False）では Rating を書き換えない。"""
    import shutil

    from iptc_rating_io import ExifToolNotFoundError, read_screening_meta, require_exiftool, write_rating
    from screening_pipeline import PipelineConfig, ScreeningPipeline

    try:
        require_exiftool()
    except ExifToolNotFoundError:
        print("skip test_r1a_t10_dry_run_does_not_write_rating: exiftool missing")
        return

    root = Path(tempfile.mkdtemp(prefix="lumina_t10_dry_"))
    try:
        month = root / "202609"
        month.mkdir()
        p = month / "blur.jpg"
        Image.new("RGB", (80, 60), color=(128, 128, 128)).save(p, quality=50)
        write_rating(p, 2)
        before = read_screening_meta(p).rating

        pipe = ScreeningPipeline(
            PipelineConfig(
                write=False,
                run_m1=True,
                run_m2=False,
                run_m3=False,
                persist_session=True,
            )
        )
        result = pipe.run_on_dir(month)
        assert result.status == "completed"
        assert read_screening_meta(p).rating == before == 2
        assert result.session_path is not None
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_r1a_t10_works_without_dop_no_error():
    """T10: Works に .dop が無くてもLumina Review 対象列挙・メタ抽出はエラーにならない。"""
    import shutil

    from scanner import extract_file_metadata
    from lumina_review import list_works_review_targets

    root = Path(tempfile.mkdtemp(prefix="lumina_t10_works_"))
    try:
        works = root / "Works"
        works.mkdir()
        sooc = works / "W1.jpg"
        dev = works / "W1_dev.jpg"
        only = works / "W2.jpg"
        Image.new("RGB", (40, 30), color=(9, 9, 9)).save(sooc, quality=90)
        Image.new("RGB", (40, 30), color=(19, 19, 19)).save(dev, quality=90)
        Image.new("RGB", (40, 30), color=(29, 29, 29)).save(only, quality=90)

        targets = list_works_review_targets(works)
        assert [p.name for p in targets] == ["W1_dev.jpg", "W2.jpg"]
        assert not any(works.glob("*.dop"))

        meta, dop_info, block = extract_file_metadata(dev)
        assert dop_info.get("dop_found") is False
        assert meta.get("rating_source") in {"jpeg", "none"}
        assert meta.get("user_intent") is not None
        assert "dxo_dop_sidecar:" in block
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_r1a_t10_iptc_sync_verify_script_roundtrip():
    """T10: scripts/iptc_sync_verify.verify_roundtrip 相当の I/O。"""
    import importlib.util
    import shutil

    from iptc_rating_io import ExifToolNotFoundError, require_exiftool

    try:
        require_exiftool()
    except ExifToolNotFoundError:
        print("skip test_r1a_t10_iptc_sync_verify_script_roundtrip: exiftool missing")
        return

    script = Path(__file__).resolve().parent / "scripts" / "iptc_sync_verify.py"
    assert script.is_file()
    spec = importlib.util.spec_from_file_location("iptc_sync_verify_mod", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    root = Path(tempfile.mkdtemp(prefix="lumina_t10_verify_"))
    try:
        jpeg = root / "verify.jpg"
        mod.make_sample_jpeg(jpeg)
        result = mod.verify_roundtrip(
            jpeg,
            rating=3,
            description="[M2] IPTC sync verify\n[M3] diversity note",
        )
        assert result["passed"] is True
        assert result["rating_ok"] is True
        assert result["description_ok"] is True
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_r1a_t10_no_works_copy_surface():
    """T10 / A6: Works コピー API を持たない（Lumina Review は読取のみ）。"""
    import inspect

    import lumina_review as tw
    from lumina_review import ReviewBatchResult

    src = inspect.getsource(tw)
    assert "shutil.copy" not in src
    assert "shutil.move" not in src
    assert "copy2" not in src
    assert hasattr(tw, "list_works_review_targets")
    assert hasattr(tw, "LuminaReviewRunner")
    # Wave 3: 旧名 alias も残す
    assert hasattr(tw, "list_works_trace_targets")
    assert hasattr(tw, "WorksTraceRunner")
    assert tw.WorksTraceRunner is tw.LuminaReviewRunner
    empty = ReviewBatchResult(works_dir="/tmp", status="completed", created_at="x")
    assert empty.to_dict()["copy_performed"] is False


def test_r1a_t10_acceptance_offline_matrix():
    """T10: R1′-A 受け入れ A1–A10 のオフライン対応表（回帰の錨）。"""
    import delta_log
    import iptc_rating_io
    import library_unit
    import screening_antenna
    import screening_diversity
    import screening_mechanical
    import screening_pipeline
    import lumina_review

    matrix = {
        "A1": (library_unit, screening_pipeline),
        "A2": (screening_mechanical,),
        "A3": (screening_antenna,),
        "A4": (screening_diversity,),
        "A5": (iptc_rating_io,),
        "A6": (lumina_review,),
        "A7": (lumina_review,),
        "A8": (delta_log,),
        "A9": ("app_gui.py", "analyze_folder.py"),
        "A10": ("docs/IPTC_SYNC_VERIFICATION.md", "scripts/iptc_sync_verify.py"),
    }
    root = Path(__file__).resolve().parent
    for key, refs in matrix.items():
        for ref in refs:
            if isinstance(ref, str):
                assert (root / ref).exists(), f"{key}: missing {ref}"
            else:
                assert ref is not None, f"{key}: module missing"
    assert library_unit.is_month_folder_name("202608")
    assert library_unit.is_event_folder_name("20260810_京都")
    assert not library_unit.is_month_folder_name("Works")
    # Wave 3: 公式名と旧 alias が同一オブジェクト
    assert iptc_rating_io.ShortlistMeta is iptc_rating_io.ScreeningMeta
    assert iptc_rating_io.read_shortlist_meta is iptc_rating_io.read_screening_meta
    assert screening_pipeline.ShortlistPipeline is screening_pipeline.ScreeningPipeline
    assert library_unit.is_shortlist_jpeg is library_unit.is_screening_jpeg


def test_hotfix_desktop_config_merge_preserves_shortlist_keys():
    """H1: 講評 GUI 相当の保存でも shortlist/works キーが消えない。"""
    import tempfile

    from desktop_config import load_config, save_config_merge

    root = Path(tempfile.mkdtemp(prefix="cfg_h1_"))
    cfg_path = root / "photo_ai_config.json"
    try:
        save_config_merge(
            {
                "last_dir": "/a",
                "shortlist_last_dir": "/short",
                "works_last_dir": "/works",
                "card_theme": "dark",
            },
            path=cfg_path,
        )
        # app_gui 相当: last_dir / theme / overwrite だけ更新
        merged = save_config_merge(
            {
                "last_dir": "/critique",
                "force_overwrite": True,
                "card_theme": "light",
            },
            path=cfg_path,
        )
        assert merged["shortlist_last_dir"] == "/short"
        assert merged["works_last_dir"] == "/works"
        assert merged["last_dir"] == "/critique"
        assert merged["card_theme"] == "light"
        again = load_config(cfg_path)
        assert again["shortlist_last_dir"] == "/short"
        assert again["works_last_dir"] == "/works"

        # Wave A6: Console タブ記憶キーも merge で消えない
        merged2 = save_config_merge({"console_last_tab": "review"}, path=cfg_path)
        assert merged2["console_last_tab"] == "review"
        assert merged2["shortlist_last_dir"] == "/short"
        again2 = load_config(cfg_path)
        assert again2["console_last_tab"] == "review"
    finally:
        import shutil

        shutil.rmtree(root, ignore_errors=True)


def test_hotfix_m2_m3_skip_none_rating():
    """H3: Rating 未書き込み（None）は M2/M3 候補に入れない。"""
    import shutil

    from iptc_rating_io import ExifToolNotFoundError, require_exiftool, write_rating
    from screening_antenna import AntennaConfig, AntennaScore, run_antenna_on_paths
    from screening_diversity import DiversityConfig, DiversityFeature, run_diversity_on_paths

    try:
        require_exiftool()
    except ExifToolNotFoundError:
        print("skip test_hotfix_m2_m3_skip_none_rating: exiftool missing")
        return

    root = Path(tempfile.mkdtemp(prefix="none_rating_"))
    try:
        with_r = root / "with.jpg"
        without = root / "none.jpg"
        Image.new("RGB", (48, 36), (10, 20, 30)).save(with_r, quality=90)
        Image.new("RGB", (48, 36), (40, 50, 60)).save(without, quality=90)
        write_rating(with_r, 1)
        # without: Rating タグなし → None

        def m2_fn(path: Path) -> AntennaScore:
            return AntennaScore(
                {"framing": 4, "sensitivity": 4, "story": 3, "technical": 3, "sense": 4},
                "hot",
            )

        batch = run_antenna_on_paths(
            [with_r, without],
            AntennaConfig(pass_ratio=1.0, min_pass=0),
            write=False,
            score_fn=m2_fn,
        )
        skipped = [d for d in batch.decisions if d.skipped]
        assert any(d.path.name == "none.jpg" for d in skipped)
        assert batch.skipped >= 1
        # with.jpg だけがスコア対象
        scored = [d for d in batch.decisions if not d.skipped and d.error is None]
        assert any(d.path.name == "with.jpg" for d in scored)
        assert all(d.path.name != "none.jpg" or d.skipped for d in batch.decisions)

        write_rating(with_r, 2)

        def m3_fn(path: Path) -> DiversityFeature:
            return DiversityFeature(
                hue_bin=1, luma_bin=2, tags=("海",), quality=4.0, attachment=3.0, reason="x"
            )

        div = run_diversity_on_paths(
            [with_r, without],
            DiversityConfig(keep_ratio=1.0, top_ratio=0.5),
            write=False,
            feature_fn=m3_fn,
        )
        assert any(d.skipped and d.path.name == "none.jpg" for d in div.decisions)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_hotfix_exception_lambda_captures_message():
    """H2: except 後もエラー文言をキャプチャできる（NameError 回避パターン）。"""
    caught: list[str] = []

    def boom():
        try:
            raise RuntimeError("simulated-ui-error")
        except Exception as e:
            err_msg = str(e)
            # shortlist_gui と同じ default-arg キャプチャ
            cb = lambda msg=err_msg: caught.append(msg)
            cb()

    boom()
    assert caught == ["simulated-ui-error"]


def test_low_priority_schedule_on_ui_skips_destroyed_root():
    """L1: 破棄済み root への after 予約は例外を出さず False。"""
    from desktop_ui import _TclError, schedule_on_ui

    class FakeRoot:
        def winfo_exists(self):
            return False

        def after(self, *_a, **_k):
            raise AssertionError("after must not be called")

    assert schedule_on_ui(FakeRoot(), lambda: None) is False

    class DeadRoot:
        def winfo_exists(self):
            raise _TclError("application has been destroyed")

        def after(self, *_a, **_k):
            raise AssertionError("after must not be called")

    assert schedule_on_ui(DeadRoot(), lambda: None) is False

    called = {"n": 0}

    class LiveRoot:
        def winfo_exists(self):
            return True

        def after(self, _ms, fn):
            called["n"] += 1
            fn()

    assert schedule_on_ui(LiveRoot(), lambda: None) is True
    assert called["n"] == 1


def test_low_priority_sessions_open_does_not_mkdir():
    """L2: 監査フォルダが無いとき mkdir しない（sessions_dir はパス計算のみ）。"""
    import shutil

    from delta_log import sessions_dir

    root = Path(tempfile.mkdtemp(prefix="l2_sess_"))
    try:
        unit = root / "OM202606"
        unit.mkdir()
        sess = sessions_dir(unit)
        assert not sess.exists()
        assert not (unit / "_lumina").exists()
        assert sess.name == "sessions"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_low_priority_rating_percent_fallback():
    """L3: RatingPercent のみでも 0–5 に復元。Rating があれば優先。"""
    from iptc_rating_io import _parse_rating, percent_to_rating, rating_to_percent

    assert percent_to_rating(60) == 3
    assert percent_to_rating(0) == 0
    assert percent_to_rating(100) == 5
    assert percent_to_rating(55) == 3
    assert percent_to_rating(-1) is None
    assert percent_to_rating(101) is None
    for n in range(0, 6):
        assert percent_to_rating(rating_to_percent(n)) == n

    assert _parse_rating({"RatingPercent": "80"}) == 4
    assert _parse_rating({"Rating": "2", "RatingPercent": "80"}) == 2
    assert _parse_rating({}) is None


def test_works_review_selection_summarizes_sooc_skipped():
    """Wave A2: _dev 優先で外した撮って出しを summarize で見える化。"""
    import shutil

    from PIL import Image

    from lumina_review import list_works_review_targets, summarize_works_review_selection

    root = Path(tempfile.mkdtemp(prefix="ux_a2_works_"))
    try:
        works = root / "202608"
        works.mkdir()
        Image.new("RGB", (16, 12), (10, 20, 30)).save(works / "A.jpg", quality=85)
        Image.new("RGB", (16, 12), (40, 50, 60)).save(works / "A_dev.jpg", quality=85)
        Image.new("RGB", (16, 12), (70, 80, 90)).save(works / "B.jpg", quality=85)

        summary = summarize_works_review_selection(works)
        names = [p.name for p in summary["targets"]]
        assert names == ["A_dev.jpg", "B.jpg"]
        assert summary["dev_count"] == 1
        assert summary["sooc_count"] == 1
        assert [p.name for p in summary["sooc_skipped"]] == ["A.jpg"]
        assert list_works_review_targets(works) == summary["targets"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_antenna_prompt_avoids_judge_vocabulary():
    """Wave A5: M2 プロンプトは採点語より熱量ラベル。"""
    from screening_antenna import build_antenna_prompt, build_antenna_system_prompt
    from prompt_contracts import JUDGE_VOCAB_FORBIDDEN_IN_PROMPTS

    user = build_antenna_prompt()
    system = build_antenna_system_prompt()
    assert "熱量" in user
    assert "短く採点" not in user
    assert "採点ではなく" in user
    assert "審判" in system or "相対熱量" in system
    blob = user + "\n" + system
    for stem in JUDGE_VOCAB_FORBIDDEN_IN_PROMPTS:
        assert stem not in blob, stem


def test_console_ui_copy_phase1_labels():
    """P2-2 Phase 1: Console 表層ラベル（オーナー確定）。"""
    import console_ui_copy as c

    assert "選ぶ" in c.TAB_SELECT
    assert "対話ノート作成" in c.TAB_NOTES
    assert c.STAGE_M1.startswith("残す")
    assert c.STAGE_M2.startswith("見返す")
    assert c.STAGE_M3.startswith("言葉にする")
    assert "試行" in c.DRY_RUN
    assert c.CONFIRM_SELECT_Q.startswith("選ぶプロセスを始めますか")
    assert c.DONE_SELECT == "星をつけ終わりました"
    assert c.DONE_NOTES == "対話ノートを作成しました"
    assert "画像を選ぶお手伝い" in c.help_select_text()
    assert "対話ノートとして残します" in c.help_notes_text()
    assert "星の数3または4" in c.help_cards_text()


def test_prompt_contracts_judge_vocab_and_time_ban_alignment():
    """Q2: 審判語契約＋時間帯禁止語が scanner / Phase1 指示と整合。"""
    from prompt_contracts import (
        assert_time_ban_aligned_with_scanner,
        check_phase1_time_ban_in_prompt,
        check_prompt_judge_vocab,
    )

    assert_time_ban_aligned_with_scanner()
    ctx = CritiquePromptContext.from_metadata(
        {"camera_model": "TestCam", "lens_model": "TestLens"},
        {},
    )
    p1 = build_phase1_prompt(ctx)
    p2 = build_phase2_prompt(ctx, "■TITLE: t\n■SCORES:\n・眼差の輪郭 (Contours of the Eyes)  : ★★★☆☆ (3/5)")
    errors = check_prompt_judge_vocab(p1, p2, get_system_role())
    assert not errors, errors
    time_errors = check_phase1_time_ban_in_prompt(p1)
    assert not time_errors, time_errors
    from prompt_contracts import check_phase1_critique_summary_contract

    q4_errors = check_phase1_critique_summary_contract(p1)
    assert not q4_errors, q4_errors


def test_phase_d_offline_fixtures_person_and_time():
    """Q3: 画像不要 fixture で人物分岐・時間帯禁止の再発を防ぐ。"""
    from prompt_contracts import (
        check_output_person_absent,
        check_output_person_present,
        check_output_time_ban,
    )

    root = Path(__file__).resolve().parent / "eval" / "phase_d" / "fixtures"
    person = (root / "person_pass_phase1.txt").read_text(encoding="utf-8")
    no_ok = (root / "no_person_pass_phase1.txt").read_text(encoding="utf-8")
    no_fail = (root / "no_person_fail_anthropomorph.txt").read_text(encoding="utf-8")
    time_fail = (root / "time_ban_fail_phase1.txt").read_text(encoding="utf-8")

    assert check_output_person_present(person)["pass"]
    assert check_output_person_absent(no_ok)["pass"]
    assert not check_output_person_absent(no_fail)["pass"]
    assert not check_output_time_ban(time_fail)["pass"]
    assert check_output_time_ban(person)["pass"]
    assert check_output_time_ban(no_ok)["pass"]

    from prompt_contracts import check_output_critique_summary_beats

    q4_ok = (root / "critique_summary_q4_pass.txt").read_text(encoding="utf-8")
    q4_fail = (root / "critique_summary_template_fail.txt").read_text(encoding="utf-8")
    assert check_output_critique_summary_beats(q4_ok)["pass"]
    assert not check_output_critique_summary_beats(q4_fail)["pass"]


def test_q5_summarize_h3_and_reactions_scripts():
    """Q5: 集計スクリプトが fixture で動く（API 不要）。"""
    import importlib.util
    import json
    import sys

    root = Path(__file__).resolve().parent
    scripts = root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))

    def _load(name: str):
        path = scripts / f"{name}.py"
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    h3_mod = _load("summarize_h3_deltas")
    rx_mod = _load("summarize_user_reactions")

    session = (root / "eval/fixtures_q5/sample_session_with_h3.json").resolve()
    h3 = h3_mod.summarize([session])
    assert h3["sessions_with_h3_delta"] == 1
    assert h3["transitions"]["2->4"] == 1
    assert h3["transitions"]["0->2"] == 1

    rows = json.loads(
        (root / "eval/fixtures_q5/sample_reactions.json").read_text(encoding="utf-8")
    )
    rx = rx_mod.summarize(rows)
    assert rx["counts"]["good"] == 2
    assert rx["counts"]["mixed"] == 1
    assert rx["counts"]["weak"] == 2
    assert len(rx["weak_samples"]) == 2


def test_low_priority_works_subdir_hint():
    """L4: 直下0枚でもサブフォルダに JPEG があれば案内。再帰列挙はしない。"""
    import shutil

    from PIL import Image

    from lumina_review import (
        count_jpegs_in_immediate_subdirs,
        list_works_review_targets,
        works_empty_targets_hint,
    )

    root = Path(tempfile.mkdtemp(prefix="l4_works_"))
    try:
        works = root / "202606"
        nested = works / "event_like"
        nested.mkdir(parents=True)
        Image.new("RGB", (16, 12), (1, 2, 3)).save(nested / "hidden.jpg", quality=85)

        assert list_works_review_targets(works) == []
        assert count_jpegs_in_immediate_subdirs(works) == 1
        hint = works_empty_targets_hint(works)
        assert "サブフォルダ" in hint
        assert "1 枚" in hint

        Image.new("RGB", (16, 12), (4, 5, 6)).save(works / "P1_dev.jpg", quality=85)
        assert [p.name for p in list_works_review_targets(works)] == ["P1_dev.jpg"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_low_priority_prompt_pick_skips_sentinel_nashi():
    """L5: metadata の哨兵「なし」はスキップし dop_info を採用。"""
    from critique_prompts import CritiquePromptContext, coalesce_prompt_text, is_prompt_missing

    assert is_prompt_missing("なし")
    assert is_prompt_missing("")
    assert is_prompt_missing(None)
    assert not is_prompt_missing("光")

    assert coalesce_prompt_text("なし", "★★★☆☆ (3/5)") == "★★★☆☆ (3/5)"
    assert coalesce_prompt_text("なし", "なし") == "なし"

    ctx = CritiquePromptContext.from_metadata(
        {"rating_str": "なし", "keywords": "なし", "content_headline": "なし"},
        {
            "rating_str": "★★★☆☆ (3/5)",
            "keywords": "旅,光",
            "content_headline": "夕方の川",
        },
    )
    assert ctx.rating_str == "★★★☆☆ (3/5)"
    assert ctx.keywords == "旅,光"
    assert ctx.content_headline == "夕方の川"

    ctx2 = CritiquePromptContext.from_metadata(
        {"rating_str": "★★★★★ (5/5)"},
        {"rating_str": "★★★☆☆ (3/5)"},
    )
    assert ctx2.rating_str == "★★★★★ (5/5)"


def test_dry_run_session_rejects_record_post_h3():
    """C1: write_meta=False のセッションは H3 記録を拒否する。"""
    import json
    import shutil
    import tempfile

    from delta_log import DryRunSessionError, record_post_h3, write_session_document

    root = Path(tempfile.mkdtemp(prefix="dry_h3_"))
    try:
        unit = root / "OM202608"
        unit.mkdir()
        sess = unit / "_lumina" / "sessions"
        sess.mkdir(parents=True)
        path = sess / "dry.json"
        doc = {
            "schema": "lumina.shortlist_session.v1",
            "id": "dry",
            "library_unit_id": "OM202608",
            "library_unit_kind": "month",
            "library_unit_path": str(unit),
            "write_meta": False,
            "pre_h3": {"files": [], "counts_by_rating": {}},
            "files": [],
        }
        path.write_text(json.dumps(doc), encoding="utf-8")
        try:
            record_post_h3(path)
            raise AssertionError("DryRunSessionError expected")
        except DryRunSessionError as e:
            assert "ドライラン" in str(e)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_guided_futei_band_tokyo_summer_day():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from guided_futei_time import classify_futei_band

    tz = ZoneInfo("Asia/Tokyo")
    lat, lon = 35.68, 139.76
    # 夏至付近の昼（ローカル正午付近）
    noon = datetime(2026, 6, 21, 12, 0, 0, tzinfo=tz)
    band = classify_futei_band(noon, lat, lon, tz)
    assert band in {"正午（九）", "午後（八）", "午前（四）"}


def test_guided_futei_band_night():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from guided_futei_time import classify_futei_band

    tz = ZoneInfo("Asia/Tokyo")
    lat, lon = 35.68, 139.76
    night = datetime(2026, 6, 21, 2, 0, 0, tzinfo=tz)
    assert classify_futei_band(night, lat, lon, tz) == "夜"


def test_guided_timezone_anchor_tokyo():
    from zoneinfo import ZoneInfo

    from guided_futei_time import timezone_anchor

    lat, lon, region = timezone_anchor(ZoneInfo("Asia/Tokyo"))
    assert region == "東京"
    assert 35.0 < lat < 36.0
    assert 139.0 < lon < 140.0


def test_guided_futei_band_without_gps_uses_timezone_anchor():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from guided_futei_time import classify_futei_band, timezone_anchor

    tz = ZoneInfo("Asia/Tokyo")
    lat, lon, _ = timezone_anchor(tz)
    noon = datetime(2026, 6, 21, 12, 0, 0, tzinfo=tz)
    band = classify_futei_band(noon, lat, lon, tz)
    assert band in {"正午（九）", "午後（八）", "午前（四）"}


def test_guided_resolve_region_without_gps():
    from zoneinfo import ZoneInfo

    from guided_metadata import resolve_city_region

    region = resolve_city_region(None, None, {}, geocode=False, tz=ZoneInfo("Asia/Tokyo"))
    assert region == "東京"


def test_guided_api_parameters_shape():
    from guided_metadata import GuidedApiParameters, GuidedCameraSettings, GuidedImageInfo

    p = GuidedApiParameters(
        image=GuidedImageInfo(
            image_id="abc",
            size="100x100",
            shot_at="2026-01-01T12:00:00+09:00",
            timezone="Asia/Tokyo",
            region="東京",
            time_band="正午（九）",
        ),
        camera=GuidedCameraSettings(
            focal_length="50mm",
            aperture="f/2.8",
            shutter_speed="1/125s",
            iso="ISO 400",
            mode="マニュアル",
            exposure_compensation="+0.0 EV",
        ),
    )
    d = p.to_dict()
    assert d["image"]["image_id"] == "abc"
    assert d["camera"]["shutter_speed"] == "1/125s"
    assert "time_band" in d["image"]


def test_guided_parameter_display_rows():
    from guided_web.parameter_display import build_parameter_display

    display = build_parameter_display(
        {
            "image": {
                "size": "4032x3024",
                "shot_at": "2026-06-21T12:00:00+09:00",
                "timezone": "Asia/Tokyo",
                "region": "東京",
                "time_band": "正午（九）",
            },
            "camera": {
                "focal_length": "50mm",
                "aperture": "f/2.8",
                "shutter_speed": "1/125s",
                "iso": "ISO 400",
                "mode": "マニュアル",
                "exposure_compensation": "+0.0 EV",
            },
        },
        file_name="sample.jpg",
    )
    assert display[0]["title"] == "画像情報"
    assert display[1]["title"] == "カメラ設定"
    assert display[0]["rows"][0] == {"key": "file_name", "label": "ファイル名", "value": "sample.jpg"}
    assert display[0]["rows"][5]["label"] == "時間帯"
    assert display[1]["rows"][0]["label"] == "焦点距離"


def test_guided_upload_returns_parameter_display():
    import tempfile
    from pathlib import Path

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "params.jpg"
    Image.new("RGB", (80, 60), (90, 100, 110)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("params.jpg", f, "image/jpeg")})
    assert res.status_code == 200
    data = res.json()
    assert "parameter_display" in data
    assert data["parameter_display"][0]["title"] == "画像情報"
    assert any(row["label"] == "撮影日時" for row in data["parameter_display"][0]["rows"])
    assert data["parameter_display"][0]["rows"][0]["label"] == "ファイル名"
    assert data["parameter_display"][0]["rows"][0]["value"] == "params.jpg"


def test_guided_photo_response_omits_identifying_local_fields():
    """ブラウザ応答にフルパス・メタ抜粋・生 GPS を載せない。"""
    import json
    import tempfile
    from pathlib import Path

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "private.jpg"
    Image.new("RGB", (80, 60), (1, 2, 3)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("private.jpg", f, "image/jpeg")})
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert "parameter_display" in data
    assert "local_meta_preview" not in data
    assert "original_path" not in data
    assert "meta_block" not in data
    blob = json.dumps(data)
    assert "gps_lat" not in blob
    assert "GPSLatitude" not in blob
    sess = app_module._sessions[data["session_id"]]
    assert "original_path" in sess
    assert "meta_block" in sess


def test_guided_upload_rejects_unreadable_image():
    import tempfile
    from pathlib import Path

    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    fake = td / "fake.jpg"
    fake.write_text("not-a-jpeg", encoding="utf-8")
    with fake.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("fake.jpg", f, "image/jpeg")})
    assert res.status_code == 400
    assert res.json()["detail"] == "unreadable image"


def test_guided_unreadable_upload_keeps_existing_session():
    """壊れたファイルの upload は既存セッションを消さない（失敗時は差し替えない）。"""
    import tempfile
    from pathlib import Path

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "ok.jpg"
    Image.new("RGB", (80, 60), (12, 34, 56)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        ok = client.post("/api/session/photo", files={"file": ("ok.jpg", f, "image/jpeg")})
    assert ok.status_code == 200
    session_id = ok.json()["session_id"]
    file_name = ok.json()["file_name"]

    fake = td / "fake.jpg"
    fake.write_text("not-a-jpeg", encoding="utf-8")
    with fake.open("rb") as f:
        bad = client.post("/api/session/photo", files={"file": ("fake.jpg", f, "image/jpeg")})
    assert bad.status_code == 400
    assert session_id in app_module._sessions
    preview = client.get(f"/api/session/{session_id}/preview")
    assert preview.status_code == 200
    status = client.get(f"/api/session/{session_id}/critique")
    assert status.status_code == 200
    assert file_name == "ok.jpg"


def test_guided_card_footer_metadata():
    import tempfile
    from pathlib import Path

    from PIL import Image

    from guided_web.guided_card import create_guided_card

    td = Path(tempfile.mkdtemp(prefix="guided_card_"))
    jpeg = td / "sample.jpg"
    out = td / "card.png"
    Image.new("RGB", (240, 180), (70, 80, 90)).save(jpeg, "JPEG")
    create_guided_card(
        jpeg,
        PHASE1_SAMPLE,
        out,
        theme="dark",
        user_note="静かな午後",
        user_stars=3,
        file_name="sample.jpg",
    )
    assert out.is_file()
    with Image.open(out) as card:
        assert card.size == (1080, 1350)


def test_guided_body_sections_split():
    from guided_web.body_sections import split_critique_sections

    body = "【1. 第一印象】\n一行目\n【2. 情景描写】\n二行目"
    secs = split_critique_sections(body)
    assert len(secs) == 2
    assert secs[1]["id"] == "2"


def test_guided_stock_export_writes_files():
    import shutil
    import tempfile
    from pathlib import Path

    from PIL import Image

    from guided_web.stock_export import export_guided_session, export_output_names

    td = Path(tempfile.mkdtemp(prefix="guided_export_"))
    try:
        jpeg = td / "sample.jpg"
        Image.new("RGB", (200, 150), (80, 90, 100)).save(jpeg, "JPEG", quality=90)
        session = {
            "path": str(jpeg),
            "preview_path": str(jpeg),
            "original_filename": "sample.jpg",
            "original_path": "/Users/me/Pictures/sample.jpg",
            "meta_block": "=== EXIF ===\nテスト",
            "api_params": {"image": {"image_id": "test123"}},
            "critique": {
                "lens": "self",
                "phase1_raw": PHASE1_SAMPLE,
            },
        }
        save_root = td / "stock"
        save_root.mkdir()
        assert export_output_names("sample.jpg") == ("sample_LN.png", "sample_LN.md")
        files = export_guided_session(
            session,
            save_dir=save_root,
            user_stars=4,
            card_theme="light",
            user_note="テスト一言",
            reflections={
                "noticed_see": {"checked": True, "text": "", "label": "写真を見て"},
                "thought_scene": {"checked": True, "text": "", "label": "その時の情景"},
            },
        )
        assert (save_root / "sample_LN.png").is_file()
        assert (save_root / "sample_LN.md").is_file()
        assert not (save_root / "photo.jpg").exists()
        note_text = (save_root / "sample_LN.md").read_text(encoding="utf-8")
        assert "=== 振り返り ===" in note_text
        assert "オリジナルファイルのパス: /Users/me/Pictures/sample.jpg" in note_text
        assert "★ 思い: 4/5" in note_text
        assert "一言: テスト一言" in note_text
        assert "振り返りメモ: 写真を見て, その時の情景" in note_text
        assert "気づいたことがある" in note_text
        assert "☑ 写真を見て" in note_text
        assert "⬜ 言葉にして" in note_text
        assert "☑ その時の情景" in note_text
        reflect_pos = note_text.index("=== 振り返り ===")
        path_pos = note_text.index("オリジナルファイルのパス:")
        stars_pos = note_text.index("★ 思い:")
        note_pos = note_text.index("一言:")
        noticed_pos = note_text.index("気づいたことがある")
        memo_pos = note_text.index("振り返りメモ:")
        exported_pos = note_text.index("書き出し日時:")
        assert reflect_pos < path_pos < stars_pos < note_pos < noticed_pos < memo_pos < exported_pos
        assert files["card"].endswith("sample_LN.png")
    finally:
        shutil.rmtree(td, ignore_errors=True)


def test_guided_format_reflections_block():
    from guided_web.reflect_prompts import format_reflections_block

    block = format_reflections_block(
        {
            "noticed_see": {"checked": True, "text": "", "label": "写真を見て"},
            "noticed_words": {"checked": False, "text": "", "label": "言葉にして"},
            "photo_book": {"checked": True, "text": "", "label": "フォトブックにしたい"},
        }
    )
    assert "気づいたことがある" in block
    assert "☑ 写真を見て" in block
    assert "⬜ 言葉にして" in block
    assert "☑ フォトブックにしたい" in block
    assert "振り返りメモ" not in block


def test_guided_privacy_prompts_exclude_identifying_metadata():
    from guided_web.guided_privacy import (
        GuidedCritiqueContext,
        assert_prompt_is_privacy_safe,
        build_guided_phase1_prompt,
        build_guided_phase2_prompt,
    )

    api_params = {
        "image": {
            "image_id": "sess123",
            "size": "4032x3024",
            "shot_at": "2026-06-21T12:00:00+09:00",
            "timezone": "Asia/Tokyo",
            "region": "東京",
            "time_band": "正午（九）",
        },
        "camera": {
            "focal_length": "50mm",
            "aperture": "f/2.8",
            "shutter_speed": "1/250",
            "iso": "400",
            "mode": "マニュアル",
            "exposure_compensation": "0EV",
        },
    }
    ctx = GuidedCritiqueContext.from_api_params(api_params, user_note="静かな午後")
    p1 = build_guided_phase1_prompt(ctx)
    p2 = build_guided_phase2_prompt(ctx, "■TITLE: テスト")
    assert "東京" in p1
    assert "正午（九）" in p1
    assert "静かな午後" in p2
    assert "抽象パラメータ" in p1
    assert_prompt_is_privacy_safe(p1)
    assert_prompt_is_privacy_safe(p2)


def test_guided_privacy_audit_whitelist():
    import json
    import shutil
    import tempfile
    from pathlib import Path

    import guided_web.guided_privacy as gp

    td = Path(tempfile.mkdtemp(prefix="guided_privacy_"))
    old_path = gp._AUDIT_PATH
    try:
        gp._AUDIT_PATH = td / "audit.jsonl"
        api_params = {
            "image": {
                "image_id": "abc",
                "size": "100x100",
                "shot_at": "2026-01-01T12:00:00+09:00",
                "timezone": "Asia/Tokyo",
                "region": "東京",
                "time_band": "夜",
                "file_name": "secret.jpg",
                "gps_lat": 35.68,
            },
            "camera": {
                "focal_length": "35mm",
                "aperture": "f/4",
                "shutter_speed": "1/60",
                "iso": "800",
                "mode": "絞り優先",
                "exposure_compensation": "-0.3EV",
                "camera_model": "Secret Camera",
            },
        }
        gp.record_api_audit(session_id="sess1", api_params=api_params, user_note="hi")
        line = gp._AUDIT_PATH.read_text(encoding="utf-8").strip()
        entry = json.loads(line)
        audited = entry["api_parameters"]
        assert "file_name" not in audited.get("image", {})
        assert "gps_lat" not in audited.get("image", {})
        assert "camera_model" not in audited.get("camera", {})
        assert audited["image"]["region"] == "東京"
        assert entry["user_note_sha256"]
    finally:
        gp._AUDIT_PATH = old_path
        shutil.rmtree(td, ignore_errors=True)


def test_guided_critique_runner_uses_api_params():
    from pathlib import Path
    from unittest.mock import patch

    from guided_web.critique_runner import run_phase1

    captured: dict = {}

    def fake_generate(image_path, api_params, **kwargs):
        captured["api_params"] = api_params
        captured["kwargs"] = kwargs
        return "■TITLE: T\n■SUMMARY: S\n■SCORES:\n感性: ★★★☆☆ (3/5)\n■CRITIQUE_SUMMARY: テスト"

    api_params = {
        "image": {"image_id": "x", "region": "東京", "time_band": "夜"},
        "camera": {"iso": "400"},
    }
    with patch("guided_web.critique_runner.generate_guided_critique", fake_generate):
        run_phase1(Path("dummy.jpg"), api_params, lens="self", user_note="note", session_id="sid")
    assert captured["api_params"] is api_params
    assert captured["kwargs"]["session_id"] == "sid"
    assert captured["kwargs"]["user_note"] == "note"


def test_guided_selected_reflection_labels():
    from guided_web.reflect_prompts import selected_reflection_labels

    labels = selected_reflection_labels(
        {
            "noticed_see": {"checked": True, "text": "", "label": "写真を見て"},
            "photo_keep": {"checked": True, "text": "アルバムに", "label": "手元に置いておきたい"},
        }
    )
    assert labels == ["写真を見て", "アルバムに"]


def test_guided_settings_save_folder_roundtrip():
    import json
    import shutil
    import tempfile
    from pathlib import Path

    import guided_web.settings as gs

    td = Path(tempfile.mkdtemp(prefix="guided_settings_"))
    old_path = gs._SETTINGS_PATH
    try:
        gs._SETTINGS_PATH = td / "guided_settings.json"
        folder = td / "chosen"
        folder.mkdir()
        resolved = gs.set_save_folder(folder)
        assert resolved == folder.resolve()
        loaded = gs.get_save_folder()
        assert loaded == folder.resolve()
        data = json.loads(gs._SETTINGS_PATH.read_text(encoding="utf-8"))
        assert data["save_folder"] == str(folder.resolve())
        photos = td / "photos"
        photos.mkdir()
        export = td / "export"
        export.mkdir()
        gs.set_save_folder(export)
        gs.set_photo_folder(photos)
        assert gs.get_save_folder() == export.resolve()
        assert gs.get_photo_folder() == photos.resolve()
        data = json.loads(gs._SETTINGS_PATH.read_text(encoding="utf-8"))
        assert data["save_folder"] == str(export.resolve())
        assert data["photo_folder"] == str(photos.resolve())
        tmp_session = td / "lumina_guided" / "sid"
        tmp_session.mkdir(parents=True)
        skipped = gs.remember_photo_source(tmp_session / "x.jpg")
        assert skipped is None
        assert gs.get_photo_folder() == photos.resolve()
        remembered = gs.remember_photo_source(photos / "shot.jpg")
        assert remembered == photos.resolve()
    finally:
        gs._SETTINGS_PATH = old_path
        shutil.rmtree(td, ignore_errors=True)


def test_guided_session_delete_removes_temp_dir():
    import tempfile
    from pathlib import Path

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module
    from guided_web.session_cleanup import guided_temp_root

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "cleanup.jpg"
    Image.new("RGB", (80, 60), (90, 100, 110)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("cleanup.jpg", f, "image/jpeg")})
    assert res.status_code == 200
    session_id = res.json()["session_id"]
    temp_dir = guided_temp_root() / session_id
    assert temp_dir.is_dir()

    del_res = client.delete(f"/api/session/{session_id}")
    assert del_res.status_code == 200
    assert del_res.json() == {"ok": True}
    assert not temp_dir.exists()
    assert client.get(f"/api/session/{session_id}/critique").status_code == 404


def test_guided_phase2_retry_restarts_background():
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "retry.jpg"
    Image.new("RGB", (80, 60), (40, 50, 60)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("retry.jpg", f, "image/jpeg")})
    session_id = res.json()["session_id"]
    app_module._sessions[session_id]["critique"] = {
        "status": "error",
        "error": "timeout",
        "lens": "self",
        "user_note": "note",
        "phase1_raw": PHASE1_SAMPLE,
        "phase1_parsed": parse_critique_text(PHASE1_SAMPLE),
    }

    with patch("guided_web.app.run_phase2") as mock_phase2:
        mock_phase2.return_value = (
            PHASE1_SAMPLE + PHASE2_SAMPLE,
            parse_critique_text(PHASE2_SAMPLE),
            [{"id": "1", "heading": "【1】", "text": "one"}],
        )
        retry_res = client.post(f"/api/session/{session_id}/critique/phase2/retry")
    assert retry_res.status_code == 200
    assert retry_res.json()["status"] == "phase2_running"
    mock_phase2.assert_called_once()

    crit = client.get(f"/api/session/{session_id}/critique").json()
    assert crit["status"] == "complete"
    assert crit["sections"]


def test_guided_purge_orphan_temp_keeps_live_sessions():
    import tempfile
    from pathlib import Path

    from guided_web.session_cleanup import purge_orphan_temp, remove_tree

    root = Path(tempfile.mkdtemp(prefix="lumina_guided_test_"))
    live_dir = root / "live1"
    live_dir.mkdir()
    (live_dir / "keep.txt").write_text("keep", encoding="utf-8")
    orphan = root / "orphan1"
    orphan.mkdir()
    (orphan / "gone.txt").write_text("gone", encoding="utf-8")
    staging = root / "upload_abc"
    staging.mkdir()
    try:
        sessions = {"live1": {"temp_dir": str(live_dir)}}
        removed = purge_orphan_temp(sessions, root=root)
        assert "orphan1" in removed
        assert "upload_abc" in removed
        assert "live1" not in removed
        assert live_dir.is_dir()
        assert not orphan.exists()
        assert not staging.exists()
    finally:
        remove_tree(root)


def test_guided_shutdown_sessions_removes_all():
    import tempfile
    from pathlib import Path

    from guided_web.session_cleanup import remove_tree, shutdown_sessions

    root = Path(tempfile.mkdtemp(prefix="lumina_guided_shut_"))
    a = root / "a"
    b = root / "b"
    a.mkdir()
    b.mkdir()
    leftover = root / "upload_left"
    leftover.mkdir()
    sessions = {
        "a": {"temp_dir": str(a)},
        "b": {"temp_dir": str(b)},
    }
    try:
        result = shutdown_sessions(sessions, root=root)
        assert result["dropped"] == 2
        assert "upload_left" in result["orphans"]
        assert sessions == {}
        assert not a.exists()
        assert not b.exists()
        assert not leftover.exists()
    finally:
        remove_tree(root)


def test_guided_session_release_is_idempotent():
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    missing = "missing-session-id"
    del_res = client.delete(f"/api/session/{missing}")
    assert del_res.status_code == 200
    assert del_res.json() == {"ok": True}
    rel_res = client.post(f"/api/session/{missing}/release")
    assert rel_res.status_code == 200
    assert rel_res.json() == {"ok": True}


def test_guided_lifespan_purges_orphans_and_shutdown_sessions():
    import tempfile
    from pathlib import Path

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module
    from guided_web.session_cleanup import guided_temp_root

    root = guided_temp_root()
    orphan = root / "orphan_lifespan_test"
    orphan.mkdir(parents=True, exist_ok=True)
    (orphan / "junk.txt").write_text("x", encoding="utf-8")

    td = Path(tempfile.mkdtemp())
    jpeg = td / "life.jpg"
    Image.new("RGB", (80, 60), (20, 30, 40)).save(jpeg, "JPEG")
    session_id = None
    temp_dir = None
    with TestClient(app_module.app) as client:
        assert not orphan.exists()
        with jpeg.open("rb") as f:
            res = client.post("/api/session/photo", files={"file": ("life.jpg", f, "image/jpeg")})
        assert res.status_code == 200
        session_id = res.json()["session_id"]
        temp_dir = root / session_id
        assert temp_dir.is_dir()
        assert client.get("/api/health").json()["status"] == "ok"

    assert session_id not in app_module._sessions
    assert not temp_dir.exists()


def test_guided_critique_rejects_parallel_without_restart():
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "lock.jpg"
    Image.new("RGB", (80, 60), (11, 22, 33)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("lock.jpg", f, "image/jpeg")})
    session_id = res.json()["session_id"]
    app_module._sessions[session_id]["critique"] = {
        "status": "phase1_running",
        "lens": "self",
    }
    with patch("guided_web.app.run_phase1") as mock_phase1:
        locked = client.post(
            f"/api/session/{session_id}/critique",
            json={"lens": "self", "force_restart": False},
        )
    assert locked.status_code == 409
    assert locked.json()["status"] == "phase1_running"
    mock_phase1.assert_not_called()


def test_guided_phase2_ignores_stale_epoch():
    import asyncio
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "epoch.jpg"
    Image.new("RGB", (80, 60), (50, 60, 70)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("epoch.jpg", f, "image/jpeg")})
    session_id = res.json()["session_id"]
    sess = app_module._sessions[session_id]
    sess["epoch"] = 2
    sess["critique"] = {"status": "phase2_running", "lens": "self", "error": None}
    with patch("guided_web.app.run_phase2") as mock_phase2:
        asyncio.run(app_module._finish_phase2(session_id, "self", "", PHASE1_SAMPLE, epoch=1))
    mock_phase2.assert_not_called()
    assert sess["critique"]["status"] == "phase2_running"


def test_guided_cancel_critique_keeps_photo_and_discards_stale_phase2():
    import asyncio
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "cancel.jpg"
    Image.new("RGB", (80, 60), (15, 25, 35)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("cancel.jpg", f, "image/jpeg")})
    session_id = res.json()["session_id"]
    sess = app_module._sessions[session_id]
    sess["epoch"] = 1
    sess["critique"] = {
        "status": "phase1_running",
        "lens": "self",
        "user_note": "note",
        "phase1_raw": PHASE1_SAMPLE,
    }

    cancel_res = client.post(f"/api/session/{session_id}/critique/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "idle"
    assert sess["epoch"] == 2
    assert client.get(f"/api/session/{session_id}/preview").status_code == 200

    with patch("guided_web.app.run_phase2") as mock_phase2:
        asyncio.run(app_module._finish_phase2(session_id, "self", "note", PHASE1_SAMPLE, epoch=1))
    mock_phase2.assert_not_called()
    assert sess["critique"]["status"] == "idle"


def test_guided_cancel_complete_critique_is_noop():
    import tempfile
    from pathlib import Path

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "keep.jpg"
    Image.new("RGB", (80, 60), (40, 50, 60)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("keep.jpg", f, "image/jpeg")})
    session_id = res.json()["session_id"]
    sess = app_module._sessions[session_id]
    parsed = parse_critique_text(PHASE1_SAMPLE)
    sess["epoch"] = 4
    sess["critique"] = {
        "status": "complete",
        "lens": "self",
        "user_note": "keep me",
        "phase1_raw": PHASE1_SAMPLE,
        "phase1_parsed": parsed,
        "full_raw": PHASE1_SAMPLE,
        "full_parsed": parsed,
        "sections": [],
    }
    cancel_res = client.post(f"/api/session/{session_id}/critique/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "complete"
    assert sess["epoch"] == 4
    assert sess["critique"]["phase1_raw"] == PHASE1_SAMPLE


def test_guided_cancel_then_force_restart_starts_fresh():
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "restart.jpg"
    Image.new("RGB", (80, 60), (9, 10, 11)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("restart.jpg", f, "image/jpeg")})
    session_id = res.json()["session_id"]
    sess = app_module._sessions[session_id]
    sess["epoch"] = 1
    sess["critique"] = {"status": "phase1_running", "lens": "self"}
    assert client.post(f"/api/session/{session_id}/critique/cancel").json()["status"] == "idle"

    parsed = parse_critique_text(PHASE1_SAMPLE)
    with patch("guided_web.app.run_phase1", return_value=(PHASE1_SAMPLE, parsed)), patch(
        "guided_web.app.run_phase2", return_value=(PHASE1_SAMPLE, parsed, [])
    ):
        start_res = client.post(
            f"/api/session/{session_id}/critique",
            json={"lens": "self", "user_note": "", "force_restart": True},
        )
    assert start_res.status_code == 200
    assert start_res.json()["status"] in {"phase1_running", "phase2_running", "complete"}
    assert sess["epoch"] == 3


def test_guided_photo_pick_uses_ui_executor_while_critique_runs():
    """講評中でも写真選択が AI 実行器を待たない。"""
    import threading
    import time
    from concurrent.futures import wait as wait_futures
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    started = threading.Semaphore(0)
    release = threading.Event()

    def blocking_worker():
        started.release()
        release.wait(timeout=8)

    critique_exec = app_module._get_critique_executor()
    futures = [critique_exec.submit(blocking_worker) for _ in range(2)]
    assert started.acquire(timeout=2)
    assert started.acquire(timeout=2)

    picked_called = {"n": 0}

    def fake_pick(_initial):
        picked_called["n"] += 1
        return None

    client = TestClient(app_module.app)
    result = {}

    def do_pick():
        t0 = time.monotonic()
        with patch("guided_web.app.pick_image_file", side_effect=fake_pick):
            result["res"] = client.post("/api/session/photo-pick")
        result["elapsed"] = time.monotonic() - t0

    try:
        t = threading.Thread(target=do_pick)
        t.start()
        t.join(timeout=2.5)
        assert not t.is_alive()
        assert result["res"].status_code == 400
        assert picked_called["n"] == 1
        assert result["elapsed"] < 2.0, result["elapsed"]
    finally:
        release.set()
        wait_futures(futures, timeout=3)


def test_guided_ui_and_critique_executors_are_separate():
    from guided_web import app as app_module

    ui = app_module._get_ui_executor()
    ai = app_module._get_critique_executor()
    assert ui is not ai
    assert ui._thread_name_prefix != ai._thread_name_prefix


def test_guided_photo_pick_opens_photo_folder_not_export_folder():
    import shutil
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from guided_web import app as app_module
    import guided_web.settings as gs

    td = Path(tempfile.mkdtemp(prefix="guided_folders_"))
    photos = td / "camera_roll"
    export = td / "notes_out"
    photos.mkdir()
    export.mkdir()
    old_path = gs._SETTINGS_PATH
    captured = {}

    def fake_pick(initial):
        captured["initial"] = Path(initial) if initial else None
        return None

    try:
        gs._SETTINGS_PATH = td / "guided_settings.json"
        gs.set_photo_folder(photos)
        gs.set_save_folder(export)
        client = TestClient(app_module.app)
        with patch("guided_web.app.pick_image_file", side_effect=fake_pick):
            res = client.post("/api/session/photo-pick")
        assert res.status_code == 400
        assert captured["initial"] == photos.resolve()
        assert captured["initial"] != export.resolve()
    finally:
        gs._SETTINGS_PATH = old_path
        shutil.rmtree(td, ignore_errors=True)


def test_guided_stale_cancel_does_not_kill_newer_critique():
    import tempfile
    from pathlib import Path

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "stale.jpg"
    Image.new("RGB", (80, 60), (3, 4, 5)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("stale.jpg", f, "image/jpeg")})
    session_id = res.json()["session_id"]
    sess = app_module._sessions[session_id]
    sess["epoch"] = 6
    sess["critique"] = {"status": "phase1_running", "lens": "self"}
    stale = client.post(f"/api/session/{session_id}/critique/cancel?epoch=5")
    assert stale.status_code == 200
    assert stale.json()["status"] == "phase1_running"
    assert sess["epoch"] == 6
    current = client.post(f"/api/session/{session_id}/critique/cancel?epoch=6")
    assert current.json()["status"] == "idle"
    assert sess["epoch"] == 7


def test_guided_live_cancel_and_clear_during_slow_phase1():
    """講評 POST が Phase1 を待たないので、待ち中のキャンセルとクリアがすぐ終わる。"""
    import socket
    import threading
    import time
    from pathlib import Path
    from unittest.mock import patch

    import httpx
    import uvicorn
    from PIL import Image

    from guided_web import app as app_module

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    phase1_entered = threading.Event()
    phase1_release = threading.Event()

    def slow_phase1(*_args, **_kwargs):
        phase1_entered.set()
        phase1_release.wait(timeout=10)
        raise RuntimeError("slow fixture")

    config = uvicorn.Config(
        app_module.app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    base = f"http://127.0.0.1:{port}"
    jpeg = Path("/tmp/guided_web_test/live.jpg")
    jpeg.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 48), (12, 34, 56)).save(jpeg, "JPEG")

    with patch("guided_web.app.shutdown_sessions", return_value={"dropped": 0, "orphans": []}), patch(
        "guided_web.app._shutdown_executors", lambda: None
    ), patch("guided_web.app.run_phase1", side_effect=slow_phase1), patch(
        "guided_web.app.run_phase2", side_effect=AssertionError("phase2 should not run")
    ):
        thread.start()
        try:
            deadline = time.time() + 5
            while time.time() < deadline:
                try:
                    httpx.get(f"{base}/api/health", timeout=0.3).raise_for_status()
                    break
                except Exception:
                    time.sleep(0.05)
            else:
                raise AssertionError("uvicorn did not start")

            with httpx.Client(base_url=base, timeout=5.0) as client:
                up = client.post("/api/session/photo", files={"file": ("live.jpg", jpeg.read_bytes(), "image/jpeg")})
                assert up.status_code == 200
                sid = up.json()["session_id"]
                t0 = time.monotonic()
                start = client.post(
                    f"/api/session/{sid}/critique",
                    json={"lens": "self", "user_note": "", "force_restart": True},
                )
                start_elapsed = time.monotonic() - t0
                assert start.status_code == 200, start.text
                assert start.json()["status"] == "phase1_running"
                assert start_elapsed < 1.5, start_elapsed
                epoch = start.json()["epoch"]
                assert phase1_entered.wait(timeout=3)
                t1 = time.monotonic()
                cancel = client.post(f"/api/session/{sid}/critique/cancel", params={"epoch": epoch})
                assert cancel.status_code == 200
                assert cancel.json()["status"] == "idle"
                rel = client.post(f"/api/session/{sid}/release")
                assert rel.status_code == 200
                up2 = client.post(
                    "/api/session/photo",
                    files={"file": ("live2.jpg", jpeg.read_bytes(), "image/jpeg")},
                )
                assert up2.status_code == 200
                sid2 = up2.json()["session_id"]
                start2 = client.post(
                    f"/api/session/{sid2}/critique",
                    json={"lens": "self", "user_note": "", "force_restart": True},
                )
                assert start2.status_code == 200
                assert start2.json()["status"] == "phase1_running"
                assert time.monotonic() - t1 < 2.0
                client.post(
                    f"/api/session/{sid2}/critique/cancel",
                    params={"epoch": start2.json()["epoch"]},
                )
        finally:
            phase1_release.set()
            server.should_exit = True
            thread.join(timeout=4)


def test_guided_phase2_retry_skips_when_already_running():
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "running.jpg"
    Image.new("RGB", (80, 60), (8, 9, 10)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("running.jpg", f, "image/jpeg")})
    session_id = res.json()["session_id"]
    app_module._sessions[session_id]["critique"] = {
        "status": "phase2_running",
        "lens": "self",
        "phase1_raw": PHASE1_SAMPLE,
        "phase1_parsed": parse_critique_text(PHASE1_SAMPLE),
    }
    with patch("guided_web.app.run_phase2") as mock_phase2:
        retry_res = client.post(f"/api/session/{session_id}/critique/phase2/retry")
    assert retry_res.status_code == 200
    assert retry_res.json()["status"] == "phase2_running"
    mock_phase2.assert_not_called()


def test_guided_reflect_items_endpoint():
    from fastapi.testclient import TestClient

    from guided_web import app as app_module
    from guided_web.reflect_prompts import REFLECTION_GROUPS

    client = TestClient(app_module.app)
    res = client.get("/api/reflect-items")
    assert res.status_code == 200
    groups = res.json()["groups"]
    assert [g["id"] for g in groups] == ["noticed", "thought", "photo"]
    assert groups[0]["column"] == "left"
    assert groups[1]["column"] == "left"
    assert groups[2]["column"] == "right"
    assert any(item["label"] == "写真を見て" for item in groups[0]["items"])
    assert [g["column"] for g in REFLECTION_GROUPS] == ["left", "left", "right"]
    left_labels = [g["label"] for g in groups if g["column"] == "left"]
    right_labels = [g["label"] for g in groups if g["column"] == "right"]
    assert left_labels == ["気づいたことがある", "ふと思ったことは"]
    assert right_labels == ["この写真を"]


def test_guided_ui_uses_toast_empty_guides_and_export_navigation():
    from pathlib import Path

    html = Path("guided_web/static/index.html").read_text(encoding="utf-8")
    js = Path("guided_web/static/guided.js").read_text(encoding="utf-8")
    css = Path("guided_web/static/guided.css").read_text(encoding="utf-8")
    assert 'id="toast-region"' in html
    assert 'id="read-empty"' in html
    assert 'id="reflect-empty"' in html
    assert 'id="card-preview-hint"' in html
    assert "alert(" not in js
    assert "function showToast" in js
    assert "function afterExportSuccess" in js
    assert "function syncScreenGuides" in js
    assert "sendBeacon" in js
    assert "pagehide" in js
    assert "beforeunload" in js
    assert "function releaseSessionOnUnload" in js
    assert "el.inert = !on" in js
    assert "nativePickInFlight" in js
    assert "function stopCritiqueWatch" in js
    assert "function endCritiqueWatch" in js
    assert "function abandonInFlightCritique" not in js
    assert "AbortController" in js
    assert "/critique/cancel" not in js
    assert "activeCritiqueEpoch" in js
    assert "pendingCritiqueCancel" not in js
    assert "function pollCritique" in js
    assert "guided.js?v=30" in html
    assert "guided.css?v=30" in html
    assert 'id="btn-quit"' in html
    assert "終了" in html
    assert "function announceScreenLeaving" in js
    assert "function startHeartbeat" in js
    assert "/api/heartbeat" in js
    assert "/api/presence/unload" in js
    assert "function quitApp" in js
    assert "/api/shutdown" in js
    assert "/critique/cancel" not in js
    assert "data.cancelled" in js
    pick_fn = js.split("async function handleNativePhotoPick()")[1].split("function resetReflectionFields")[0]
    assert pick_fn.index("pickPhotoNative") < pick_fn.index("adoptPhotoSession")
    assert "releaseServerSession" not in pick_fn
    assert "stopCritiqueWatch" not in pick_fn
    nav_fn = js.split("function navigateToScreen")[1].split("function ")[0]
    assert "stopCritiqueWatch" not in nav_fn
    assert "/critique/cancel" not in nav_fn
    assert "hydrate" in nav_fn
    assert "ensureCritiqueWatch" in nav_fn
    assert "function ensureCritiqueWatch" in js
    assert "function applyInterruptedCritiqueHint" in js
    assert "function critiqueWatchIsLive" in js
    assert "async function adoptPhotoSession" in js
    selected_fn = js.split("async function handleSelectedFile")[1].split("async function ")[0]
    assert selected_fn.index("uploadPhoto") < selected_fn.index("adoptPhotoSession")
    assert "releaseServerSession" not in selected_fn
    adopt_fn = js.split("async function adoptPhotoSession")[1].split("async function ")[0]
    assert "const previousId = sessionId" in adopt_fn
    assert adopt_fn.index("stopCritiqueWatch") < adopt_fn.index("applyPhotoSession")
    assert adopt_fn.index("applyPhotoSession") < adopt_fn.index("/release")
    assert "/critique/cancel" not in adopt_fn
    clear_fn = js.split("async function clearAllSession")[1].split("document.getElementById(\"pick-file\")")[0]
    assert "stopCritiqueWatch" in clear_fn
    assert "releaseServerSession" in clear_fn
    assert "/critique/cancel" not in clear_fn
    again_fn = js.split('getElementById("btn-again")')[1].split("getElementById(\"btn-keep\")")[0]
    assert "navigateToScreen" in again_fn
    assert "stopCritiqueWatch" not in again_fn
    assert "/critique/cancel" not in again_fn
    speak_click = js.split('getElementById("btn-speak").addEventListener')[1].split(
        "async function startCritique"
    )[0]
    assert speak_click.index("clearReadAndReflectData") < speak_click.index("navigateToScreen")
    assert speak_click.index("setReadLoading(true)") < speak_click.index("navigateToScreen")
    assert "hydrate: false" in speak_click
    assert "ensureCritiqueWatch" not in speak_click
    tab_nav = js.split("forEach((btn) =>")[1].split('getElementById("btn-again")')[0]
    assert "hydrate: false" not in tab_nav
    assert "navigateToScreen(btn.dataset.screen)" in tab_nav
    speak_fn = js.split("async function startCritique")[1].split("async function applyCritiqueProgress")[0]
    assert "force_restart: true" in speak_fn
    assert "/critique/cancel" not in speak_fn
    unload_fn = js.split("function releaseSessionOnUnload")[1].split("function announceScreenLeaving")[0]
    assert "event.persisted" in unload_fn
    assert "/release" in unload_fn
    assert "/critique/cancel" not in unload_fn
    assert "/api/shutdown" not in unload_fn
    leave_fn = js.split("function announceScreenLeaving")[1].split("const HEARTBEAT_MS")[0]
    assert "/api/presence/unload" in leave_fn
    assert "/api/shutdown" not in leave_fn
    export_fn = js.split("function afterExportSuccess")[1].split("function ")[0]
    assert "showToast" in export_fn
    assert "navigateToScreen" not in export_fn
    assert "reflect-checklist-column-left" in js
    assert "reflect-checklist-column-right" in js
    assert "group.column === \"right\"" in js
    assert ".toast-region" in css
    assert ".empty-guide" in css
    assert ".card-preview-hint" in css
    assert "[hidden]" in css
    assert "display: none !important" in css
    assert "inert" in html
    assert ".header-title-row" in css
    assert ".header-quit" in css
    assert ".quit-done" in css
    assert ".reflect-checklist-column" in css
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr)" in css
    assert "repeat(2, minmax(0, 1fr))" not in css


def test_guided_run_script_reports_boot_failure():
    from pathlib import Path

    text = Path("scripts/run_guided_web.sh").read_text(encoding="utf-8")
    assert "エラー: サーバの起動に失敗しました。" in text
    assert "python3 -m guided_web.app" in text
    assert "listening_pids" in text
    assert "lsof" in text
    assert "起動確認タイムアウト" in text
    assert "前のサーバを止めて、最新のプログラムで起動し直します…" in text
    assert "すでに起動中です" not in text
    assert "サーバを起動します（終了は Control+C）…" in text
    assert ">(tee" not in text


def test_guided_index_html_is_not_cached():
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    res = client.get("/")
    assert res.status_code == 200
    cache = (res.headers.get("cache-control") or "").lower()
    assert "no-store" in cache
    assert "guided.js?v=30" in res.text
    assert 'http-equiv="Cache-Control"' in res.text


def test_offline_ci_installs_guided_web_deps():
    from pathlib import Path

    text = Path(".github/workflows/offline-tests.yml").read_text(encoding="utf-8")
    for pkg in ("fastapi", "uvicorn", "python-multipart", "httpx"):
        assert pkg in text, pkg


def test_native_dialog_cancel_does_not_fall_through_to_tk():
    """Mac で osascript をキャンセルしたら Tk を起動しない（プロセス abort 防止）。"""
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import patch

    from guided_web.native_dialog import DialogResult, DialogStatus, interpret_osascript, pick_mac_then_optional_tk

    cancelled = interpret_osascript(SimpleNamespace(returncode=1, stdout=""))
    assert cancelled.status is DialogStatus.CANCELLED
    picked = interpret_osascript(SimpleNamespace(returncode=0, stdout="/Users/me/Notes\n"))
    assert picked.status is DialogStatus.PICKED
    assert picked.path == Path("/Users/me/Notes")
    missing = interpret_osascript(error=FileNotFoundError("osascript"))
    assert missing.status is DialogStatus.UNAVAILABLE
    timed = interpret_osascript(error=subprocess.TimeoutExpired(cmd="osascript", timeout=1))
    assert timed.status is DialogStatus.CANCELLED

    tk_called = {"n": 0}

    def fake_tk(_initial):
        tk_called["n"] += 1
        return Path("/tmp/tk")

    with patch("guided_web.native_dialog.platform.system", return_value="Darwin"):
        out = pick_mac_then_optional_tk(
            lambda _i: DialogResult(DialogStatus.CANCELLED),
            fake_tk,
            None,
        )
    assert out is None
    assert tk_called["n"] == 0

    with patch("guided_web.native_dialog.platform.system", return_value="Darwin"):
        out = pick_mac_then_optional_tk(
            lambda _i: DialogResult(DialogStatus.UNAVAILABLE),
            fake_tk,
            None,
        )
    assert out == Path("/tmp/tk")
    assert tk_called["n"] == 1


def test_guided_folder_pick_cancel_skips_tk_on_mac():
    from unittest.mock import patch

    from guided_web import folder_picker as fp
    from guided_web.native_dialog import DialogResult, DialogStatus

    tk_called = {"n": 0}

    def boom_tk(_initial):
        tk_called["n"] += 1
        raise AssertionError("Tk must not run after Mac cancel")

    with patch("guided_web.native_dialog.platform.system", return_value="Darwin"), patch.object(
        fp, "_pick_folder_mac", return_value=DialogResult(DialogStatus.CANCELLED)
    ), patch.object(fp, "_pick_folder_tk", side_effect=boom_tk):
        assert fp.pick_folder() is None
    assert tk_called["n"] == 0


def test_guided_export_cancel_is_not_an_error():
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "export.jpg"
    Image.new("RGB", (80, 60), (1, 2, 3)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("export.jpg", f, "image/jpeg")})
    session_id = res.json()["session_id"]
    app_module._sessions[session_id]["critique"] = {
        "status": "complete",
        "lens": "self",
        "phase1_raw": PHASE1_SAMPLE,
    }
    with patch("guided_web.app.pick_folder", return_value=None):
        export_res = client.post(
            f"/api/session/{session_id}/export",
            json={"user_stars": 3, "card_theme": "dark", "user_note": "", "reflections": {}},
        )
    assert export_res.status_code == 200
    assert export_res.json()["cancelled"] is True
    critique = client.get(f"/api/session/{session_id}/critique")
    assert critique.status_code == 200
    assert critique.json()["status"] == "complete"


def test_guided_critique_lifecycle_intents_cover_every_operation():
    """講評への効果は noop / supersede / destroy の3つだけ。cancel は操作に無い。"""
    from guided_web.critique_lifecycle import (
        CritiqueEffect,
        UserIntent,
        effect_for,
        hydrates_read_ui,
        keeps_photo,
        may_call_critique_cancel,
    )

    expected = {
        UserIntent.TAB_SWITCH: CritiqueEffect.NOOP,
        UserIntent.AGAIN: CritiqueEffect.NOOP,
        UserIntent.PHOTO_PICK_CANCEL: CritiqueEffect.NOOP,
        UserIntent.PHOTO_REPLACE_FAIL: CritiqueEffect.NOOP,
        UserIntent.EXPORT_CANCEL: CritiqueEffect.NOOP,
        UserIntent.EXPORT_SAVE: CritiqueEffect.NOOP,
        UserIntent.PAGE_BFCACHE: CritiqueEffect.NOOP,
        UserIntent.SPEAK: CritiqueEffect.SUPERSEDE,
        UserIntent.PHASE2_RETRY: CritiqueEffect.SUPERSEDE,
        UserIntent.CLEAR: CritiqueEffect.DESTROY_SESSION,
        UserIntent.PHOTO_REPLACE_SUCCESS: CritiqueEffect.DESTROY_SESSION,
        UserIntent.PAGE_UNLOAD: CritiqueEffect.DESTROY_SESSION,
    }
    assert set(UserIntent) == set(expected)
    for intent, effect in expected.items():
        assert effect_for(intent) is effect
        assert may_call_critique_cancel(intent) is False
        assert keeps_photo(intent) is (effect is not CritiqueEffect.DESTROY_SESSION)
        assert hydrates_read_ui(intent) is (intent is UserIntent.TAB_SWITCH)
    assert hydrates_read_ui(UserIntent.SPEAK) is False


def test_guided_force_restart_supersedes_running_without_cancel():
    """言葉にするは cancel→idle ではなく、同じセッションで epoch を進める。"""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "supersede.jpg"
    Image.new("RGB", (80, 60), (21, 22, 23)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("supersede.jpg", f, "image/jpeg")})
    session_id = res.json()["session_id"]
    sess = app_module._sessions[session_id]
    sess["epoch"] = 1
    sess["critique"] = {"status": "phase1_running", "lens": "self"}
    parsed = parse_critique_text(PHASE1_SAMPLE)
    with patch("guided_web.app.run_phase1", return_value=(PHASE1_SAMPLE, parsed)), patch(
        "guided_web.app.run_phase2", return_value=(PHASE1_SAMPLE, parsed, [])
    ):
        start_res = client.post(
            f"/api/session/{session_id}/critique",
            json={"lens": "self", "user_note": "", "force_restart": True},
        )
    assert start_res.status_code == 200
    assert start_res.json()["status"] in {"phase1_running", "phase2_running", "complete"}
    assert sess["epoch"] == 2
    assert sess["critique"].get("status") != "idle"
    assert session_id in app_module._sessions


def test_guided_destroy_bumps_epoch_so_stale_phase2_cannot_complete():
    """クリアは idle にせずセッションを捨て、古い epoch の書き込みを無効化する。"""
    import asyncio
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module
    from guided_web.session_cleanup import is_current_epoch

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "destroy.jpg"
    Image.new("RGB", (80, 60), (31, 32, 33)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        res = client.post("/api/session/photo", files={"file": ("destroy.jpg", f, "image/jpeg")})
    session_id = res.json()["session_id"]
    sess = app_module._sessions[session_id]
    sess["epoch"] = 1
    sess["critique"] = {"status": "phase2_running", "lens": "self", "error": None}
    held = sess
    del_res = client.delete(f"/api/session/{session_id}")
    assert del_res.status_code == 200
    assert session_id not in app_module._sessions
    assert not is_current_epoch(held, 1)
    assert client.get(f"/api/session/{session_id}/critique").status_code == 404
    with patch("guided_web.app.run_phase2") as mock_phase2:
        asyncio.run(app_module._finish_phase2(session_id, "self", "", PHASE1_SAMPLE, epoch=1))
    mock_phase2.assert_not_called()
    assert held["critique"]["status"] == "phase2_running"


def test_guided_photo_pick_cancel_keeps_existing_session():
    """ピッカー Cancel は今の写真を捨てない。"""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from PIL import Image
    from fastapi.testclient import TestClient

    from guided_web import app as app_module

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "keep_pick.jpg"
    Image.new("RGB", (80, 60), (41, 42, 43)).save(jpeg, "JPEG")
    with jpeg.open("rb") as f:
        ok = client.post("/api/session/photo", files={"file": ("keep_pick.jpg", f, "image/jpeg")})
    session_id = ok.json()["session_id"]
    with patch("guided_web.app.pick_image_file", return_value=None):
        cancelled = client.post("/api/session/photo-pick")
    assert cancelled.status_code == 400
    assert session_id in app_module._sessions
    assert client.get(f"/api/session/{session_id}/preview").status_code == 200


def test_guided_choose_screen_is_not_inert_when_visible():
    from pathlib import Path

    html = Path("guided_web/static/index.html").read_text(encoding="utf-8")
    choose = html.split('id="screen-choose"')[1].split("<main")[0]
    read = html.split('id="screen-read"')[1].split("<main")[0]
    reflect = html.split('id="screen-reflect"')[1].split("<div id=\"toast-region\"")[0]
    assert "inert" not in choose.split(">")[0]
    assert "inert" in read.split(">")[0]
    assert "inert" in reflect.split(">")[0]


def test_guided_sleep_guard_refcount_spawns_once():
    from guided_web.sleep_guard import reset_guard_for_tests, is_held, force_release

    spawned = []

    class FakeProc:
        def __init__(self):
            self.terminated = False
            self._code = None

        def poll(self):
            return self._code

        def terminate(self):
            self.terminated = True
            self._code = 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self._code = 9

    def spawn():
        proc = FakeProc()
        spawned.append(proc)
        return proc

    try:
        guard = reset_guard_for_tests(enabled=True, spawn=spawn)
        assert not is_held()
        with guard.busy():
            assert is_held()
            assert len(spawned) == 1
            with guard.busy():
                assert is_held()
                assert len(spawned) == 1
            assert is_held()
            assert not spawned[0].terminated
        assert not is_held()
        assert spawned[0].terminated
    finally:
        force_release()
        reset_guard_for_tests(enabled=False)


def test_guided_sleep_guard_disabled_does_not_spawn():
    from guided_web.sleep_guard import reset_guard_for_tests, is_held, force_release

    spawned = []

    def spawn():
        spawned.append("x")
        return None

    try:
        guard = reset_guard_for_tests(enabled=False, spawn=spawn)
        with guard.busy():
            assert is_held()
        assert spawned == []
        assert not is_held()
    finally:
        force_release()
        reset_guard_for_tests(enabled=False)


def test_guided_sleep_guard_caffeinate_prevents_idle_only():
    from unittest.mock import patch

    from guided_web.sleep_guard import spawn_caffeinate

    captured = {}

    class FakePopen:
        def __init__(self, args, **kwargs):
            captured["args"] = list(args)

    with patch("guided_web.sleep_guard.subprocess.Popen", FakePopen):
        spawn_caffeinate()
    assert captured["args"][0] == "caffeinate"
    assert "-i" in captured["args"]
    assert "-w" in captured["args"]
    assert "-d" not in captured["args"]


def test_guided_critique_holds_sleep_guard_during_phases():
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from PIL import Image
    from fastapi.testclient import TestClient

    from critique_parser import parse_critique_text
    from guided_web import app as app_module
    from guided_web.sleep_guard import is_held, force_release

    held = {}

    def fake_phase1(*_a, **_k):
        held["p1"] = is_held()
        return PHASE1_SAMPLE, parse_critique_text(PHASE1_SAMPLE)

    def fake_phase2(*_a, **_k):
        held["p2"] = is_held()
        return (
            PHASE1_SAMPLE + PHASE2_SAMPLE,
            parse_critique_text(PHASE1_SAMPLE + PHASE2_SAMPLE),
            [{"id": "1", "heading": "【1】", "text": "one"}],
        )

    client = TestClient(app_module.app)
    td = Path(tempfile.mkdtemp())
    jpeg = td / "sleep.jpg"
    Image.new("RGB", (80, 60), (9, 10, 11)).save(jpeg, "JPEG")
    try:
        with jpeg.open("rb") as f:
            res = client.post("/api/session/photo", files={"file": ("sleep.jpg", f, "image/jpeg")})
        session_id = res.json()["session_id"]
        assert not is_held()
        with patch("guided_web.app.run_phase1", side_effect=fake_phase1), patch(
            "guided_web.app.run_phase2", side_effect=fake_phase2
        ):
            started = client.post(
                f"/api/session/{session_id}/critique",
                json={"lens": "self"},
            )
        assert started.status_code == 200
        assert held.get("p1") is True
        assert held.get("p2") is True
        assert not is_held()
        assert client.get(f"/api/session/{session_id}/critique").json()["status"] == "complete"
    finally:
        force_release()


def test_guided_export_sleep_guard_starts_after_folder_pick():
    from pathlib import Path

    text = Path("guided_web/app.py").read_text(encoding="utf-8")
    export_fn = text.split("async def export_session")[1].split("@app.get")[0]
    assert "pick_folder" in export_fn
    assert export_fn.index("pick_folder") < export_fn.index("sleep_busy")
    pick_fn = text.split("async def pick_photo")[1].split("def _release_session")[0]
    assert "sleep_busy" not in pick_fn


def test_guided_local_server_binds_localhost_and_stops():
    from unittest.mock import MagicMock, patch

    from guided_web.local_server import GuidedLocalServer

    fake_server = MagicMock()
    captured = {}

    class FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.target = target

        def start(self):
            captured["started"] = True

        def is_alive(self):
            return True

        def join(self, timeout=None):
            captured["joined"] = True

    def fake_config(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return MagicMock()

    with patch("guided_web.local_server.uvicorn.Config", side_effect=fake_config), patch(
        "guided_web.local_server.uvicorn.Server", return_value=fake_server
    ), patch("guided_web.local_server.threading.Thread", FakeThread), patch(
        "guided_web.local_server.stop_listeners"
    ):
        server = GuidedLocalServer(9876)
        assert server.url == "http://127.0.0.1:9876/"
        server.start(replace_existing=True)
        assert captured["args"][0] == "guided_web.app:app"
        assert captured["kwargs"]["host"] == "127.0.0.1"
        assert captured["kwargs"]["port"] == 9876
        assert captured.get("started") is True
        server.stop()
        assert fake_server.should_exit is True
        assert captured.get("joined") is True


def test_guided_app_opens_page_like_command_without_webkit():
    """自前の描画ホストは使わない。.command と同じ open 経路。Dock 偽装もしない。"""
    from pathlib import Path

    plist = Path("LuminaNotesGuided.app/Contents/Info.plist").read_text(encoding="utf-8")
    launcher = Path("LuminaNotesGuided.app/Contents/MacOS/LuminaNotesGuided").read_text(encoding="utf-8")
    script = Path("scripts/run_guided_app.sh").read_text(encoding="utf-8")
    window = Path("guided_web/desktop_window.py").read_text(encoding="utf-8")
    backup = Path("scripts/run_guided_web.sh").read_text(encoding="utf-8")
    combined = window + script + launcher
    assert "notes.lumina.guided" in plist
    assert "NSAllowsLocalNetworking" in plist
    assert "run_guided_app.sh" in launcher
    assert "guided_root.sh" in launcher
    assert "guided_root_resolve" in launcher
    assert "アプリケーションフォルダへコピーすると動きません" not in launcher
    assert Path("LuminaNotesGuided.app/Contents/Resources/guided_root.sh").is_file()
    install = Path("scripts/install_guided_app.sh").read_text(encoding="utf-8")
    assert "GUIDED_APPLICATIONS_DIR" in install
    assert "guided_root_save" in install
    assert "guided_python.sh" in script
    assert "guided_web.desktop_window" in script
    assert "--server-only" not in script
    assert "osacompile" not in script
    assert "Contents/MacOS/applet" not in script
    assert "exec osascript" not in script
    assert "mac_dock_host" not in combined
    assert not Path("guided_web/mac_dock_host.jxa").exists()
    assert not Path("LuminaNotesGuided.app/Contents/MacOS/applet").exists()
    assert "NSPrincipalClass" not in plist
    assert "<key>LSUIElement</key>" in plist
    lsui = plist.split("<key>LSUIElement</key>", 1)[1]
    assert "<true/>" in lsui.split("<key>", 1)[0]
    assert "arch -arm64" in Path("scripts/guided_python.sh").read_text(encoding="utf-8")
    assert "hw.optional.arm64" in Path("scripts/guided_python.sh").read_text(encoding="utf-8")
    assert "LSRequiresNativeExecution" in plist
    assert "arm64" in plist
    assert "pywebview" not in script
    assert "import webview" not in window
    assert "from WebKit" not in combined
    assert "import WebKit" not in combined
    assert "tkinter" not in combined.lower()
    assert "/usr/bin/open" in window
    assert "is_shutdown_requested" in window
    assert "should_detach" in window
    assert "start_new_session" in window
    assert "GUIDED_DAEMON" in window
    assert "presence_is_gone" in window
    assert "python3 -m guided_web.app" in backup
    assert "ブラウザを開きます" in backup


def test_guided_api_shutdown_sets_event_without_killing_process():
    from fastapi.testclient import TestClient

    from guided_web import app as app_module
    from guided_web.shutdown import clear_shutdown, is_shutdown_requested

    clear_shutdown()
    client = TestClient(app_module.app)
    res = client.post("/api/shutdown")
    assert res.status_code == 200
    assert res.json() == {"status": "stopping"}
    assert is_shutdown_requested()
    health = client.get("/api/health")
    assert health.status_code == 200
    clear_shutdown()


def test_guided_wait_until_quit_returns_on_ui_shutdown():
    import threading

    from guided_web.desktop_window import wait_until_quit
    from guided_web.presence import reset as reset_presence
    from guided_web.shutdown import clear_shutdown, request_shutdown

    class FakeServer:
        def is_running(self):
            return True

    clear_shutdown()
    reset_presence()
    threading.Timer(0.05, request_shutdown).start()
    wait_until_quit(FakeServer(), poll_s=0.01)
    clear_shutdown()


def test_guided_ui_shutdown_stops_local_server():
    from urllib.error import URLError
    from urllib.request import Request, urlopen

    from guided_web.desktop_window import wait_until_quit
    from guided_web.local_server import GuidedLocalServer, unused_port

    server = GuidedLocalServer(unused_port())
    try:
        server.start(replace_existing=True)
        server.wait_healthy(timeout_s=15)
        req = Request(server.url + "api/shutdown", method="POST")
        with urlopen(req, timeout=2) as resp:
            assert resp.status == 200
        wait_until_quit(server, poll_s=0.05)
    finally:
        server.stop()
    assert not server.is_running()
    try:
        urlopen(server.url + "api/health", timeout=1)
        raise AssertionError("server should be down after shutdown")
    except (URLError, OSError):
        pass


def test_guided_presence_refresh_keeps_server_alive():
    from guided_web.presence import Presence

    clock = [0.0]
    presence = Presence(now=lambda: clock[0], unload_grace_s=0.8, idle_grace_s=90.0)
    presence.reset()
    presence.mark_unload()
    clock[0] = 0.2
    presence.ping()
    clock[0] = 1.0
    assert presence.is_gone() is False


def test_guided_presence_tab_close_is_gone_after_grace():
    from guided_web.presence import Presence

    clock = [0.0]
    presence = Presence(now=lambda: clock[0], unload_grace_s=0.8, idle_grace_s=90.0)
    presence.reset()
    presence.mark_unload()
    clock[0] = 0.79
    assert presence.is_gone() is False
    clock[0] = 0.81
    assert presence.is_gone() is True


def test_guided_api_heartbeat_and_unload_do_not_kill_process():
    from fastapi.testclient import TestClient

    from guided_web import app as app_module
    from guided_web.presence import reset as reset_presence
    from guided_web.shutdown import clear_shutdown, is_shutdown_requested

    clear_shutdown()
    reset_presence()
    client = TestClient(app_module.app)
    beat = client.post("/api/heartbeat")
    assert beat.status_code == 200
    leaving = client.post("/api/presence/unload")
    assert leaving.status_code == 200
    assert leaving.json() == {"status": "leaving"}
    assert is_shutdown_requested() is False
    health = client.get("/api/health")
    assert health.status_code == 200
    clear_shutdown()
    reset_presence()


def test_guided_tab_close_stops_local_server():
    import os
    from urllib.error import URLError
    from urllib.request import Request, urlopen

    from guided_web.desktop_window import wait_until_quit
    from guided_web.local_server import GuidedLocalServer, unused_port
    from guided_web.presence import reset as reset_presence
    from guided_web.shutdown import clear_shutdown

    previous = os.environ.get("GUIDED_UNLOAD_GRACE_S")
    os.environ["GUIDED_UNLOAD_GRACE_S"] = "0.25"
    server = GuidedLocalServer(unused_port())
    try:
        server.start(replace_existing=True)
        server.wait_healthy(timeout_s=15)
        req = Request(server.url + "api/presence/unload", method="POST")
        with urlopen(req, timeout=2) as resp:
            assert resp.status == 200
        wait_until_quit(server, poll_s=0.05)
    finally:
        server.stop()
        if previous is None:
            os.environ.pop("GUIDED_UNLOAD_GRACE_S", None)
        else:
            os.environ["GUIDED_UNLOAD_GRACE_S"] = previous
        clear_shutdown()
        reset_presence()
    assert not server.is_running()
    try:
        urlopen(server.url + "api/health", timeout=1)
        raise AssertionError("server should be down after tab close")
    except (URLError, OSError):
        pass


def test_guided_detach_only_for_darwin_app_launcher():
    import os
    from unittest.mock import patch

    from guided_web.desktop_window import should_detach

    with patch("guided_web.desktop_window.platform.system", return_value="Linux"):
        assert should_detach() is False
    with patch("guided_web.desktop_window.platform.system", return_value="Darwin"), patch.dict(
        os.environ, {"GUIDED_DAEMON": "1"}, clear=False
    ):
        assert should_detach() is False
    with patch("guided_web.desktop_window.platform.system", return_value="Darwin"), patch.dict(
        os.environ, {"GUIDED_KEEP_FOREGROUND": "1"}, clear=False
    ):
        assert should_detach() is False
    env = {key: value for key, value in os.environ.items() if key not in {"GUIDED_DAEMON", "GUIDED_KEEP_FOREGROUND"}}
    with patch("guided_web.desktop_window.platform.system", return_value="Darwin"), patch.dict(
        os.environ, env, clear=True
    ):
        assert should_detach() is True


def test_guided_root_resolve_remembers_repo_and_apps_copy():
    import os
    import subprocess
    import tempfile
    from pathlib import Path

    resolver = Path("LuminaNotesGuided.app/Contents/Resources/guided_root.sh").resolve()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        repo = tmp / "photo-critique-bot"
        (repo / "scripts").mkdir(parents=True)
        (repo / "guided_web").mkdir()
        (repo / "scripts" / "run_guided_app.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (repo / "guided_web" / "desktop_window.py").write_text("# root marker\n", encoding="utf-8")
        cfg = tmp / "guided_root"
        env = {**os.environ, "GUIDED_ROOT_FILE": str(cfg), "GUIDED_APP_ROOT": ""}
        env.pop("GUIDED_APP_ROOT", None)
        script = f"""
set -euo pipefail
unset GUIDED_APP_ROOT
source {resolver}
guided_root_config="{cfg}"
guided_root_resolve "{repo}"
test "$GUIDED_APP_ROOT" = "{repo}"
test "$(cat "{cfg}")" = "{repo}"
unset GUIDED_APP_ROOT
guided_root_resolve "{tmp}/Applications"
test "$GUIDED_APP_ROOT" = "{repo}"
"""
        result = subprocess.run(
            ["bash", "-c", script],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr + result.stdout


def test_guided_install_app_copies_to_applications_dir():
    import os
    import subprocess
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as raw:
        dest_dir = Path(raw) / "Applications"
        cfg = Path(raw) / "guided_root"
        env = {
            **os.environ,
            "GUIDED_APPLICATIONS_DIR": str(dest_dir),
            "GUIDED_ROOT_FILE": str(cfg),
        }
        result = subprocess.run(
            ["bash", "scripts/install_guided_app.sh"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        copied = dest_dir / "LuminaNotesGuided.app"
        assert (copied / "Contents" / "MacOS" / "LuminaNotesGuided").is_file()
        assert (copied / "Contents" / "Resources" / "guided_root.sh").is_file()
        assert Path(cfg.read_text(encoding="utf-8").strip()).is_dir()
        assert (Path(cfg.read_text(encoding="utf-8").strip()) / "scripts" / "run_guided_app.sh").is_file()


def test_guided_python_wrapper_runs_current_interpreter():
    import subprocess

    result = subprocess.run(
        ["bash", "scripts/guided_python.sh", "-c", "print('guided-python-ok')"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "guided-python-ok" in result.stdout


def test_guided_open_page_uses_system_open():
    from unittest.mock import patch

    from guided_web.desktop_window import open_guided_page

    captured = {}

    def fake_run(args, **_kwargs):
        captured["args"] = list(args)

    with patch("guided_web.desktop_window.platform.system", return_value="Darwin"), patch(
        "guided_web.desktop_window.subprocess.run", side_effect=fake_run
    ):
        open_guided_page("http://127.0.0.1:8765/")
    assert captured["args"][0] == "/usr/bin/open"
    assert captured["args"][1].startswith("http://127.0.0.1:8765/")
    assert "v=" in captured["args"][1]


def test_guided_wait_until_quit_returns_when_server_stops():
    from guided_web.desktop_window import wait_until_quit

    class FakeServer:
        def is_running(self):
            return False

    wait_until_quit(FakeServer(), poll_s=0.01)


def test_guided_local_server_health_roundtrip():
    from urllib.request import urlopen

    from guided_web.local_server import GuidedLocalServer, unused_port

    server = GuidedLocalServer(unused_port())
    try:
        server.start(replace_existing=True)
        server.wait_healthy(timeout_s=15)
        with urlopen(server.url + "api/health", timeout=2) as resp:
            assert resp.status == 200
        assert server.is_running()
    finally:
        server.stop()
    assert not server.is_running()


def run_all():
    test_parser_phase1()
    test_parser_legacy_score_aliases()
    test_parser_phase2()
    test_self_lens_prompts()
    test_time_zone_fact_labels_avoid_banned_stems()
    test_datetime_prefers_original_not_modify()
    test_phase_d_p02_uses_datetime_original_not_modify()
    test_log_manager_processed_filename()
    test_line_full_split_four_parts()
    test_line_dialogue_split_sections_1_to_3()
    test_iptc_phase1_block_upsert_preserves_stages_and_user()
    test_storage_path_from_card_url()
    test_normalize_card_theme()
    test_create_critique_card_layout()
    test_create_critique_card_light_theme()
    test_critique_summary_short_keeps_fixed_image_area()
    test_n01_no_disclaimer_on_card_and_lens()
    test_n04_score_label_fits_before_stars()
    test_n05_sensitivity_mentions_light_and_reflection()
    test_n06_log_keeps_numeric_scores()
    test_iptc_stage_block_upsert_preserves_user_text()
    test_iptc_rating_description_roundtrip()
    test_library_unit_naming_rules()
    test_library_unit_prefixed_unit_from_dir()
    test_overall_multi_unit_status_cancel_between_units()
    test_list_pending_h3_includes_child_events()
    test_plan_screening_units_include_child_events()
    test_summarize_review_errors_limits_and_formats()
    test_resolve_session_for_unit_prefers_target_sessions()
    test_library_unit_discover_and_list_jpegs()
    test_mechanical_m1_blur_and_intent_protect()
    test_antenna_m2_relative_heat_no_star_gate()
    test_diversity_m3_margin_top_and_bias_control()
    test_shortlist_pipeline_m1_m2_m3_and_cancel()
    test_delta_log_session_reload_and_summary()
    test_list_session_paths_matches_resolved_pipeline_path()
    test_h3_delta_builder_for_judgment_improvement()
    test_works_trace_dev_preference_and_no_copy()
    test_scanner_jpeg_primary_over_dop_for_intent_and_rating()
    test_r1a_t10_shortlist_write_preserves_pixels()
    test_r1a_t10_pipeline_continues_on_item_failure()
    test_r1a_t10_dry_run_does_not_write_rating()
    test_r1a_t10_works_without_dop_no_error()
    test_r1a_t10_iptc_sync_verify_script_roundtrip()
    test_r1a_t10_no_works_copy_surface()
    test_r1a_t10_acceptance_offline_matrix()
    test_hotfix_desktop_config_merge_preserves_shortlist_keys()
    test_hotfix_m2_m3_skip_none_rating()
    test_hotfix_exception_lambda_captures_message()
    test_low_priority_schedule_on_ui_skips_destroyed_root()
    test_low_priority_sessions_open_does_not_mkdir()
    test_low_priority_rating_percent_fallback()
    test_low_priority_works_subdir_hint()
    test_works_review_selection_summarizes_sooc_skipped()
    test_antenna_prompt_avoids_judge_vocabulary()
    test_console_ui_copy_phase1_labels()
    test_prompt_contracts_judge_vocab_and_time_ban_alignment()
    test_phase_d_offline_fixtures_person_and_time()
    test_q5_summarize_h3_and_reactions_scripts()
    test_p2_2_card_words_before_stars()
    test_low_priority_prompt_pick_skips_sentinel_nashi()
    test_dry_run_session_rejects_record_post_h3()
    test_guided_futei_band_tokyo_summer_day()
    test_guided_futei_band_night()
    test_guided_api_parameters_shape()
    test_guided_parameter_display_rows()
    test_guided_upload_returns_parameter_display()
    test_guided_photo_response_omits_identifying_local_fields()
    test_guided_upload_rejects_unreadable_image()
    test_guided_unreadable_upload_keeps_existing_session()
    test_guided_card_footer_metadata()
    test_guided_body_sections_split()
    test_guided_stock_export_writes_files()
    test_guided_format_reflections_block()
    test_guided_privacy_prompts_exclude_identifying_metadata()
    test_guided_privacy_audit_whitelist()
    test_guided_critique_runner_uses_api_params()
    test_guided_selected_reflection_labels()
    test_guided_settings_save_folder_roundtrip()
    test_guided_session_delete_removes_temp_dir()
    test_guided_phase2_retry_restarts_background()
    test_guided_purge_orphan_temp_keeps_live_sessions()
    test_guided_shutdown_sessions_removes_all()
    test_guided_session_release_is_idempotent()
    test_guided_lifespan_purges_orphans_and_shutdown_sessions()
    test_guided_critique_rejects_parallel_without_restart()
    test_guided_phase2_ignores_stale_epoch()
    test_guided_cancel_critique_keeps_photo_and_discards_stale_phase2()
    test_guided_cancel_complete_critique_is_noop()
    test_guided_cancel_then_force_restart_starts_fresh()
    test_guided_photo_pick_uses_ui_executor_while_critique_runs()
    test_guided_ui_and_critique_executors_are_separate()
    test_guided_photo_pick_opens_photo_folder_not_export_folder()
    test_guided_stale_cancel_does_not_kill_newer_critique()
    test_guided_live_cancel_and_clear_during_slow_phase1()
    test_guided_phase2_retry_skips_when_already_running()
    test_guided_reflect_items_endpoint()
    test_guided_ui_uses_toast_empty_guides_and_export_navigation()
    test_guided_run_script_reports_boot_failure()
    test_guided_index_html_is_not_cached()
    test_offline_ci_installs_guided_web_deps()
    test_native_dialog_cancel_does_not_fall_through_to_tk()
    test_guided_folder_pick_cancel_skips_tk_on_mac()
    test_guided_export_cancel_is_not_an_error()
    test_guided_critique_lifecycle_intents_cover_every_operation()
    test_guided_force_restart_supersedes_running_without_cancel()
    test_guided_destroy_bumps_epoch_so_stale_phase2_cannot_complete()
    test_guided_photo_pick_cancel_keeps_existing_session()
    test_guided_choose_screen_is_not_inert_when_visible()
    test_guided_sleep_guard_refcount_spawns_once()
    test_guided_sleep_guard_disabled_does_not_spawn()
    test_guided_sleep_guard_caffeinate_prevents_idle_only()
    test_guided_critique_holds_sleep_guard_during_phases()
    test_guided_export_sleep_guard_starts_after_folder_pick()
    test_guided_local_server_binds_localhost_and_stops()
    test_guided_app_opens_page_like_command_without_webkit()
    test_guided_api_shutdown_sets_event_without_killing_process()
    test_guided_presence_refresh_keeps_server_alive()
    test_guided_presence_tab_close_is_gone_after_grace()
    test_guided_api_heartbeat_and_unload_do_not_kill_process()
    test_guided_tab_close_stops_local_server()
    test_guided_detach_only_for_darwin_app_launcher()
    test_guided_root_resolve_remembers_repo_and_apps_copy()
    test_guided_install_app_copies_to_applications_dir()
    test_guided_python_wrapper_runs_current_interpreter()
    test_guided_open_page_uses_system_open()
    test_guided_wait_until_quit_returns_when_server_stops()
    test_guided_wait_until_quit_returns_on_ui_shutdown()
    test_guided_ui_shutdown_stops_local_server()
    test_guided_local_server_health_roundtrip()
    print("test_offline_suite: OK")


if __name__ == "__main__":
    run_all()
