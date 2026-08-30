"""Guided Web 向け API 送信の最小化・監査。

ローカルには scanner 全文（meta_block）を残し、Vision API プロンプトには
``GuidedApiParameters`` 相当の抽象フィールドのみ渡す。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_vision import DEFAULT_OPENAI_MODEL
from critique_lens import CritiqueLens, get_lens, normalize_lens
from critique_prompts import (
    PROMPT_MISSING,
    _scores_meaning_block,
    get_system_role,
    phase1_output_slots,
    sanitize_str,
)
from guided_web.light_prompt_variants import DEFAULT_VARIANT, extra_phase1_rules, present_light_hint
from prompt_contracts import (
    EAST_WEST_REWRITE_NOTE_PHASE1,
    EAST_WEST_REWRITE_NOTE_PHASE2,
    east_west_phase_accept,
)

_AUDIT_PATH = Path.home() / ".lumina_notes" / "guided_api_audit.jsonl"

# プロンプトに載せてよい API 抽象キー（構想 §7.2 / §7.3）
ALLOWED_IMAGE_KEYS = frozenset(
    {"image_id", "size", "shot_at", "timezone", "region", "time_band", "light_hint"}
)
ALLOWED_CAMERA_KEYS = frozenset(
    {
        "focal_length",
        "aperture",
        "shutter_speed",
        "iso",
        "mode",
        "exposure_compensation",
    }
)

# ローカル詳細メタから API に送ってはいけない代表キー（回帰テスト用）
FORBIDDEN_PROMPT_MARKERS = (
    "camera_model",
    "lens_model",
    "preset_name",
    "content_headline",
    "GPSLatitude",
    "シリアル",
    "iptc",
    "Rating（JPEG",
    "#カメラ_",
    "#レンズ_",
)


@dataclass(frozen=True)
class GuidedCritiqueContext:
    """Vision API プロンプト用の抽象コンテキスト（個人特定・機体固有情報なし）。"""

    user_intent: str
    image_id: str
    size: str
    shot_at: str
    timezone: str
    region: str
    time_band: str
    light_hint: str
    focal_length: str
    aperture: str
    shutter_speed: str
    iso: str
    mode: str
    exposure_compensation: str

    @classmethod
    def from_api_params(
        cls,
        api_params: dict[str, Any],
        *,
        user_note: str = "",
    ) -> GuidedCritiqueContext:
        image = api_params.get("image") or {}
        camera = api_params.get("camera") or {}
        note = (user_note or "").strip()
        return cls(
            user_intent=sanitize_str(note) if note else PROMPT_MISSING,
            image_id=sanitize_str(image.get("image_id")),
            size=sanitize_str(image.get("size")),
            shot_at=sanitize_str(image.get("shot_at")),
            timezone=sanitize_str(image.get("timezone")),
            region=sanitize_str(image.get("region")),
            time_band=sanitize_str(image.get("time_band")),
            light_hint=sanitize_str(image.get("light_hint")),
            focal_length=sanitize_str(camera.get("focal_length")),
            aperture=sanitize_str(camera.get("aperture")),
            shutter_speed=sanitize_str(camera.get("shutter_speed")),
            iso=sanitize_str(camera.get("iso")),
            mode=sanitize_str(camera.get("mode")),
            exposure_compensation=sanitize_str(camera.get("exposure_compensation")),
        )


def api_parameters_for_audit(api_params: dict[str, Any]) -> dict[str, Any]:
    """監査ログ用: 許可キーのみのコピー。"""
    image = api_params.get("image") or {}
    camera = api_params.get("camera") or {}
    return {
        "image": {k: image[k] for k in ALLOWED_IMAGE_KEYS if k in image},
        "camera": {k: camera[k] for k in ALLOWED_CAMERA_KEYS if k in camera},
    }


def _light_azimuth_fact_rule(light_hint: str) -> str:
    """東／西は太陽位置の事実。見た目のオレンジで夕方へ読み替えない。"""
    return f"""【光の方位は事実・覆さない】
