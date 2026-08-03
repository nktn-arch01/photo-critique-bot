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


def run_pattern(client, img_base64, pattern_name, metadata_str, format_mode):
    prompt_compact = f"""あなたはプロの写真評論家です。
与えられた写真を観察し、カード画像生成に必要な以下の4項目（TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY）のみを即座に作成してください。

【撮影環境データ】
{metadata_str}

【講評作成の絶対ルール】
1. ■SCORESの5項目は提示された写真を個別に分析し、1〜5の数値（および対応する★記号）を独自に算出して出力してください。

【出力フォーマット】
■TITLE: 15文字以内のタイトル
■SUMMARY: 25文字以内のキャッチコピー
■SCORES:
・構図・構成  : [写真に応じた★評価] ([1〜5の数値]/5)
・光・色彩    : [写真に応じた★評価] ([1〜5の数値]/5)
・ストーリー  : [写真に応じた★評価] ([1〜5の数値]/5)
・技術・露出  : [写真に応じた★評価] ([1〜5の数値]/5)
・独自・世界観: [写真に応じた★評価] ([1〜5の数値]/5)
(※SCORES出力例: ・構図・構成  : ★★★☆☆ (3/5) のように必ず★記号5文字と(数値/5)形式で出力すること)
■CRITIQUE_SUMMARY: 好奇心を煽る文章を70〜80文字程度で記述してください。
"""

    prompt_full = f"""あなたは写真表現と撮影技術を深く探求するプロの写真評論家・フォトブック編集者です。
与えられた写真と以下の撮影環境・メタデータを観察し、撮影者の美意識に寄り添う情熱的で具体的な講評を作成してください。

【撮影環境データ】
{metadata_str}

【講評作成の絶対ルール】
1. 【撮影意図への回答】: 撮影者の意図・コメントがあれば触れ、なければ写真の視覚的魅力を中心に解説してください。
2. 【脱テンプレート化】: 安易な定型フレーズは使用厳禁です。
3. 【動的な独立評価】: ■SCORESの5項目（構図・構成、光・色彩、ストーリー、技術・露出、独自・世界観）は固定サンプル値を出力せず、提示された写真を個別に厳格分析し、1〜5の数値（および対応する★記号）を毎回独自に算出して出力してください。

【出力フォーマット】
■TITLE: 写真の核心を表現した15文字以内のタイトル
■SUMMARY: この写真の美を決定づける25文字以内のキャッチコピー
■SCORES:
・構図・構成  : [写真に応じた★評価] ([1〜5の数値]/5)
・光・色彩    : [写真に応じた★評価] ([1〜5の数値]/5)
・ストーリー  : [写真に応じた★評価] ([1〜5の数値]/5)
・技術・露出  : [写真に応じた★評価] ([1〜5の数値]/5)
・独自・世界観: [写真に応じた★評価] ([1〜5の数値]/5)
(※SCORES出力例: ・構図・構成  : ★★★☆☆ (3/5) のように必ず★記号5文字と(数値/5)形式で出力すること)
■CRITIQUE_SUMMARY: 読者の好奇心を煽るフックとなる文章を70〜80文字程度で記述してください。

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
#カメラ #レンズ #構図 #光 #雰囲気
"""

    prompt = prompt_compact if format_mode == "compact" else prompt_full
    max_tok = 500 if format_mode == "compact" else 4096

    print(f"\n⏳ 実行中: {pattern_name} ...", flush=True)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                ]
            }
        ],
        temperature=0.7,
        max_tokens=max_tok
    )
    content = response.choices[0].message.content or ""
    
    # スコア部分を抽出
    scores_m = re.search(r'((?:##\s*)?■?\s*SCORES\s*[:：][\s\S]*?)(?=(?:##\s*)?■?\s*CRITIQUE_SUMMARY|##\s*【|$)', content)
    scores_text = scores_m.group(1).strip() if scores_m else "❌ SCORES抽出失敗"
    
    return scores_text


def main():
    client = get_client()
    test_img = find_test_image()
    print(f"📸 テスト対象画像: {test_img}")
    img_b64 = encode_image(test_img)

    meta_full = """- 撮影日時: 2026-07-20 05:47:30 (早朝・黎明)
- カメラ/レンズ: OM-3 / OM 14-150mm F4.0-5.6 II
- 設定: f/5.5 | 1/1000s | ISO 200 | 70mm
- Preset: 標準/未指定
- Headline: ヘッドライン
- 撮影意図: 朝の金属の質感を表現したい
- カテゴリー: カテゴリー
- タグ: バイク, メカ"""

    meta_none = "- なし"

    meta_intent_only = "- 撮影意図: 朝の金属の質感を表現したい"

    results = {}
    results["パターン A (フルデータ + 簡易版)"] = run_pattern(client, img_b64, "パターン A (フルデータ + 簡易版)", meta_full, "compact")
    results["パターン B (メタデータ無 + 詳細版)"] = run_pattern(client, img_b64, "パターン B (メタデータ無 + 詳細版)", meta_none, "full")
    results["パターン C (フルデータ + 詳細版/現在)"] = run_pattern(client, img_b64, "パターン C (フルデータ + 詳細版/現在)", meta_full, "full")
    results["パターン D (意図のみ + 詳細版)"] = run_pattern(client, img_b64, "パターン D (意図のみ + 詳細版)", meta_intent_only, "full")

    print("\n" + "="*60)
    print("📊 A/B テスト検証結果一覧")
    print("="*60)
    for name, score_res in results.items():
        print(f"\n【{name}】")
        print(score_res)
    print("\n" + "="*60)


if __name__ == "__main__":
    main()
