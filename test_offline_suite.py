"""
API キー・ネットワーク不要の回帰テスト一式。
push 前: python3 test_offline_suite.py
"""

from pathlib import Path
import tempfile

from PIL import Image

from critique_parser import parse_critique_text, is_valid_phase2_content
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
    create_critique_card,
    _fixed_text_block_height,
)
from line_messaging import split_full_critique_for_line
from log_manager import DesktopLogManager
from privacy_utils import storage_path_from_card_url

CARD_SAMPLE = """
■TITLE: 魅惑のメカニズム
■SUMMARY: 研ぎ澄まされた金属美
■SCORES:
・構図・構成  : ★★★★☆ (4/5)
・光・色彩    : ★★★★★ (5/5)
・ストーリー  : ★★★☆☆ (3/5)
・技術・露出  : ★★★★★ (5/5)
・独自・世界観: ★★★★☆ (4/5)
■CRITIQUE_SUMMARY: 光と質感が織りなす印象的な情景。機械的な線と陰影が新しい視点を与えます。
"""

PHASE1_SAMPLE = """
■TITLE: 試験タイトル
■SUMMARY: キャッチ
■SCORES:
・構図・構成  : ★★★☆☆ (3/5)
・光・色彩    : ★★★★☆ (4/5)
■CRITIQUE_SUMMARY: 要約文です。
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


def test_parser_phase2():
    assert is_valid_phase2_content(PHASE2_SAMPLE)
    p = parse_critique_text(PHASE2_SAMPLE)
    assert p["has_valid_phase2"]


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
■TITLE: 魅惑のメカニズム
■SUMMARY: 研ぎ澄まされた金属美
■SCORES:
・構図・構成  : ★★★★☆ (4/5)
・光・色彩    : ★★★★★ (5/5)
・ストーリー  : ★★★☆☆ (3/5)
・技術・露出  : ★★★★★ (5/5)
・独自・世界観: ★★★★☆ (4/5)
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


def run_all():
    test_parser_phase1()
    test_parser_phase2()
    test_log_manager_processed_filename()
    test_line_full_split_four_parts()
    test_storage_path_from_card_url()
    test_normalize_card_theme()
    test_create_critique_card_layout()
    test_create_critique_card_light_theme()
    test_critique_summary_short_keeps_fixed_image_area()
    print("test_offline_suite: OK")


if __name__ == "__main__":
    run_all()
