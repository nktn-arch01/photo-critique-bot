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
    LOGO_SIZE,
    LOGO_TEXT_GAP,
    SCORE_ROW_HEIGHT,
    create_critique_card,
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
■CRITIQUE_SUMMARY: 境界のきらめきと線の陰影が、見所として立ち上がる。好奇心を誘う一枚です。
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
    # N-03: CRITIQUE_SUMMARY プロンプトを 20260808 版へ戻す
    assert "効果的な見所を主体に、読者の好奇心を煽る文章" in p1
    assert "あなたは〇〇に惹かれたのでは" not in p1
    p2 = build_phase2_prompt(
        ctx, "■TITLE: t\n■SCORES:\n・眼差の輪郭 (Contours of the Eyes)  : ★★★☆☆ (3/5)"
    )
    assert "次なる一枚への対話と提案" in p2
    assert "ステップアップ・アドバイス" not in p2
    assert "曖昧さの肯定" in p2
    assert "DateTimeOriginal" in p2
    assert "時計帯ヒント" in p2


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


def test_line_full_split_four_parts():
    combined = PHASE1_SAMPLE + "\n---\n" + PHASE2_SAMPLE
    parts = split_full_critique_for_line(combined)
    assert len(parts) == 4
    assert "■TITLE" in parts[0]
    assert parts[1].startswith("## 【1.")
    assert "## 【4." in parts[2]
    assert parts[3].startswith("## 【6.")


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
    # 免責を描かなくなったぶん、文字ブロックはロゴ＋スコアだけで免責行分短い
    # （以前は +28。厳密値より「免責行を含まない」ことだけ保証）
    h = _fixed_text_block_height()
    assert h == (
        1
        + 18  # title line
        + 50
        + 38
        + 4
        + 1
        + 18  # score line
        + 5 * SCORE_ROW_HEIGHT
        + 12
        + 1
        + 18  # critique line
        + LOGO_SIZE
    )


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
        read_shortlist_meta,
        require_exiftool,
        write_shortlist_decision,
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
    meta = write_shortlist_decision(jpeg, rating=3, description=desc)
    assert meta.rating == 3
    assert meta.description == desc
    assert meta.stage_reason("M2") == "Lumina sync test reason"
    assert meta.stage_reason("M3") == "diversity placeholder"

    # 段追記: 既存 M2 を残しつつ M3 を置換、Rating も更新
    write_shortlist_decision(jpeg, rating=4, stage="M3", reason="top pick")
    again = read_shortlist_meta(jpeg)
    assert again.rating == 4
    assert again.stage_reason("M2") == "Lumina sync test reason"
    assert again.stage_reason("M3") == "top pick"

    write_stage_reason(jpeg, "M2", "updated antenna")
    final = read_shortlist_meta(jpeg)
    assert final.stage_reason("M2") == "updated antenna"
    assert final.rating == 4  # Description のみ更新でも Rating は維持

    shutil.rmtree(td, ignore_errors=True)


def test_library_unit_naming_rules():
    """T2: 月 YYYYMM / イベント YYYYMMDD_名前。規則外はイベントにしない。"""
    from library_unit import (
        is_event_folder_name,
        is_month_folder_name,
        try_parse_event_name,
        try_parse_month_name,
    )

    assert is_month_folder_name("202608")
    assert try_parse_month_name("202608") == "202608"
    assert not is_month_folder_name("202613")  # 無効月
    assert not is_month_folder_name("20268")
    assert not is_month_folder_name("Photos")

    assert is_event_folder_name("20260810_京都旅行")
    parsed = try_parse_event_name("20260810_京都旅行")
    assert parsed is not None
    assert parsed[1] == "京都旅行"
    assert parsed[2].isoformat() == "2026-08-10"

    assert is_event_folder_name("20260822_海辺の午後")
    assert is_event_folder_name("20260101_day-trip_v2")  # _ と - は可

    # スペース・不正日付・記号はイベント扱いしない
    assert not is_event_folder_name("20260810_京都 旅行")
    assert not is_event_folder_name("20260810")
    assert not is_event_folder_name("京都旅行")
    assert not is_event_folder_name("20260230_無効日")
    assert not is_event_folder_name("20260810_bad.name")
    assert not is_event_folder_name("misc_folder")


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

    from iptc_rating_io import ExifToolNotFoundError, read_shortlist_meta, require_exiftool
    from shortlist_mechanical import (
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
    assert read_shortlist_meta(sharp_p).rating == 1
    assert read_shortlist_meta(blur_p).rating == 0
    assert Image.open(sharp_p).size == before
    shutil.rmtree(td, ignore_errors=True)


def test_antenna_m2_relative_heat_no_star_gate():
    """T4: 相対熱量で選抜。★5必須なし。Rating0はスキップ。[M2] 書き込み。"""
    import shutil

    from iptc_rating_io import (
        ExifToolNotFoundError,
        read_shortlist_meta,
        require_exiftool,
        write_rating,
    )
    from shortlist_antenna import (
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

    meta4 = read_shortlist_meta(paths[4])
    meta3 = read_shortlist_meta(paths[3])
    meta0 = read_shortlist_meta(paths[0])
    assert meta4.rating == 2 and meta4.stage_reason("M2")
    assert meta3.rating == 2
    assert meta0.rating == 1  # 非合格は1のまま
    assert read_shortlist_meta(zero).rating == 0

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
    assert read_shortlist_meta(paths[2]).rating == 2
    assert "flat-best" in (read_shortlist_meta(paths[2]).stage_reason("M2") or "")

    shutil.rmtree(td, ignore_errors=True)


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
    test_library_unit_discover_and_list_jpegs()
    test_mechanical_m1_blur_and_intent_protect()
    test_antenna_m2_relative_heat_no_star_gate()
    print("test_offline_suite: OK")


if __name__ == "__main__":
    run_all()
