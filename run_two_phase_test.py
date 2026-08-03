import os
import sys
import re
import base64
from pathlib import Path
from openai import OpenAI


def get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        key_file = Path.home() / ".openai_api_key"
        if key_file.exists():
            api_key = key_file.read_text(encoding="utf-8").strip()
    return OpenAI(api_key=api_key)


def find_test_image() -> Path:
    candidates = list(Path(".").glob("**/*_DxO.jpg")) + list(Path(".").glob("**/*.jpg"))
    if not candidates:
        print("❌ テスト用画像が見つかりません。")
        sys.exit(1)
    return candidates[0]


def encode_image(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def main():
    client = get_client()
    test_img = find_test_image()
    print(f"📸 選択肢2(2段階生成) 検証対象画像: {test_img}")
    img_b64 = encode_image(test_img)

    # 20260801最新版メタデータ環境設定
    date_time = "2026-07-20 05:47:30"
    time_zone_fact = "早朝・黎明（日の出前後）"
    camera_model = "OM-3"
    lens_model = "OM 14-150mm F4.0-5.6 II"
    f_number = "f/5.5"
    shutter_speed = "1/1000s"
    iso = "ISO 200"
    focal_length = "70mm"
    rating_str = "なし"
    preset_name = "標準/未指定"

    content_headline = "ヘッドライン"
    user_intent = "金属の質感を美しく表現したい"
    category = "カテゴリー"
    other_categories = "なし"
    keywords = "バイク, メカ"

    # ==========================================
    # Phase 1: 4項目(TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY) 生成
    # (20260801最新版プロンプトの文章を100%完全維持)
    # ==========================================
    prompt_phase1 = f"""あなたはプロの写真評論家です。
与えられた写真を観察し、カード画像生成に必要な以下の4項目（TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY）のみを即座に作成してください。

【撮影環境ファクトデータ】
- 撮影日時: {date_time} (時間帯分類: {time_zone_fact})
- カメラ: {camera_model} / レンズ: {lens_model}
- 撮影設定: {f_number} | {shutter_speed} | {iso} | 焦点距離: {focal_length}

【講評作成の絶対ルール】
1. ■SCORESの5項目は提示された写真を個別に分析し、1〜5の数値（および対応する★記号）を独自に算出して出力してください。
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

    print("\n⏳ [Phase 1 実行中] SCORES・カード項目を生成中...")
    res1 = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_phase1},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]
            }
        ],
        temperature=0.7,
        max_tokens=500
    )
    phase1_output = res1.choices[0].message.content or ""

    # ==========================================
    # Phase 2: 本文【1】〜【7】生成
    # (Phase 1の確定SCORESを渡し、20260801最新版講評ルールで生成)
    # ==========================================
    prompt_phase2 = f"""あなたは写真表現と撮影技術を深く探求するプロの写真評論家・フォトブック編集者です。
与えられた写真、撮影環境・メタデータ、および既に確定した以下の基本評価・要約を観察し、撮影者の美意識に寄り添う情熱的で具体的な講評本文（【1】〜【7】）を作成してください。

【事前確定評価・要約データ】
{phase1_output}

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
5. 【確定評価の維持】: 提示された事前確定の■SCORESの内容と整合性を保ちながら【1】〜【7】の文章を記述してください。

【出力フォーマット】
以下の見出しと【1】から【7】までの解説文のみを途切れなく記述してください。

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

    print("⏳ [Phase 2 実行中] 長文講評本文【1】〜【7】を生成中...")
    res2 = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_phase2},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]
            }
        ],
        temperature=0.7,
        max_tokens=4096
    )
    phase2_output = res2.choices[0].message.content or ""

    full_combined_result = f"{phase1_output.strip()}\n\n---\n\n{phase2_output.strip()}"

    print("\n" + "="*60)
    print("📊 選択肢2 (2段階生成) 最終生成結果")
    print("="*60)
    print(full_combined_result)
    print("="*60)


if __name__ == "__main__":
    main()
