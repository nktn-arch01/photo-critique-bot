import os
import time
import base64
import re
from pathlib import Path
from openai import OpenAI


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        key_file = Path.home() / ".openai_api_key"
        if key_file.exists():
            api_key = key_file.read_text(encoding="utf-8").strip()
    if not api_key:
        raise ValueError("OpenAI APIキーが見つかりません。~/.openai_api_key または環境変数 OPENAI_API_KEY を設定してください。")
    return OpenAI(api_key=api_key)


def encode_image(image_path: Path) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def sanitize_str(val: str) -> str:
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

    if mode == "full":
        prompt = f"""あなたは写真表現と撮影技術を深く探求するプロの写真評論家・フォトブック編集者です。
与えられた写真と以下の撮影環境・メタデータを観察し、撮影者の美意識に寄り添う情熱的で具体的な講評を作成してください。

【撮影環境ファクトデータ】
- 撮影日時: {date_time} (時間帯分類: {time_zone_fact})
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
3. 【光と陰影の整合】: 時間帯ファクト（{time_zone_fact}）と、実際の画面に現れている直射光・反射・シャドウの濃さを正しく対応させて描写してください。
4. 【具体的なアクション指導】: アドバイスでは具体的な動作や数値で示してください。
5. 【動的な独立評価】: ■SCORESの5項目（構図・構成、光・色彩、ストーリー、技術・露出、独自・世界観）は固定サンプル値を出力せず、提示された写真を個別に厳格分析し、1〜5の数値（および対応する★記号）を毎回独自に算出して出力してください。なお、3/5を「標準・良好」、4/5を「優秀」、5/5は「極めて稀な最高評価」、2/5以下は「明確な改善点あり」とし、極端な最高点や最低点に偏らせず、3/5を中心に写真ごとの差を表現してください。

【出力フォーマット】
以下のフォーマットと見出しを厳格に維持し、各見出しの後に必ず【1】から【7】までのすべての解説文を途切れなく記述してください。

■TITLE: 写真の核心を表現した15文字以内のタイトル
■SUMMARY: この写真の美を決定づける25文字以内のキャッチコピー
■SCORES:
・構図・構成  : [写真に応じた★評価] ([1〜5の数値]/5)
・光・色彩    : [写真に応じた★評価] ([1〜5の数値]/5)
・ストーリー  : [写真に応じた★評価] ([1〜5の数値]/5)
・技術・露出  : [写真に応じた★評価] ([1〜5の数値]/5)
・独自・世界観: [写真に応じた★評価] ([1〜5の数値]/5)
(※SCORES出力例: ・構図・構成  : ★★★☆☆ (3/5) のように必ず★記号5文字と(数値/5)形式で出力すること)
■CRITIQUE_SUMMARY: 否定的なコメント、数値、専門的な技術的表現、および「意図せず」「意識していない」「意図しない」といった言葉・フレーズは一切使用厳禁です。画面の中に自然と立ち現れている美しさや、新たな気づきを与える効果的な見所を主体に、読者が思わず本文を詳しく読みたくなるような好奇心を煽るフックとなる文章を70〜80文字程度で詳細に記述してください。

---

## 【1. 情景・空気感とストーリー性】
(写真全体の情景、空気感、および背景にあるストーリー性を情熱的かつ具体的に解説する文章)

## 【2. 視線誘導と構成の美学】
(画面内のフレーミング、被写体の配置、視線の流れについて具体的に解説する文章)

## 【3. 光の強弱・色彩と印象解析】
(光の当たり方、陰影のグラデーション、色彩がもたらす心理的効果について解説する文章)

## 【4. EXIFデータの技術的役割と表現効果】
(絞りやシャッタースピードなどのカメラ設定が画面表現にどのように寄与しているかの解説文章)

## 【5. 撮影者のためのステップアップ・アドバイス】
(次に撮影する際の実践的なアクションや具体的な工夫の提案文章)

## 【6. フォトブック＆SNSでの役割提案】
(作品の魅力が最も活きる発表の場や構成の提案文章)

## 【7. 自動タグ】
#カメラ_{camera_model} #レンズ_{lens_model} #構図_こだわり #光_演出 #雰囲気_表現
"""
    else:
        prompt = f"""あなたはプロの写真評論家です。
与えられた写真を観察し、カード画像生成に必要な以下の4項目（TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY）のみを即座に作成してください。

【講評作成の絶対ルール】
1. ■SCORESの5項目は提示された写真を個別に分析し、1〜5の数値（および対応する★記号）を独自に算出して出力してください。3/5を「標準・良好」、4/5を「優秀」、5/5は「極めて稀な最高評価」とし、3/5を中心に写真に応じた差をつけてください。
2. 【1】〜【7】などの本文文章は一切出力しないでください。

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

    max_tok = 4096 if mode == "full" else 500

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.7,
                max_tokens=max_tok
            )
            content = response.choices[0].message.content or ""
            
            has_title = bool(re.search(r'■\s*TITLE\s*[:：]', content))
            has_scores = bool(re.search(r'■\s*SCORES\s*[:：]', content))
            has_crit_sum = bool(re.search(r'■\s*CRITIQUE_SUMMARY\s*[:：]', content))

            if not (has_title and has_scores and has_crit_sum) or "申し訳ありません" in content:
                print(f"⚠️ 構造ヘッダー未検出または拒否応答。自動再試行 ({attempt}/{max_retries})...")
                if attempt < max_retries:
                    time.sleep(backoff_factor ** attempt)
                    continue
                else:
                    raise ValueError("OpenAI API出力に必須ヘッダーが含まれませんでした。")
                    
            return content

        except Exception as e:
            if attempt == max_retries:
                raise e
            time.sleep(backoff_factor ** attempt)
