"""JPEG 内 Rating / Description（スクリーニングメタ）の単一ソース I/O.

R1′-A §0 / §5.1 / docs/IPTC_SYNC_VERIFICATION.md のタグ契約に従う。
`.dop` / `.xmp` サイドカーは扱わない。書き込みは exiftool 経由。

説明の段ラベル（[M2]/[M3]）は「ブロック置換」で固定:
- 既存の同ラベル行があればその行だけ置き換える
- 無ければ末尾に追記する
- ラベル無しのユーザー文は消さない
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# --- 書き込みタグ契約（検証ドキュメントと同一） ---
WRITE_RATING_TAGS = (
    "Rating",
    "XMP:Rating",
    "RatingPercent",
)
WRITE_DESCRIPTION_TAGS = (
    "ImageDescription",
    "XMP-dc:Description",
    "IPTC:Caption-Abstract",
)

READ_TAGS = (
    "Rating",
    "XMP:Rating",
    "RatingPercent",
    "ImageDescription",
    "XMP-dc:Description",
    "IPTC:Caption-Abstract",
)

StageLabel = Literal["M2", "M3"]
STAGE_LABELS: tuple[StageLabel, ...] = ("M2", "M3")

_STAGE_LINE_RE = re.compile(r"^\[(M2|M3)\]\s*(.*)$")


class ExifToolNotFoundError(RuntimeError):
    """exiftool が PATH にない。"""


class ExifToolError(RuntimeError):
    """exiftool 実行失敗。"""


class IptcIoError(ValueError):
    """引数・ファイル状態の不正。"""


@dataclass(frozen=True)
class ScreeningMeta:
    """JPEG から読んだスクリーニング用メタ（一次ソース）。"""

    path: Path
    rating: int | None
    description: str
    raw_tags: dict[str, str]

    def stage_reason(self, stage: StageLabel) -> str | None:
        return parse_stage_blocks(self.description).get(stage)


# Wave 3 互換 alias（1リリース据え置き）
ShortlistMeta = ScreeningMeta


def require_exiftool() -> str:
    path = shutil.which("exiftool")
    if not path:
        raise ExifToolNotFoundError(
            "exiftool が見つかりません。インストールしてから再実行してください。"
        )
    return path


def rating_to_percent(rating: int) -> int:
    """0–5 → RatingPercent（Microsoft 互換の目安: rating×20）。"""
    if not isinstance(rating, int) or rating < 0 or rating > 5:
        raise IptcIoError(f"rating は 0–5 の整数である必要があります: {rating!r}")
    return rating * 20


def percent_to_rating(percent: object) -> int | None:
    """RatingPercent → 0–5（``rating_to_percent`` の逆。近い値は四捨五入）.

    ``Rating`` / ``XMP:Rating`` が無い JPEG（Windows 互換など）向けのフォールバック。
    """
    if percent is None:
        return None
    try:
        p = int(round(float(str(percent).strip())))
    except (TypeError, ValueError):
        return None
    if p < 0 or p > 100:
        return None
    rating = int(round(p / 20.0))
    if 0 <= rating <= 5:
        return rating
    return None


def _run_exiftool(args: list[str]) -> subprocess.CompletedProcess[str]:
    exiftool = require_exiftool()
    proc = subprocess.run(
        [exiftool, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ExifToolError(proc.stderr.strip() or proc.stdout.strip() or "exiftool failed")
    return proc


def _ensure_jpeg_path(path: Path | str) -> Path:
    p = Path(path)
    if not p.is_file():
        raise IptcIoError(f"ファイルがありません: {p}")
    return p


def read_raw_tags(path: Path | str) -> dict[str, str]:
    """契約タグを exiftool -json で読む（キーは短縮名になり得る）。"""
    jpeg = _ensure_jpeg_path(path)
    args = ["-json", "-s", *[f"-{t}" for t in READ_TAGS], str(jpeg)]
    proc = _run_exiftool(args)
    if not proc.stdout.strip():
        raise ExifToolError("exiftool read returned empty output")
    data = json.loads(proc.stdout)[0]
    data.pop("SourceFile", None)
    return {str(k): str(v) for k, v in data.items() if v is not None and str(v) != ""}


def _parse_rating(raw: dict[str, str]) -> int | None:
    """Rating / XMP:Rating を優先。無ければ RatingPercent から復元（L3）。"""
    for key in ("Rating", "XMP:Rating"):
        val = raw.get(key)
        if val is None:
            continue
        try:
            n = int(float(str(val).strip()))
        except ValueError:
            continue
        if 0 <= n <= 5:
            return n
    for key in ("RatingPercent",):
        got = percent_to_rating(raw.get(key))
        if got is not None:
            return got
    return None


def _pick_description(raw: dict[str, str]) -> str:
    for key in ("ImageDescription", "Description", "Caption-Abstract", "XMP-dc:Description"):
        val = raw.get(key)
        if val is not None and str(val).strip() != "":
            return str(val)
    return ""


def read_screening_meta(path: Path | str) -> ScreeningMeta:
    jpeg = _ensure_jpeg_path(path)
    raw = read_raw_tags(jpeg)
    return ScreeningMeta(
        path=jpeg,
        rating=_parse_rating(raw),
        description=_pick_description(raw),
        raw_tags=raw,
    )


# Wave 3 互換 alias
read_shortlist_meta = read_screening_meta


def write_rating(path: Path | str, rating: int) -> None:
    jpeg = _ensure_jpeg_path(path)
    percent = rating_to_percent(rating)
    args = ["-overwrite_original", f"-Rating={rating}", f"-XMP:Rating={rating}", f"-RatingPercent={percent}", str(jpeg)]
    _run_exiftool(args)


def write_description(path: Path | str, description: str) -> None:
    jpeg = _ensure_jpeg_path(path)
    if description is None:
        raise IptcIoError("description が None です")
    args = [
        "-overwrite_original",
        f"-ImageDescription={description}",
        f"-XMP-dc:Description={description}",
        f"-IPTC:Caption-Abstract={description}",
        str(jpeg),
    ]
    _run_exiftool(args)


def write_rating_and_description(path: Path | str, rating: int, description: str) -> None:
    """Rating と Description を一回の exiftool で書く（検証スクリプトと同一契約）。"""
    jpeg = _ensure_jpeg_path(path)
    percent = rating_to_percent(rating)
    if description is None:
        raise IptcIoError("description が None です")
    args = [
        "-overwrite_original",
        f"-Rating={rating}",
        f"-XMP:Rating={rating}",
        f"-RatingPercent={percent}",
        f"-ImageDescription={description}",
        f"-XMP-dc:Description={description}",
        f"-IPTC:Caption-Abstract={description}",
        str(jpeg),
    ]
    _run_exiftool(args)


def parse_stage_blocks(description: str) -> dict[StageLabel, str]:
    """説明文から [M2]/[M3] の本文を取り出す（最後に現れた行を採用）。"""
    found: dict[StageLabel, str] = {}
    if not description:
        return found
    for line in description.splitlines():
        m = _STAGE_LINE_RE.match(line.strip())
        if not m:
            continue
        stage = m.group(1)  # type: ignore[assignment]
        found[stage] = m.group(2).strip()
    return found


def format_rating_display(rating: int | None) -> str:
    """講評／ログ表示用の ★ 文字列。None は「なし」。"""
    if rating is None:
        return "なし"
    if not isinstance(rating, int) or rating < 0 or rating > 5:
        return "なし"
    return "★" * rating + "☆" * (5 - rating) + f" ({rating}/5)"


def strip_stage_reason_lines(description: str) -> str:
    """説明から [M2]/[M3] 行を除き、ユーザー文・その他だけを残す（講評の意図注入用）。"""
    if not description:
        return ""
    kept: list[str] = []
    for line in description.splitlines():
        if _STAGE_LINE_RE.match(line.strip()):
            continue
        kept.append(line)
    # 前後の空行を整理（中間の空行は維持）
    text = "\n".join(kept).strip()
    return text


def upsert_stage_reason(description: str, stage: StageLabel, reason: str) -> str:
    """段ラベル行をブロック置換。他行（ユーザー文・他段）は残す。"""
    if stage not in STAGE_LABELS:
        raise IptcIoError(f"未知の段ラベル: {stage!r}")
    reason_one_line = " ".join(str(reason).splitlines()).strip()
    new_line = f"[{stage}] {reason_one_line}".rstrip()

    text = description or ""
    lines = text.splitlines()
    replaced = False
    out: list[str] = []
    for line in lines:
        m = _STAGE_LINE_RE.match(line.strip())
        if m and m.group(1) == stage:
            if not replaced:
                out.append(new_line)
                replaced = True
            # 同一ラベルの重複行は落とす（単一ブロック）
            continue
        out.append(line)

    if not replaced:
        if out and out[-1].strip() != "":
            out.append(new_line)
        elif not out:
            out.append(new_line)
        else:
            out.append(new_line)

    # 末尾の空行は1つまでに整える（ユーザー空行は中間は維持）
    while len(out) > 1 and out[-1] == "" and out[-2] == "":
        out.pop()
    return "\n".join(out)


def write_stage_reason(path: Path | str, stage: StageLabel, reason: str) -> str:
    """既存説明を読み、段理由を upsert して書き戻す。新しい説明全文を返す。"""
    meta = read_screening_meta(path)
    updated = upsert_stage_reason(meta.description, stage, reason)
    write_description(path, updated)
    return updated


def write_screening_decision(
    path: Path | str,
    *,
    rating: int,
    stage: StageLabel | None = None,
    reason: str | None = None,
    description: str | None = None,
) -> ScreeningMeta:
    """スクリーニング1コマ分の書き込みヘルパ。

    - ``description`` を渡すとその全文を書く
    - さもなくば既存説明を読み、``stage``+``reason`` があれば upsert して書く
    - どちらも無ければ Rating のみ更新
    """
    jpeg = _ensure_jpeg_path(path)
    if description is not None:
        final_desc = description
    elif stage is not None and reason is not None:
        current = read_screening_meta(jpeg).description
        final_desc = upsert_stage_reason(current, stage, reason)
    else:
        write_rating(jpeg, rating)
        return read_screening_meta(jpeg)

    write_rating_and_description(jpeg, rating, final_desc)
    return read_screening_meta(jpeg)


# Wave 3 互換 alias
write_shortlist_decision = write_screening_decision
