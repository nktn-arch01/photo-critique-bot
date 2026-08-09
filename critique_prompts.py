"""講評生成用プロンプトの単一ソース（OpenAI / Gemini 共通）。

共通レイヤ: 出力フォーマットキー、メタデータ注入、時間帯ラベル禁止など。
レンズ固有: SYSTEM_ROLE、スコア軸の意味、タイトル／短評／人物／EXIF／アドバイスのスタンス。
"""

from __future__ import annotations

from dataclasses import dataclass

from critique_lens import DEFAULT_LENS, CritiqueLens, get_lens, normalize_lens


def sanitize_str(val: str) -> str:
    if not val:
        return "なし"
    clean = str(val).replace("\x00", "").strip()
    return clean if clean else "なし"


@dataclass(frozen=True)
class CritiquePromptContext:
    user_intent: str
    camera_model: str
    lens_model: str
    f_number: str
    shutter_speed: str
    iso: str
    focal_length: str
    date_time: str
    time_zone_fact: str
    content_headline: str
    category: str
    other_categories: str
    keywords: str
    rating_str: str
    preset_name: str

    @classmethod
    def from_metadata(cls, metadata: dict | None, dop_info: dict | None) -> "CritiquePromptContext":
        metadata = metadata or {}
        dop_info = dop_info or {}
        return cls(
            user_intent=sanitize_str(metadata.get("user_intent")),
            camera_model=sanitize_str(metadata.get("camera_model")),
            lens_model=sanitize_str(metadata.get("lens_model")),
            f_number=sanitize_str(metadata.get("f_number")),
            shutter_speed=sanitize_str(metadata.get("shutter_speed")),
            iso=sanitize_str(metadata.get("iso")),
            focal_length=sanitize_str(metadata.get("focal_length")),
            date_time=sanitize_str(metadata.get("date_time")),
            time_zone_fact=sanitize_str(metadata.get("time_zone_fact")),
            content_headline=sanitize_str(dop_info.get("content_headline")),
            category=sanitize_str(dop_info.get("category")),
            other_categories=sanitize_str(dop_info.get("other_categories")),
            keywords=sanitize_str(dop_info.get("keywords")),
            rating_str=sanitize_str(dop_info.get("rating_str")),
            preset_name=sanitize_str(dop_info.get("preset_name")),
        )

    @property
    def camera_tag(self) -> str:
        return self.camera_model.replace(" ", "_")

    @property
    def lens_tag(self) -> str:
        return self.lens_model.replace(" ", "_")


def _resolve_lens(lens: str | CritiqueLens | None) -> CritiqueLens:
    if isinstance(lens, CritiqueLens):
        return lens
    return get_lens(normalize_lens(lens))


def _scores_format_block(lens: CritiqueLens) -> str:
    lines = ["■SCORES:"]
    for axis in lens.score_axes:
        lines.append(f"・{axis.label}  : [写真に応じた★評価] ([1〜5の数値]/5)")
    example_label = lens.score_axes[0].label if lens.score_axes else "空間の切り取り"
    lines.append(
        f"(※SCORES出力例: ・{example_label}  : ★★★☆☆ (3/5) のように必ず★記号5文字と(数値/5)形式で出力すること)"
    )
    return "\n".join(lines)


def _scores_meaning_block(lens: CritiqueLens) -> str:
    lines = ["【■SCORES：感性のアンテナの深層基準】"]
    for axis in lens.score_axes:
        lines.append(f"・{axis.label}: {axis.meaning}")
    return "\n".join(lines)


def build_phase1_prompt(ctx: CritiquePromptContext, lens: str | CritiqueLens | None = None) -> str:
    """Phase 1: カード用4項目（TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY）。"""
    L = _resolve_lens(lens)
    return f"""与えられた写真を観察し、カード画像生成に必要な以下の4項目（TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY）のみを即座に作成してください。

【撮影環境ファクトデータ】
- カメラ: {ctx.camera_model} / レンズ: {ctx.lens_model}

【講評作成の絶対ルール】
1. {L.score_definition_rule}
2. 時間帯ラベルの厳禁: 『朝日』『夕日』『夕焼け』『夕暮れ』『夕映え』『夕景』『夜景』『黄昏』『夜の』『早朝』などの直接的な時間帯を示す単語・ラベルの使用は【一切厳禁】です。画面が暗く見えても時計の時間帯を推測して書かないでください。光の角度・質感・明暗・グラデーションだけを描写してください。
3. 人物の「しぐさ」の読解（必須・最優先）: 画面内に人物（顔・全身・シルエット・手など人の姿）が写っている場合、光や空間の描写より先にその人物を扱うこと。■CRITIQUE_SUMMARY の**一文目**で「視線」「しぐさ」「佇まい」のいずれかを使って具体的に触れよ（「人の存在」「思索」だけでは不可）。人物が一人も写っていない場合のみ、この条項は適用しない。
4. 【1】〜【7】などの本文文章は一切出力しないでください。

{_scores_meaning_block(L)}

【出力フォーマット】
以下の4項目のみを出力してください。

■TITLE: 15文字以内。撮影者の眼差しの正体を言い当てる詩的・仮説的なタイトル（時間帯単語は使用不可）。被写体名（「花」「空」「海」等）を使ったラベル貼りを禁止。
■SUMMARY: 写真の美を決定づける25文字以内のキャッチコピー。
{_scores_format_block(L)}
■CRITIQUE_SUMMARY: 否定的なコメント、数値、専門的な技術的表現、および「意図せず」「意識していない」「意図しない」といった言葉・フレーズは一切使用厳禁です。画面の中に自然と立ち現れている美しさや、撮影者の「無意識の意図」への仮説（「あなたは〇〇に惹かれたのでは」）、新たな気づきを与える対話のきっかけを、70〜80文字程度で記述してください。
"""


