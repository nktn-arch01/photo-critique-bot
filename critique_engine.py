import os
import time
import base64
from pathlib import Path
from openai import OpenAI

# 共通パーサーモジュールの読み込み
from critique_parser import parse_critique_text


def get_openai_client() -> OpenAI:
    """OpenAI APIクライアントの初期化を行います。"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        key_file = Path.home() / ".openai_api_key"
        if key_file.exists():
            api_key = key_file.read_text(encoding="utf-8").strip()
    if not api_key:
        raise ValueError("OpenAI APIキーが見つかりません。~/.openai_api_key または環境変数 OPENAI_API_KEY を設定してください。")
    return OpenAI(api_key=api_key)


def encode_image(image_path: Path) -> str:
    """画像ファイルをBase64文字列にエンコードします。"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def sanitize_str(val: str) -> str:
    """ヌル文字の除去と文字列の整形を行います。"""
    if not val:
        return "なし"
    clean = str(val).replace("\x00", "").strip()
    return clean if clean else "なし"


def generate_critique(
    image_path: Path, 
    metadata: dict = None, 
    dop_info: dict = None, 
    model: str = "gpt-4o-mini",
    mode: str = "compact",
    max_retries: int = 3,
    backoff_factor: float = 2.0
) -> str:
    """
    OpenAI Vision APIを呼び出し、写真のAI講評文を生成します。
    mode="compact": Phase 1 (カード用要素) のみ生成して高速返信
    mode="full": Phase 1 ➔ Phase 2 (長文本文) の2段階分離生成
    """
    client = get_openai_client()
    base64_image = encode_image(image_path)

    metadata = metadata or {}
    dop_info = dop_info or {}

    user_intent = sanitize_str(metadata.get("user_intent"))
    camera_model = sanitize_str(metadata.get("camera_model"))
    lens_model = sanitize_str(metadata.get("lens_model"))
    f_number = sanitize_str(metadata.get("f_number"))
    shutter_speed = sanitize_str(metadata.get("shutter_speed"))
    iso = sanitize_str(metadata.get("iso"))
    focal_length = sanitize_str(metadata.get("focal_length"))
    date_time = sanitize_str(metadata.get("date_time"))
    time_zone_fact = sanitize_str(metadata.get("time_zone_fact"))

    content_headline = sanitize_str(dop_info.get("content_headline"))
    category = sanitize_str(dop_info.get("category"))
    other_categories = sanitize_str(dop_info.get("other_categories"))
    keywords = sanitize_str(dop_info.get("keywords"))
    rating_str = sanitize_str(dop_info.get("rating_str"))
    preset_name = sanitize_str(dop_info.get("preset_name"))

    # 時間帯ファクトの表示補正（類語も含めた禁止ルールの強化）
    if time_zone_fact in ["不明", "なし", ""]:
        time_zone_display = (
            "不明 (※EXIF非保持。『夕日』『夕暮れ』『夕焼け』『夕映え』『夕景』『黄昏』などの夕方を示す言葉は一切使用厳禁。"
            "『柔らかな光』『水面を彩る光』『美しいシルエット』などの言葉で光とコントラストを表現すること)"
        )
    else:
        time_zone_display = time_zone_fact

    # ハッシュタグ破綻防止: スペースをアンダースコアに自動置換
    camera_tag = camera_model.replace(" ", "_")
    lens_tag = lens_model.replace(" ", "_")

    # =========================================================
    # Phase 1: カード用4項目 (TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY) 生成
    # =========================================================
    prompt_phase1 = f"""あなたはプロの写真評論家です。
与えられた写真と以下の撮影ファクトを観察し、カード画像生成に必要な以下の4項目（TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY）のみを即座に作成してください。

【撮影環境ファクトデータ】
- 撮影日時: {date_time} (時間帯分類: {time_zone_display})
- カメラ: {camera_model} / レンズ: {lens_model}

【講評作成の絶対ルール】
1. ■SCORESの5項目は提示された写真を個別に分析し、1〜5の数値（および対応する★記号）を独自に算出して出力してください。
2. 時間帯ファクト（{time_zone_display}）を遵守してください。時間帯が『不明』の場合、タイトル・要約・本文全体で『夕日』『夕焼け』『夕暮れ』『夕映え』『夕景』『黄昏』などの言葉を使用することは【一切厳禁】です。光の質やコントラスト、美しいグラデーションとして描写してください。
3. 【1】〜【7】などの本文文章は一切出力しないでください。

【出力フォーマット】
以下の4項目のみを出力してください。

■TITLE: 写真の核心を表現した15文字以内のタイトル
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

    phase1_output = ""
    for attempt in range(1, max_retries + 1):
        try:
            res1 = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_phase1},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }
                ],
                temperature=0.7,
                max_tokens=500
            )
            content = res1.choices[0].message.content or ""
            
            parsed_check = parse_critique_text(content)
            if parsed_check["has_valid_phase1"] and "申し訳ありません" not in content:
                phase1_output = content.strip()
                break
            
            if attempt < max_retries:
                time.sleep(backoff_factor ** attempt)
            else:
                raise ValueError("Phase 1 API出力に必須構造が含まれませんでした。")
        except Exception as e:
            if attempt == max_retries:
                raise e
            time.sleep(backoff_factor ** attempt)

    # 簡易版 (compact) の場合は Phase 1 の結果のみを即座に返す
    if mode != "full":
        return phase1_output

    # =========================================================
    # Phase 2: 本文【1】〜【7】生成
    # =========================================================
    prompt_phase2 = f"""あなたは写真表現と撮影技術を深く探求するプロの写真評論家・フォトブック編集者です。
