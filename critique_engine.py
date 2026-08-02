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
    max_retries: int = 4,
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

【講評作成ガイドライン】
1. 撮影者の意図・悩み（「{user_intent}」）に直接触れ、それがどう写真に結実しているか、またはどうすればより意図が際立つか回答してください。
2. 『三分割法』『柔らかい光』『季節感あふれる』といった定型フレーズを避け、目の前の写真を具体的に描写してください。
3. 時間帯ファクト（{time_zone_fact}）と、実際の画面に現れている光・シャドウを整合させて解説してください。
4. ■SCORESの5項目（構図・構成、光・色彩、ストーリー、技術・露出、独自・世界観）は省略せず必ず全5行を出力してください。数値（1〜5）および対応する★記号（例: 4なら★★★★☆）は提示された写真を分析して毎回独自に算出して出力してください。
5. ■CRITIQUE_SUMMARY は、読者の好奇心を煽るフックとなる文章を「70〜80文字程度（必ず65文字以上・2文以上）」で詳細に記述してください。短すぎる1文のみの出力は不可とします。
6. ## 【7. 自動タグ】 では、写真に写っている被写体、場所、季節、空気感、テーマ等に応じたハッシュタグ（例: #被写体名 #季節 #雰囲気 など）を8〜12個程度生成してください。

【出力フォーマット】
以下の見出し形式と項目名を厳格に維持し、すべてのセクションを途切れなく記述してください。

■TITLE: 写真の核心を表現した15文字以内のタイトル
■SUMMARY: この写真の美を決定づける25文字以内のキャッチコピー
■SCORES:
・構図・構成  : ★★★★☆ (4/5)
・光・色彩    : ★★★★★ (5/5)
・ストーリー  : ★★★★☆ (4/5)
・技術・露出  : ★★★★☆ (4/5)
・独自・世界観: ★★★★☆ (4/5)
■CRITIQUE_SUMMARY: 否定的な表現を使わず、読者の好奇心を煽るフックとなる文章を70〜80文字程度で詳細に記述してください。

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
(写真に応じたハッシュタグ8〜12個)
"""
    else:
        prompt = f"""あなたはプロの写真評論家です。
写真とメタデータを観察し、カード画像生成に必要な4項目（TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY）のみを作成してください。

【撮影環境ファクトデータ】
- 撮影日時: {date_time} (時間帯分類: {time_zone_fact})
- カメラ: {camera_model} / レンズ: {lens_model}
- 撮影設定: {f_number} | {shutter_speed} | {iso} | 焦点距離: {focal_length}

【出力フォーマット】
■TITLE: 写真の核心を表現した15文字以内のタイトル
■SUMMARY: この写真の美を決定づける25文字以内のキャッチコピー
■SCORES:
・構図・構成  : ★★★★☆ (4/5)
・光・色彩    : ★★★★★ (5/5)
・ストーリー  : ★★★★☆ (4/5)
・技術・露出  : ★★★★☆ (4/5)
・独自・世界観: ★★★★☆ (4/5)
■CRITIQUE_SUMMARY: 好奇心を煽る文章を70〜80文字程度で記述してください。
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
            
            # 厳格な出力バリデーション（完全自動検知）
            required_items = [
                "■TITLE:", "■SUMMARY:", "■SCORES:",
                "・構図・構成", "・光・色彩", "・ストーリー", "・技術・露出", "・独自・世界观",
                "■CRITIQUE_SUMMARY:"
            ]
            # 日本語表記ゆれ対策
            if "・独自・世界観" in content:
                required_items.remove("・独自・世界观")

            missing = [item for item in required_items if item not in content]
            
            crit_sum_m = re.search(r'■CRITIQUE_SUMMARY:\s*(.+)', content)
            crit_sum_len = len(crit_sum_m.group(1).strip()) if crit_sum_m else 0

            if missing or crit_sum_len < 60 or "申し訳ありません" in content:
                print(f"⚠️ 出力検証不完全 (欠落項目: {missing}, 要約長: {crit_sum_len}字)。自動再試行 ({attempt}/{max_retries})...")
                if attempt < max_retries:
                    time.sleep(backoff_factor ** attempt)
                    continue
                else:
                    raise ValueError(f"OpenAI API出力が条件を満たしませんでした (欠落: {missing})")
                    
            return content

        except Exception as e:
            if attempt == max_retries:
                raise e
            time.sleep(backoff_factor ** attempt)