光の方位（{light_hint}）は撮影時刻と太陽位置から確定した事実です。
ガラスのオレンジや青い空は、一日の前半でも後半でも同じに見える。見た目だけで西の空・一日の後半（または東の空・一日の前半）に読み替えてはいけない。
画面を優先してよいのは、光の強さ・色の濃さ・影の形だけである。方位（東の空／西の空、一日の前半／後半）は覆さない。
『朝日』『夕日』『夕焼け』『夕暮れ』『夕映え』『夕景』『夕刻』『夕方』『夜景』『黄昏』『夜の』『早朝』は TITLE・SUMMARY・本文・タグのいずれにも使わない。
東の空／一日の前半のときは西の空や一日の後半の光として書かない。西の空／一日の後半のときはその逆。
事前確定の観察に禁止の時間帯語があっても踏襲せず、光の方位の事実に従う。"""


def _environment_block(ctx: GuidedCritiqueContext, light_hint: str, *, phase: int) -> str:
    """Phase1 には撮影設定を載せない（構図・露出の助言は本文【4】の仕事）。"""
    lines = [
        "【撮影環境（抽象パラメータのみ）】",
        f"- 撮影日時: {ctx.shot_at}",
        f"- タイムゾーン: {ctx.timezone}",
        f"- 地域（都市レベル）: {ctx.region}",
        f"- 光の方位（事実）: {light_hint}",
        f"- 画像サイズ: {ctx.size}",
    ]
    if phase != 1:
        lines.append(
            "- 撮影設定: "
            f"絞り {ctx.aperture} | SS {ctx.shutter_speed} | ISO {ctx.iso} | "
            f"焦点距離 {ctx.focal_length} | 露出モード {ctx.mode} | "
            f"露出補正 {ctx.exposure_compensation}"
        )
    lines.append(f"- 撮影者の一言: {ctx.user_intent}")
    return "\n".join(lines)


def _resolve_lens(lens: str | CritiqueLens | None) -> CritiqueLens:
    if isinstance(lens, CritiqueLens):
        return lens
    return get_lens(normalize_lens(lens))


def build_guided_phase1_prompt(
    ctx: GuidedCritiqueContext,
    lens: str | CritiqueLens | None = None,
    *,
    variant: str | None = None,
) -> str:
    """Phase1: 抽象パラメータのみ（機種名・IPTC・Rating 等は含めない）。"""
    L = _resolve_lens(lens)
    vid = variant or DEFAULT_VARIANT
    hint = present_light_hint(ctx.light_hint, vid)
    extra = extra_phase1_rules(vid)
    extra_block = f"\n{extra}\n" if extra else ""
    return f"""与えられた写真を観察し、カード画像生成に必要な以下の4項目（TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY）のみを即座に作成してください。

{_environment_block(ctx, hint, phase=1)}

【講評作成の絶対ルール】
1. {L.score_definition_rule}
2. {_light_azimuth_fact_rule(hint)}
描写は光の角度・質感・明暗・グラデーションだけにしてください。{extra_block}
3. 人物の扱い（分岐・厳守）:
   - **判定**: まず画面に「人の姿」（顔・体・手・シルエット）があるかを確認する。看板のキャラクター絵は人物に数えない。
   - **人の姿がある**: 光や空間の話だけで終えるな。■CRITIQUE_SUMMARY の一文目は、写っているその人の「視線」「しぐさ」「佇まい」（または「佇む姿」）のいずれかで始めよ。
   - **人の姿がない**: 「しぐさ」「佇まい」「人物」を**一切使うな**。物の形と光だけで書け。
4. 【1】〜【7】などの本文文章は一切出力しないでください。

{_scores_meaning_block(L)}

【出力フォーマット】
以下の4項目のみを出力してください。

{phase1_output_slots(L)}
"""


def build_guided_phase2_prompt(
    ctx: GuidedCritiqueContext,
    phase1_output: str,
    lens: str | CritiqueLens | None = None,
    *,
    variant: str | None = None,
) -> str:
    """Phase2: 抽象パラメータのみ（IPTC・機種タグ・Preset 等は含めない）。"""
    L = _resolve_lens(lens)
    vid = variant or DEFAULT_VARIANT
    hint = present_light_hint(ctx.light_hint, vid)
    return f"""与えられた写真、撮影環境（抽象パラメータ）、および既に確定した以下の観察スナップショット・要約を読み、撮影者の美意識に寄り添う対話本文（【1】〜【7】）を作成してください。

【事前確定の観察結果・要約】
{phase1_output}

{_environment_block(ctx, hint, phase=2)}