与えられた写真、撮影環境・メタデータ、および既に確定した以下の基本評価・要約を観察し、撮影者の美意識に寄り添う情熱的で具体的な講評本文（【1】〜【7】）を作成してください。

【事前確定評価・要約データ】
{phase1_output}

【撮影環境ファクトデータ】
- 撮影日時: {date_time} (時間帯分類: {time_zone_display})
- カメラ: {camera_model} / レンズ: {lens_model}
- 撮影設定: {f_number} | {shutter_speed} | {iso} | 焦点距離: {focal_length}
- DxO評価/Preset: {rating_str} | Preset: {preset_name}

【撮影者が付与したメタデータ (IPTC)】
- 作品タイトル/見出し (Headline): {content_headline}
- 撮影意図・悩み・コメント (User Intent): {user_intent}
- カテゴリー: {category} (補足: {other_categories})
- キーワード/タグ: {keywords}

【講評作成の絶対ルール】
1. 【撮影意図への回答】: 撮影者の意図・悩み（「{user_intent}」）に直接触れ、それがどう写真に結実しているか、またはどうすればより意図が際立つか回答してください。
2. 【脱テンプレート化】: 『三分割法』『柔らかい光』『季節感あふれる』といった安易で一般的な定型フレーズは使用厳禁です。
3. 【光と陰影の整合】: 時間帯ファクト（{time_zone_display}）を遵守してください。時間帯が『不明』の場合、『夕日』『夕焼け』『夕暮れ』『夕映え』『夕景』『黄昏』などの言葉は一切使わず、光の表情や水面の反射を客観的に表現してください。
4. 【具体的なアクション指導】: アドバイスでは具体的な動作や数値で示してください。
5. 【確定評価の維持】: 提示された事前確定の■SCORESの内容と整合性を保ちながら【1】〜【7】の文章を記述してください。
6. 【自動タグの厳格付与】: 【7】の先頭には必ず `#カメラ_{camera_tag} #レンズ_{lens_tag}` をそのまま出力し、続けて写真の被写体・光・質感に応じたハッシュタグを8〜12個出力してください（※時間帯不明時は『夕景』等のタグも付与禁止）。

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
#カメラ_{camera_tag} #レンズ_{lens_tag} #被写体名 #情景キーワード #光表現 #質感表現
"""

    phase2_output = ""
    for attempt in range(1, max_retries + 1):
        try:
            res2 = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_phase2},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }
                ],
                temperature=0.7,
                max_tokens=4096
            )
            content = res2.choices[0].message.content or ""
            if "【1." in content or "【1" in content:
                phase2_output = content.strip()
                break
            
            if attempt < max_retries:
                time.sleep(backoff_factor ** attempt)
            else:
                raise ValueError("Phase 2 API出力に本文構造が含まれませんでした。")
        except Exception as e:
            if attempt == max_retries:
                raise e
            time.sleep(backoff_factor ** attempt)

    return f"{phase1_output}\n\n---\n\n{phase2_output}"