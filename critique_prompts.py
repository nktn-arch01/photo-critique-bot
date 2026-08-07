"""講評生成用プロンプトの単一ソース（OpenAI / Gemini 共通）。"""

from dataclasses import dataclass


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


def build_phase1_prompt(ctx: CritiquePromptContext) -> str:
    return f"""あなたはプロの写真評論家です。
与えられた写真を観察し、カード画像生成に必要な以下の4項目（TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY）のみを即座に作成してください。

【撮影環境ファクトデータ】
- カメラ: {ctx.camera_model} / レンズ: {ctx.lens_model}

【講評作成の絶対ルール】
1. ■SCORESの5項目は提示された写真を個別に分析し、1〜5の数値（および対応する★記号）を独自に算出して出力してください。
2. 『朝日』『夕日』『夕焼け』『夕暮れ』『夕映え』『夕景』『夜景』『黄昏』などの直接的な時間帯を示す単語・ラベルの使用は【一切厳禁】です。安易な時間帯ラベルに頼らず、画面に現れている光の角度、質感、明暗のコントラスト、グラデーションの美しさを表現してください。
3. 【1】〜【7】などの本文文章は一切出力しないでください。

【出力フォーマット】
以下の4項目のみを出力してください。

■TITLE: 写真の核心を表現した15文字以内のタイトル (時間帯単語は使用不可)
■SUMMARY: この写真の美を決定づける25文字以内のキャッチコピー
■SCORES:
・構図・構成  : [写真に応じた★評価] ([1〜5の数値]/5)
・光・色彩    : [写真に応じた★評価] ([1〜5の数値]/5)
・ストーリー  : [写真に応じた★評価] ([1〜5の数値]/5)
・技術・露出  : [写真に応じた★評価] ([1〜5の数値]/5)
・独自・世界観: [写真に応じた★評価] ([1〜5の数値]/5)
(※SCORES出力例: ・構図・構成  : ★★★☆☆ (3/5) のように必ず★記号5文字と(数値/5)形式で出力すること)
■CRITIQUE_SUMMARY: 否定的なコメント、数値、専門的な技術的表現、および「意図せず」「意識していない」「意図しない」といった言葉・フレーズは一切使用厳禁です。画面の中に自然と立ち現れている美しさや、新たな気づきを与える効果的な見所を主体に、読者の好奇心を煽る文章を70〜80文字程度で記述してください。
"""


def build_phase2_prompt(ctx: CritiquePromptContext, phase1_output: str) -> str:
    return f"""あなたは写真表現と撮影技術を深く探求するプロの写真評論家・フォトブック編集者です。
与えられた写真、撮影環境・メタデータ、および既に確定した以下の基本評価・要約を観察し、撮影者の美意識に寄り添う情熱的で具体的な講評本文（【1】〜【7】）を作成してください。

【事前確定評価・要約データ】
{phase1_output}

【撮影環境ファクトデータ】
- 撮影日時: {ctx.date_time} (時間帯分類: {ctx.time_zone_fact})
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
2. 【脱テンプレート化】: 『三分割法』『柔らかい光』『季節感あふれる』といった安易で一般的な定型フレーズは使用厳禁です。
3. 【光と陰影の具象的描写】: 撮影時間帯ファクト（{ctx.time_zone_fact}）を前提知識として考慮しつつも、『朝日』『夕日』『夕焼け』『夕暮れ』『夕映え』『夕景』『夜景』『黄昏』などの単語を安易に連呼することは避けてください。単語のラベル貼りではなく、「光の差し込む角度」「明暗のコントラスト」「グラデーションの推移」「シャドウの深度」など具体的な光と色彩の表現として文章を構築してください。
4. 【具体的なアクション指導】: アドバイスでは具体的な動作や数値で示してください。
5. 【確定評価の維持】: 提示された事前確定の■SCORESの内容と整合性を保ちながら【1】〜【7】の文章を記述してください。
6. 【自動タグの厳格付与】: 【7】の先頭には必ず `#カメラ_{ctx.camera_tag} #レンズ_{ctx.lens_tag}` をそのまま出力し、続けて写真の被写体・光・質感に応じたハッシュタグを8〜12個出力してください（※安易な時間帯ラベルタグの乱用は控えること）。

【出力フォーマット】
以下の見出しと【1】から【7】までの解説文のみを途切れなく記述してください。

---

## 【1. 情景・空気感とストーリー性】
(解説文章)

## 【2. 視線誘導と構成の美学】
(解説文章)

## 【3. 光の強弱・色彩と印象解析】
(解説文章)

## 【4. EXIFデータの技術的役割と表現効果】
(解説文章)

## 【5. 撮影者のためのステップアップ・アドバイス】
(解説文章)

## 【6. フォトブック＆SNSでの役割提案】
(解説文章)

## 【7. 自動タグ】
#カメラ_{ctx.camera_tag} #レンズ_{ctx.lens_tag} #被写体名 #情景キーワード #光表現 #質感表現
"""
