import os
import re
import sys
import time
import shutil
import subprocess
import base64
import io
from datetime import datetime
from PIL import Image, ExifTags
from openai import OpenAI
from generate_critique_card import parse_gpt_output, create_critique_card

# ==========================================
# ⚙️ 設定エリア
# ==========================================
KEY_FILE_PATH = os.path.expanduser("~/.openai_api_key")
ALBUM_SRC = "01_AI解析用"
ALBUM_DEST = "02_解析完了"

MODEL_NAME = "gpt-4o-mini"

TEMP_DIR = "/tmp/AI_Photos"
SAVE_DIR_BASE = os.path.expanduser("~/写真分析ノート")
LOG_DIR_BASE = os.path.expanduser("~/Google ドライブ")

REFUSAL_KEYWORDS = [
    "お応えできません", "申し訳ありませんが", "リクエストに応じ",
    "I cannot fulfill", "I'm unable to", "safety system",
    "I'm sorry", "can't assist", "cannot assist", "as an ai"
]

OPENAI_API_KEY = None
if os.path.exists(KEY_FILE_PATH):
    with open(KEY_FILE_PATH, "r", encoding="utf-8") as kf:
        OPENAI_API_KEY = kf.read().strip()

if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("YOUR_"):
    print("❌ 【エラー】OpenAI APIキーが設定されていません。")
    print("👉 ターミナルで以下を実行してAPIキーを保存してください:")
    print('   echo "sk-..." > ~/.openai_api_key\n')
    sys.exit(1)

try:
    subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())])
    print("☕️ Macの自動スリープ防止機能を有効化しました。")
except Exception:
    pass

if os.path.exists(TEMP_DIR):
    shutil.rmtree(TEMP_DIR)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(SAVE_DIR_BASE, exist_ok=True)
os.makedirs(LOG_DIR_BASE, exist_ok=True)

client = OpenAI(api_key=OPENAI_API_KEY)

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', '_', name)

def check_duplicate_and_get_path(target_dir, filename):
    clean_name = sanitize_filename(filename)
    base_save_filename = f"{clean_name}.md"
    target_path = os.path.join(target_dir, base_save_filename)

    if os.path.exists(target_dir):
        for f in os.listdir(target_dir):
            if f == base_save_filename or (f.startswith(f"{clean_name}_v") and f.endswith(".md")):
                return None, None, "SKIP"

    return target_path, base_save_filename, "NEW"

def load_and_encode_image(image_path, max_size=2048):
    with Image.open(image_path) as img:
        img_rgb = img.convert('RGB')
        img_rgb.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        buffered = io.BytesIO()
        img_rgb.save(buffered, format="JPEG", quality=85)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

def extract_comprehensive_exif(image_path):
    exif_data = {}
    try:
        with Image.open(image_path) as img:
            raw_exif = img._getexif()
            if raw_exif:
                for tag_id, val in raw_exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                    exif_data[tag_name] = val
            try:
                ifd_exif = img.getexif().get_ifd(0x8769)
                for tag_id, val in ifd_exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                    if tag_name not in exif_data or not exif_data[tag_name]:
                        exif_data[tag_name] = val
            except Exception:
                pass
    except Exception as e:
        print(f"   ⚠️ EXIF抽出警告: {e}")
    return exif_data

def append_log_safely(log_path, entry_text):
    for _ in range(3):
        try:
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(entry_text)
            break
        except Exception:
            time.sleep(0.5)

EXPORT_WITH_CAPTION_SCRIPT = '''
on run argv
    set exportFolder to item 1 of argv
    set albumSrc to item 2 of argv
    
    tell application "Photos"
        set targetAlbum to null
        if exists container albumSrc then
            set targetAlbum to container albumSrc
        else if exists album albumSrc then
            set targetAlbum to album albumSrc
        end if
        
        if targetAlbum is not null then
            set photoList to media items of targetAlbum
            repeat with p in photoList
                set fName to filename of p
                set cap to description of p
                if cap is missing value then set cap to ""
                log "CAPTION_DATA:::" & fName & ":::" & cap
                export {p} to (POSIX file exportFolder)
            end repeat
        end if
    end tell
end run
'''

SAFE_APPLESCRIPT = '''
on run argv
    set photoFilename to item 1 of argv
    set baseFilename to item 2 of argv
    set newTitle to item 3 of argv
    set newCaption to item 4 of argv
    set albumSrc to item 5 of argv
    set albumDest to item 6 of argv
    
    tell application "Photos"
        if not (exists album albumDest) then
            make new album named albumDest
        end if
        
        set srcAlbum to null
        if exists album albumSrc then
            set srcAlbum to album albumSrc
        end if
        
        set destAlbum to album albumDest
        
        if srcAlbum is not null then
            set targetItems to (media items of srcAlbum whose filename is photoFilename)
            if (count of targetItems) is 0 then
                set targetItems to (media items of srcAlbum whose filename contains baseFilename)
            end if
            
            repeat with p in targetItems
                try
                    set name of p to newTitle
                    set description of p to newCaption
                end try
            end repeat
            
            if (count of targetItems) > 0 then
                try
                    add targetItems to destAlbum
                end try
            end if
        end if
    end tell
end run
'''