def build_phase2_prompt(
    ctx: CritiquePromptContext,
    phase1_output: str,
    lens: str | CritiqueLens | None = None,
) -> str:
    """Phase 2: 長文講評本文（【1】〜【7】）。"""
    L = _resolve_lens(lens)
    return f"""与えられた写真、撮影環境・メタデータ、および既に確定した以下の基本評価・要約を観察し、撮影者の美意識に寄り添う情熱的で具体的な講評本文（【1】〜【7】）を作成してください。

【事前確定評価・要約データ】
{phase1_output}

【撮影環境ファクトデータ】
- 撮影日時（EXIF DateTimeOriginal＝シャッターを切った時刻。現像・書出の ModifyDate ではない）: {ctx.date_time}
- 時計帯ヒント（視覚ラベルではない）: {ctx.time_zone_fact}
- カメラ: {ctx.camera_model} / レンズ: {ctx.lens_model}
- 撮影設定: {ctx.f_number} | {ctx.shutter_speed} | {ctx.iso} | 焦点距離: {ctx.focal_length}
- DxO評価/Preset: {ctx.rating_str} | Preset: {ctx.preset_name}

【撮影者が付与したメタデータ (IPTC)】
- 作品タイトル/見出し (Headline): {ctx.content_headline}
- 撮影意図・悩み・コメント (User Intent): {ctx.user_intent}
- カテゴリー: {ctx.category} (補足: {ctx.other_categories})
- キーワード/タグ: {ctx.keywords}

【講評作成の絶対ルール】
1. 【撮影意図への回答】: 撮影者の意図・悩み（「{ctx.user_intent}」）に直接触れ、それがどう写真に結実しているか、またはどうすればより意図が際立つか回答してください。
2. 【脱テンプレート化】: 『三分割法』『柔らかい光』『季節感あふれる』『光と影の物語』『静けさを映す』といった安易で一般的な定型フレーズは使用厳禁です。各写真固有の観察から文章を始めてください。
3. 【光と陰影の具象的描写】: 時計帯ヒント（{ctx.time_zone_fact}）は「いつ撮ったか」の背景知識です。画面が暗く見えても、ヒントと矛盾する『夜』『夕景』などのラベルで上書きしないでください。『朝日』『夕日』『夕焼け』『夕暮れ』『夕映え』『夕景』『夜景』『黄昏』『早朝』の単語は使用厳禁。描写は「光の差し込む角度」「明暗のコントラスト」「グラデーションの推移」「シャドウの深度」など具体的な光と色彩のみで行ってください。
4. 【物語としての人物】: 人物が写っている場合は必ず「しぐさ」「視線」「佇まい」から前後の時間の流れを推論して言語化してください。偶然の写り込みであっても、その人が入り込むことで風景の価値がどう更新されたかという新たな意味を提案してください。人物がいない場合のみ省略可。
5. 【構図の心理学】: 人物の配置（端、背後、距離感）が観る者に与える「心理的な余白」や「被写体との距離感（親密さや敬意）」を分析してください。
6. 【曖昧さの肯定】: 露出の過不足やブレが「当時の心の揺れ」を表現しているなら、それを技術的ミスとせず、ブランド原則「曖昧さに意味があるなら、それを残す」に基づき肯定してください。「修正」「改善」「失敗」など欠陥を示唆する言葉は使用厳禁です。
7. 【写真に戻るための問いかけ】: 完結した答えや数値指導で締めず、「次、同じ光に出会ったら、あえて〇〇を試して余韻を狙ってみませんか？」といった、再びカメラを構えたくなる対話で締めてください。
8. 【確定評価の維持】: 提示された事前確定の■SCORESの内容と整合性を保ちながら【1】〜【6】の文章を各200文字程度、合計1200文字程度で記述してください。
9. 【自動タグの厳格付与】: 【7】の先頭には必ず `#カメラ_{ctx.camera_tag} #レンズ_{ctx.lens_tag}` をそのまま出力し、続けて写真の被写体・光・質感に応じたハッシュタグを8〜12個出力してください（※安易な時間帯ラベルタグの乱用は控えること）。

【出力フォーマット】
以下の見出しと【1】から【7】までの解説文のみを途切れなく記述してください。

---

## 【1. 情景・空気感とストーリー性】
(解説文: 人物のしぐさや光の移ろいから読み取れる、この瞬間だけの「気配」を言語化)

## 【2. 視線誘導と構成の美学】
(解説文: 構図や人物の立ち位置がもたらす視覚的リズムと、そこから生まれる「心の距離感」を分析)

## 【3. 光の強弱・色彩と印象解析】
(解説文: 「光の照射角度」や「シャドウの深度」など、具象的な言葉で感性の正体を解き明かす)

## 【4. EXIFデータの技術的役割と表現効果】
(解説文: 数値の正誤ではなく、その設定が「あなたの心の揺れ」をどう定着させたかを記述)

## 【5. {L.phase5_heading}】
(解説文: 定型句を排し、感性をさらに深めるための具体的な「問いかけ」と「次の一歩」を提示)

## 【6. フォトブック＆SNSでの役割提案】
(解説文: 「写真集の静かなアクセント（間）になる」等の編集者視点で、この写真が線として繋がる可能性を提案)

## 【7. 自動タグ】
#カメラ_{ctx.camera_tag} #レンズ_{ctx.lens_tag} #被写体名 #情景キーワード #光表現 #質感表現
"""


def get_system_role(lens: str | CritiqueLens | None = None) -> str:
    return _resolve_lens(lens).system_role
