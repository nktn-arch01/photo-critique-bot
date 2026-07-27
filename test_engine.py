import os
from pathlib import Path
from critique_engine import CritiqueEngine, CritiqueInput
from metadata_extractor import extract_jpeg_metadata

api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    print("[-] OPENAI_API_KEY 環境変数が未設定です。")
    exit(1)

test_file = Path("test_input.jpg")
if not test_file.exists():
    print("[-] test_input.jpg が見つかりません。")
    exit(1)

print("=== Phase 1: CritiqueEngine 単体テスト開始 ===")

# メタデータ抽出
meta = extract_jpeg_metadata(test_file)

# 生画像バイトの読み込み
image_bytes = test_file.read_bytes()

# 入力オブジェクト構築
inp = CritiqueInput(
    image_bytes=image_bytes,
    file_name=meta["file_name"],
    date_time=str(meta["date_time"]),
    time_zone_fact=meta["time_zone_fact"],
    camera_model=meta["camera_model"],
    lens_model=meta["lens_model"],
    f_number=meta["f_number"],
    shutter_speed=meta["shutter_speed"],
    iso=meta["iso"],
    focal_length=meta["focal_length"],
    user_intent=meta["user_intent"]
)

# エンジン実行
engine = CritiqueEngine(api_key=api_key)
res = engine.generate(inp)

print("\n[+] AI応答・パース完了 (Schema Version:", res.schema_version, ")")
print("----------------------------------------")
print("■ TITLE   :", res.title)
print("■ SUMMARY :", res.summary)
print("■ SCORES  :", res.scores)
print("----------------------------------------")
print("【生成されたMarkdown本文の一部】")
print(res.body_markdown[:200] + "...\n")