print(f"📸 写真アプリの '{ALBUM_SRC}' アルバムから画像と撮影意図（キャプション）を抽出中...")

user_intents = {}
try:
    res = subprocess.run(["osascript", "-", TEMP_DIR, ALBUM_SRC], input=EXPORT_WITH_CAPTION_SCRIPT, text=True, capture_output=True, timeout=300)
    for line in res.stderr.splitlines():
        if "CAPTION_DATA:::" in line:
            parts = line.split("CAPTION_DATA:::")[1].split(":::")
            if len(parts) >= 2:
                fname = parts[0].strip()
                caption = parts[1].strip()
                user_intents[fname] = caption
except Exception as e:
    print(f"⚠️ キャプション読み込み警告: {e}")

files = [f for f in os.listdir(TEMP_DIR) if not f.startswith(".")]

if not files:
    print(f"⚠️ アルバム '{ALBUM_SRC}' に対象の写真が見つかりませんでした。")
    sys.exit(0)

print(f"✨ {len(files)} 枚の対象写真を検出しました。\n")

prog_map = {
    1: "マニュアル (M)", 2: "プログラムAE (P)", 3: "絞り優先AE (A)",
    4: "シャッター優先AE (S)", 5: "クリエイティブ", 6: "アクション",
    7: "ポートレート", 8: "風景"
}

PROMPT_TEMPLATE = """あなたは写真の美と物語を深く理解する写真美術誌のキュレーター兼写真評論家です。
提示された「写真画像」と「撮影者の意図・悩み」を踏まえ、写真の魅力を深く言語化してください。

【評価トーン指示（50:50のゴールデンバランス）】
・**【称賛・魅力の発見 50%】** : 撮影者の視点や意図、写真が持つ独自の魅力・情緒・美点を温かく肯定的に深く言語化してください。
・**【批評・成長の示唆 50%】** : プロの目から見た「撮影者の悩みへの回答」および「表現をさらに引き立てるための課題や改善策」を建設的に助言してください。

【光と強さに関するルール】
・「朝＝柔らかい光」等の固定概念を禁止します。直射光の「眩しさ」「強いシャドウ」等、現実の光の表現をありのまま評価してください。

【厳格な指示】
・「三分割法」「柔らかい光」等の定型句の使い回しを禁止します。
・「一歩前に出て広角端で寄る」「F8まで絞る」など具体的な数値・動作を指定してください。

# 照合用情報
・ファイル名: {filename}
・撮影日時: {photo_datetime}
・カメラ: {camera}
・レンズ: {lens}
・設定: {settings}
・撮影者の意図・悩み: {user_intent}

---

# 出力フォーマット

■TITLE: (写真のストーリーや本質を射抜くタイトルを15文字以内で出力)

■SUMMARY: (写真全体を一言で表す魅力的なサマリー・キャッチコピーを25文字以内で出力)

■SCORES:
・構図・構成 : [★の数5段階] (X/5)
・光・色彩   : [★の数5段階] (X/5)
・ストーリー : [★の数5段階] (X/5)
・技術・露出 : [★の数5段階] (X/5)
・独自・世界観: [★の数5段階] (X/5)

---
ファイル名: {filename}
撮影日時: {photo_datetime}
ファイル更新日時: {file_mtime}
カメラ: {camera}
レンズ_焦点距離: {lens}
設定: {settings}
撮影意図: {user_intent}

---
## 【1. 情景・空気感とストーリー性】
・画面内で主役と背景が紡ぎ出す物語。撮影者の意図（{user_intent}）がどう写真に結実しているか、またはどうすればより意図が伝わるかを深く言語化してください。

## 【2. 視線誘導と構成の美学】
・観客の視線がどこから入り、どう巡るか。光と影、配置や余白がどのような「視覚的リズム」を生み出しているか。

## 【3. 光の強弱・色彩と印象解析】
・【光の実際の強さと質】（眩しさ、直射光、陰影の濃さ等）を描写し、色彩の対比が見る者の心理に与える印象を分析してください。

## 【4. EXIFデータの技術的役割と表現効果】
・設定（F値、SS、露出補正）が「この空気感・解像感・明暗を生み出すためにどう貢献しているか（または惜しい点）」を評価してください。

## 【5. 撮影者のためのステップアップ・アドバイス】
・**この写真の最大の魅力（核心）**: 表現として最も成功している情緒的・視覚的価値。
・**次回試すべき具体的アクション（意図への回答を含む）**: （※距離・立ち位置・レンズワーク・絞り値など具体的な数値・動作を指定）

## 【6. フォトブック＆SNSでの役割提案】
・**フォトブックでの配置・役割**: （例：アルバムの表紙 / 章の始まりを告げる大判メイン / 感情を落ち着かせる静かなアクセント枠 など提案）
・**Instagram適合度**: ★☆☆☆☆ 〜 ★★★★★（評価理由、世界観を深めるキャプション草案、ハッシュタグ5選）

## 【7. 自動タグ】
#カメラ_[モデル名] #レンズ_[焦点距離] #構図_[主要な構図名] #光_[光の種別] #雰囲気_[空気感のタグ]
"""