【講評作成の絶対ルール】
1. 【撮影意図への回答】: 撮影者の一言（「{ctx.user_intent}」）に触れ、写真への結びつきを述べてください（一言が「なし」のときは画面観察を主にしてください）。
2. 【脱テンプレート化】: 安易な定型フレーズは使用厳禁です。各写真固有の観察から書いてください。
3. {_light_azimuth_fact_rule(hint)}
描写は光の角度・明暗・グラデーションで行ってください。
4. 【物語としての人物】: 人の姿がある場合のみしぐさ・視線・佇まいを用いる。ない場合は人物語を仮定しない。
5. 【構図の心理学】: 配置・余白・光のリズムを分析する。
6. 【曖昧さの肯定】: 技術的欠陥として切り捨てない。
7. 【問いかけで締める】: 再びシャッターを切りたくなる対話で締める。
8. 【確定観察との整合】: ■SCORES と整合した【1】〜【6】を各200文字程度、合計1200文字程度。
9. 【タグ付与】: 【7】の先頭に、被写体・光・質感・雰囲気に応じたハッシュタグを8〜12個（機種名・レンズ名・ファイル名・GPS・個人名は禁止）。

【出力フォーマット】
以下の見出しと【1】から【7】までの解説文のみを途切れなく記述してください。

---

## 【1. 情景・空気感とストーリー性】
(解説文)

## 【2. 視線誘導と構成の美学】
(解説文)

## 【3. 光の強弱・色彩と印象解析】
(解説文)

## 【4. 撮影設定と表現効果】
(解説文: 絞り・SS・ISO・焦点距離等の抽象パラメータがもたらした見え方を、数値の正誤ではなく感性として記述)

## 【5. {L.phase5_heading}】
(解説文)

## 【6. フォトブック＆SNSでの役割提案】
(解説文)

## 【7. 自動タグ】
#被写体名 #情景キーワード #光表現 #質感表現
"""


def record_api_audit(
    *,
    session_id: str | None,
    api_params: dict[str, Any],
    image_path: Path | None = None,
    user_note: str = "",
    phase: str = "critique",
) -> None:
    """送信監査ログ（API キー・生 GPS・フルパスは記録しない）。"""
    payload = api_parameters_for_audit(api_params)
    image_hash = None
    if image_path and image_path.is_file():
        digest = hashlib.sha256(image_path.read_bytes()).digest()
        image_hash = digest.hex()[:16]
    note = (user_note or "").strip()
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_id": session_id,
        "phase": phase,
        "model": os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        "api_parameters": payload,
        "user_note_sha256": hashlib.sha256(note.encode("utf-8")).hexdigest()[:16] if note else None,
        "image_sha256_prefix": image_hash,
    }
    try:
        _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _AUDIT_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def generate_guided_critique(
    image_path: Path,
    api_params: dict[str, Any],
    *,
    user_note: str = "",
    mode: str = "compact",
    lens: str = "self",
    phase1_override: str | None = None,
    session_id: str | None = None,
) -> str:
    """抽象パラメータのみで講評を生成する Guided 専用エントリポイント。"""
    from critique_engine import generate_critique_with_prompts

    ctx = GuidedCritiqueContext.from_api_params(api_params, user_note=user_note)
    lens_id = normalize_lens(lens)
    record_api_audit(
        session_id=session_id,
        api_params=api_params,
        image_path=image_path,
        user_note=user_note,
        phase="phase1" if mode == "compact" and not phase1_override else "full",
    )
    accept = east_west_phase_accept(ctx.light_hint)
    return generate_critique_with_prompts(
        image_path,
        mode=mode,
        lens=lens_id,
        phase1_override=phase1_override,
        system_role=get_system_role(lens_id),
        build_phase1=lambda: build_guided_phase1_prompt(ctx, lens=lens_id),
        build_phase2=lambda phase1_text: build_guided_phase2_prompt(ctx, phase1_text, lens=lens_id),
        phase_accept=accept,
        phase1_retry_note=EAST_WEST_REWRITE_NOTE_PHASE1 if accept is not None else None,
        phase2_retry_note=EAST_WEST_REWRITE_NOTE_PHASE2 if accept is not None else None,
    )


def assert_prompt_is_privacy_safe(prompt: str) -> None:
    """テスト用: 禁止マーカーがプロンプトに含まれないことを検証。"""
    lower = prompt.lower()
    for marker in FORBIDDEN_PROMPT_MARKERS:
        if marker.lower() in lower:
            raise AssertionError(f"forbidden marker in prompt: {marker}")