stats = {"total": len(files), "new": 0, "reanalyzed": 0, "skipped": 0, "error": 0}

for idx, filename in enumerate(files, 1):
    print(f"--------------------------------------------------")
    print(f"🔍 [{idx}/{len(files)}枚目] 検証中: {filename}")
    file_path = os.path.join(TEMP_DIR, filename)

    mtime_ts = os.path.getmtime(file_path)
    file_mtime = datetime.fromtimestamp(mtime_ts).strftime("%Y-%m-%d %H:%M:%S")

    exif_data = extract_comprehensive_exif(file_path)

    raw_datetime = str(exif_data.get("DateTimeOriginal") or exif_data.get("DateTime") or "").replace('\x00', '').strip()
    if raw_datetime and len(raw_datetime) >= 19:
        photo_datetime = raw_datetime[:10].replace(":", "-") + raw_datetime[10:19]
        photo_year = raw_datetime[:4]
        if not photo_year.isdigit():
            photo_year = "その他"
    else:
        photo_datetime = raw_datetime or "不明"
        photo_year = "その他"

    year_save_dir = os.path.join(SAVE_DIR_BASE, photo_year)
    os.makedirs(year_save_dir, exist_ok=True)
    
    save_path, save_filename, status = check_duplicate_and_get_path(year_save_dir, filename)
    log_file_path = os.path.join(LOG_DIR_BASE, f"写真分析ログ_{photo_year}.txt")

    if status == "SKIP":
        print(f"   ⏩ [重複スキップ] 同名ファイル『{filename}』の解析済みノートが存在します。")
        stats["skipped"] += 1
        time.sleep(0.2)
        continue
    else:
        print(f"   ✨ [新規解析] 新規ノート『{save_filename}』を作成します。")

    make = str(exif_data.get("Make", "")).replace('\x00', '').strip()
    model = str(exif_data.get("Model", "")).replace('\x00', '').strip()
    camera_full = f"{make} {model}".strip() or "不明"

    f_number = exif_data.get("FNumber")
    exp_time = exif_data.get("ExposureTime")
    iso = exif_data.get("ISO") or exif_data.get("ISOSpeedRatings")
    focal = exif_data.get("FocalLength")
    lens = str(exif_data.get("LensModel", "不明")).replace('\x00', '').strip()

    exp_bias = exif_data.get("ExposureBiasValue")
    exp_prog = exif_data.get("ExposureProgram")

    try: f_str = f"F{float(f_number):.1f}" if f_number else "不明"
    except: f_str = str(f_number or "不明")

    try:
        if exp_time:
            ss_val = float(exp_time)
            ss_str = f"1/{round(1/ss_val)}秒" if 0 < ss_val < 1 else f"{ss_val}秒"
        else: ss_str = "不明"
    except: ss_str = str(exp_time or "不明")

    iso_str = str(iso[0]) if isinstance(iso, (tuple, list)) else str(iso or "不明")

    try: focal_str = f"{float(focal):.0f}mm" if focal else "不明"
    except: focal_str = str(focal or "不明")

    try:
        if exp_bias is not None:
            bias_val = float(exp_bias)
            ev_str = f"{bias_val:+.1f} EV"
        else: ev_str = "±0 EV"
    except: ev_str = str(exp_bias or "±0 EV")

    if exp_prog in prog_map: mode_str = prog_map[exp_prog]
    else: mode_str = "不明"

    settings_full = f"F値: {f_str} / SS: {ss_str} / ISO: {iso_str} / 焦点距離: {focal_str} / 露出補正: {ev_str} / 撮影モード: {mode_str}"
    
    intent_text = user_intents.get(filename, "").strip() or "特になし（AIにおまかせ）"

    print(f"   [撮影年] {photo_year}年 ({photo_datetime})")
    print(f"   [EXIF] {camera_full} | {lens}")
    print(f"   [設定] {settings_full}")
    print(f"   [撮影意図・悩み] {intent_text}")

    base64_img = load_and_encode_image(file_path)
    prompt = PROMPT_TEMPLATE.format(
        filename=filename, photo_datetime=photo_datetime,
        file_mtime=file_mtime, camera=camera_full,
        lens=lens, settings=settings_full,
        user_intent=intent_text
    )

    result_text = None
    is_refused = False
    max_retries = 2

    for attempt in range(max_retries + 1):
        is_refused = False
        result_text = None
        
        try:
            retry_label = f" (試行 {attempt + 1}/{max_retries + 1})" if attempt > 0 else ""
            print(f"   ✨ OpenAI ({MODEL_NAME}) で意図＆スコア付き講評作成中...{retry_label}")
            
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_img}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2500,
                timeout=90.0
            )
            result_text = response.choices[0].message.content
        except Exception as e:
            err_msg = str(e)
            print(f"   ⚠️ OpenAI API通信エラー: {err_msg}")
            if "429" in err_msg or "rate_limit" in err_msg.lower():
                wait_time = 10 * (attempt + 1)
                print(f"   ⏳ Rate Limit(トークン制限)を検出。{wait_time}秒待機して再試行します...")
                time.sleep(wait_time)

        if result_text:
            for kw in REFUSAL_KEYWORDS:
                if kw.lower() in result_text.lower():
                    is_refused = True
                    break

        if result_text and not is_refused:
            break
        else:
            if attempt < max_retries and not ("429" in str(locals().get('e', ''))):
                reason = "AI安全フィルター拒否" if is_refused else "応答なし"
                print(f"   🔄 【自動リトライ】{reason}を検出。3秒後に再挑戦します...")
                time.sleep(3)

    if not result_text or is_refused:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        reason = "AI安全フィルター拒否" if is_refused else "API通信エラー/RateLimit"
        append_log_safely(log_file_path, f"\n\n==================================================\n解析日時: {now_str} | ファイル: {filename} | 【{reason}のためスキップ】\n==================================================\n")
        print(f"   ⚠️ {filename} は{reason}のため解析をスキップしました（01_AI解析用 アルバムに残存）\n")
        stats["error"] += 1
        continue

    # 1. 撮影年フォルダにMarkdownノート保存
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(result_text)
    print(f"   ✅ [1/4] ノート保存成功: {photo_year}/{save_filename}")
    stats["new"] += 1

    # 2. 講評カード画像の自動生成と保存（白黒反転・アスペクト比対応版）
    try:
        analysis_data = parse_gpt_output(result_text)
        card_output_filename = f"{sanitize_filename(os.path.splitext(filename)[0])}_card.jpg"
        card_output_path = os.path.join(year_save_dir, card_output_filename)
        
        create_critique_card(
            image_path=file_path,
            analysis_data=analysis_data,
            output_path=card_output_path
        )
        print(f"   ✅ [2/4] 講評カード画像作成成功: {photo_year}/{card_output_filename}")
    except Exception as e:
        print(f"   ⚠️ 講評カード画像作成エラー: {e}")

    # 3. 撮影年別の年間ログファイルに「講評全文」を追記
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = (
        f"\n\n==================================================\n"
        f"📌 解析日時: {now_str} | ノート名: {save_filename}\n"
        f"==================================================\n"
        f"{result_text}\n"
    )
    append_log_safely(log_file_path, log_entry)
    print(f"   ✅ [3/4] 年間ログ追記成功 (写真分析ログ_{photo_year}.txt)")

    # 4. 写真アプリ整理
    title_match = re.search(r"■\s*TITLE\s*[:：]\s*(.+)", result_text, re.IGNORECASE)
    title_line = title_match.group(1).strip().replace("*", "") if title_match else "タイトル不明"
    base_filename = os.path.splitext(filename)[0]

    try:
        subprocess.run([
            "osascript", "-",
            filename,
            base_filename,
            title_line,
            result_text,
            ALBUM_SRC,
            ALBUM_DEST
        ], input=SAFE_APPLESCRIPT, text=True, check=True, timeout=60)
        print(f"   ✅ [4/4] 写真アプリ書き込み ＆ 『{ALBUM_DEST}』へ追加完了")
    except Exception as e:
        print(f"   ⚠️ 写真アプリへの書き込み警告 (処理は継続します): {e}")

    time.sleep(1)
    print("")

if os.path.exists(TEMP_DIR):
    shutil.rmtree(TEMP_DIR)

print("==================================================")
print("🎉 すべての処理が正常に完了しました！")
print("--------------------------------------------------")
print(f" 📊 処理結果サマリー:")
print(f"   ・対象総数   : {stats['total']} 枚")
print(f"   ・新規解析ノート: {stats['new']} 枚")
print(f"   ・重複スキップ : {stats['skipped']} 枚 (同名ノート存在によりスキップ)")
if stats['error'] > 0:
    print(f"   ・AI拒否/失敗  : {stats['error']} 枚")
print("==================================================")