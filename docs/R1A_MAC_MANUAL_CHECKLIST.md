# R1′-A Mac 手動確認チェックリスト

更新日: 2026-08-11  
位置づけ: **オーナーが Mac 実機で GUI／実フォルダを確認する手順**。Cloud Agent では実行不可。  
関連: [`R1A_DESKTOP_OPS_POLICY.md`](R1A_DESKTOP_OPS_POLICY.md) / [`R1A_IMPLEMENTATION_BREAKDOWN.md`](R1A_IMPLEMENTATION_BREAKDOWN.md) / [`IPTC_SYNC_VERIFICATION.md`](IPTC_SYNC_VERIFICATION.md)

**用語（2026-08-11）:** ウィンドウ名 **Lumina Notes Console**（スクリーニング + Lumina Review）。旧「短絡／短絡バッチ」→ **スクリーニング**、旧「痕跡生成」→ **Lumina Review**。

結果の書き方: 各行の **結果** に `PASS` / `FAIL` / `SKIP` と短いメモを書く。完了したら本ファイルか PR コメントに貼る。

---

## 0. 事前準備（5〜10分）

### 0.1 ブランチを取り込む

Mac のリポジトリで（パスは自分の clone 先に合わせる。よくある例: `~/photo-critique-bot`）:

**いま確認したいもの = UX Wave A（PR #10）のとき:**

```bash
cd ~/photo-critique-bot
git fetch origin
git checkout cursor/lumina-ux-wave-a-c35c
git pull origin cursor/lumina-ux-wave-a-c35c
```

**PR が `main` にマージ済みなら:**

```bash
cd ~/photo-critique-bot
git checkout main
git pull origin main --ff-only
```

初心者向けの **Wave A だけ**の手順は §11.1 を上から順に。

### 0.2 依存を確認

```bash
python3 -c "import PIL; print('PIL OK')"
which exiftool || echo "exiftool がありません（brew install exiftool）"
test -f ~/.openai_api_key && echo "APIキーあり" || echo "APIキーなし（M2/M3・Lumina Review は SKIP 可）"
```

| # | 確認 | 結果 |
|---|------|------|
| P1 | `exiftool` がある | |
| P2 | `~/.openai_api_key` がある（無い場合は M2/M3・Lumina Review を SKIP） | |
| P3 | 最新ブランチを pull した | |

### 0.3 確認用フォルダを作る（推奨）

リポジトリ直下で:

```bash
python3 prepare_mac_manual_fixtures.py
```

既定の出力先: `~/Desktop/LuminaManualCheck/`

中身のイメージ:

```text
~/Desktop/LuminaManualCheck/
  OM202608/                    # スクリーニング・月（機種接頭辞）
    sample_a.jpg …
    OM20260815_旅行/           # スクリーニング・イベント
      trip_a.jpg …
  2026/
    202608/                    # Works 月（Lumina Review）
      W1_dev.jpg
      W2.jpg
      _subdir_only/            # L4 案内確認用（直下には置かない JPEG）
        buried.jpg
```

| # | 確認 | 結果 |
|---|------|------|
| P4 | フィクスチャが作れた／または実運用フォルダを使う準備ができた | |

---

## 1. Lumina Notes Console 起動

Finder で `LuminaNotesConsole.command` をダブルクリック（旧 `LuminaShortlist.command` も可。またはターミナルで `python3 shortlist_gui.py`）。

| # | 確認 | 結果 |
|---|------|------|
| S1 | ウィンドウ「Lumina Notes Console」が開く | |

---

## 2. P1 — 機種接頭辞フォルダ

1. 「対象フォルダ」で `…/OM202608` を選ぶ  
2. **ドライラン ON**、段は **M1 のみ** で「スクリーニングを開始」

| # | 確認 | 結果 |
|---|------|------|
| A1 | `OM202608` が「フォルダ名エラー」にならない | |
| A2 | バッチが完了し、ログに JPEG 枚数が出る | |
| A3 | （任意）`OM20260815_旅行` でも同様に開始できる | |

書き込み確認（任意・ドライラン OFF）:

| # | 確認 | 結果 |
|---|------|------|
| A4 | M1 書き込み後、Finder／exiftool で Rating が入る | |

---

## 3. L2 — 監査フォルダを開く（mkdir しない）

**まだスクリーニングを一度も書いていない別フォルダ**（またはフィクスチャを作り直した直後）で:

1. 対象に空の規則フォルダを選ぶ（例: 新規 `OM202609`）  
2. 「監査フォルダを開く」を押す  

| # | 確認 | 結果 |
|---|------|------|
| B1 | 「まだスクリーニングセッションがありません」系の案内が出る | |
| B2 | Finder 上に `_lumina` フォルダが**勝手に作られていない** | |

その後、ドライラン OFF でスクリーニングを1回実行してから再度「監査フォルダを開く」:

| # | 確認 | 結果 |
|---|------|------|
| B3 | `_lumina/sessions` が開き、JSON が見える | |

---

## 4. M2 — DxO修正後を記録（target 正）

1. `OM202608` でスクリーニングを1回完了させる（ドライラン OFF・少なくとも M1）  
2. 画面上の対象パスを**わざと別の存在するフォルダ名に手編集**してから戻す、または別フォルダを一度選んでから再び `OM202608` を選ぶ  
3. 「DxO修正後を記録」を押す  

| # | 確認 | 結果 |
|---|------|------|
| C1 | 確認ダイアログのセッション名が **いまの対象フォルダ配下** のもの | |
| C2 | 記録完了し、ログに `changed=` / `unchanged=` が出る | |
| C3 | （任意）DxO で Rating を1枚変えてから再度記録 → `changed_count` が増える | |

---

## 5. M3/M4 — 開始時スナップショット／固まりにくさ

1. スクリーニング開始確認ダイアログの直前まで進む  
2. 開始後、チェックボックスをいじっても**実行中の設定は変わらない**（見た目だけ変わるのは可）  
3. 「DxO修正後を記録」中もウィンドウ操作ができる（完全フリーズしない）  

| # | 確認 | 結果 |
|---|------|------|
| D1 | 実行中に UI が長時間完全停止しない | |

---

## 6. L1 — 実行中にウィンドウを閉じる

1. M1 のみ・枚数のあるフォルダでスクリーニングを開始  
2. すぐウィンドウを閉じる（確認で「終了」）  
3. ターミナル／コンソールに `TclError` / `application has been destroyed` が**大量に出ていない**  

| # | 確認 | 結果 |
|---|------|------|
| E1 | 閉じたあとに致命的な Tk エラーが出ない | |

---

## 7. M1 / L4 — Works Lumina Review（YYYYMM・直下のみ）

1. Works に `…/2026/202608` を選ぶ  
2. 「Lumina Reviewを開始」（API キーが無い場合は SKIP）  

| # | 確認 | 結果 |
|---|------|------|
| F1 | `YYYYMM` 以外の名前を選ぶとエラー／注意になる | |
| F2 | 直下の `_dev` / `.jpg` が対象になる | |
| F3 | Lumina Review 後も JPEG 枚数が増えない（コピーなし） | |
| F4 | カード／ノート／ログが Works 月フォルダ内にできる | |
| F5 | Works を `_subdir_only` だけにした状態（直下 JPEG を一時退避）で開始 → 「サブフォルダ内に JPEG が…」案内が出る | |

年次ログ:

| # | 確認 | 結果 |
|---|------|------|
| F6 | `…/2026/Luminaログ_2026.txt` など年フォルダ側に年次が出る（Wave 2 公式名） | |

---

## 8. L3 — RatingPercent のみ（任意・技術確認）

API／GUI ではなくターミナルで十分:

```bash
# フィクスチャの1枚で Rating を消し、Percent だけ残す例
IMG=~/Desktop/LuminaManualCheck/OM202608/sample_a.jpg
exiftool -overwrite_original -Rating= -XMP:Rating= -RatingPercent=60 "$IMG"
python3 -c "
from iptc_rating_io import read_screening_meta
from pathlib import Path
import os
p=Path(os.path.expanduser('$IMG'))
print(read_screening_meta(p).rating)  # 期待: 3
"
```

| # | 確認 | 結果 |
|---|------|------|
| G1 | 出力が `3` | |

---

## 9. 総合メモ

| 項目 | 記入 |
|------|------|
| 実施日 | |
| macOS 版 | |
| DxO 版（使った場合） | |
| 使ったフォルダ（実運用／フィクスチャ） | |
| FAIL の詳細 | |
| 次に直してほしいこと | |

---

## 10. 合否の目安

- **必須寄り:** A1, B1–B3, C1–C2, F1–F3  
- **あれば安心:** E1, F4–F6, D1  
- **任意:** A4, C3, G1、API が要る Lumina Review フル実行  

すべて必須寄りが PASS なら、R1′-A デスクトップ運用の手動確認は完了扱いにできる。

---

## 11. Wave A（UX・2026-08-12 以降）

ブランチ例: `cursor/lumina-ux-wave-a-c35c` / 計画: `docs/R1A_UX_IMPROVEMENT_PLAN.md`

| # | 確認 | 結果 |
|---|------|------|
| W1 | APIキーを一時退避した状態で M2 ON → 開始前に「APIキーがありません」 | |
| W2 | 同上で Lumina Review → 開始前にキーエラー（バッチ途中ではない） | |
| W3 | Works に `A.jpg` + `A_dev.jpg` → 確認ダイアログに撮って出し除外の件数 | |
| W4 | 書き込みスクリーニング後・未記録のままウィンドウを閉じる → 「記録の確認」 | |
| W5 | ヘルプが単独実行可の説明、Lumina Review 完了が「対話痕跡ができました」系 | |
| W6 | タブ「スクリーニング」と「Lumina Review」が分かれ、Review だけ実行できる | |

### 11.1 初心者向け：Wave A だけを順に確認する手順

コードは編集しません。**ターミナルへコピー＆ペースト**と、画面の見た目確認だけです。  
わからない・FAIL になったら、その番号（例: W3）と画面に出た文言をメモして伝えてください。

#### ステップ0 — ターミナルを開く

1. Mac の「ターミナル」アプリを開く（Spotlight で `ターミナル` と検索でも可）
2. 次を **まとめて** 貼り付けて Enter

```bash
cd ~/photo-critique-bot
git fetch origin
git checkout cursor/lumina-ux-wave-a-c35c
git pull origin cursor/lumina-ux-wave-a-c35c
pwd
git branch --show-current
```

**見てほしいこと:** 最後の行が `cursor/lumina-ux-wave-a-c35c` であること。  
違う／エラーならここで止めて、出た文字をそのまま共有してください。

#### ステップ1 — 確認用フォルダを作る

同じターミナルで:

```bash
cd ~/photo-critique-bot
python3 prepare_mac_manual_fixtures.py
```

**見てほしいこと:** 「作成完了」と出て、Desktop に `LuminaManualCheck` ができること。

Wave A の W3 用に、撮って出し＋`_dev` のペアも足します:

```bash
python3 - <<'PY'
from pathlib import Path
from PIL import Image, ImageDraw

works = Path.home() / "Desktop" / "LuminaManualCheck" / "2026" / "202608"
works.mkdir(parents=True, exist_ok=True)

def save(name, color, label):
    p = works / name
    img = Image.new("RGB", (320, 240), color)
    d = ImageDraw.Draw(img)
    d.text((40, 100), label, fill=(255, 255, 255))
    img.save(p, "JPEG", quality=90)
    print("wrote", p)

save("A.jpg", (90, 40, 40), "A sooc")
save("A_dev.jpg", (40, 90, 50), "A_dev")
print("OK: Works に A.jpg と A_dev.jpg を追加しました")
PY
```

#### ステップ2 — Console を起動する

Finder で次をダブルクリック:

`~/photo-critique-bot/LuminaNotesConsole.command`

（またはターミナルで）

```bash
cd ~/photo-critique-bot
python3 console_gui.py
```

**見てほしいこと（W5 / W6）:**

- ウィンドウタイトルが **Lumina Notes Console**
- 上部にタブが2つ: **スクリーニング** / **Lumina Review**
- 「Lumina Review」タブを開くと、スクリーニング無しでも Works だけ選べること
- 各タブの説明に「単独で実行できます」系の文言があること

| # | 結果（自分で記入） |
|---|-------------------|
| W5（見た目・文言） | |
| W6（タブ分離） | |

#### ステップ3 — W1：APIキー無しでスクリーニングが止まるか

**注意:** キーを一時的にどかすだけです。終わったら必ず戻します。

ターミナル（Console とは別ウィンドウで可）:

```bash
# 退避（キーがある場合）
test -f ~/.openai_api_key && mv ~/.openai_api_key ~/.openai_api_key.bak_waveA && echo "退避しました" || echo "もともとキーファイルなし"
```

Console で:

1. **① 対象フォルダ** → 参照 → `デスクトップ/LuminaManualCheck/OM202608`
2. チェック: **M1・M2 を ON**（M3 はどちらでも可）、**ドライランは ON でよい**
3. 「スクリーニングを開始」を押す

**見てほしいこと:** 「実行確認」の前、またはすぐ後に **「APIキーがありません」** 系が出て、長い処理が始まらないこと。

| # | 結果 |
|---|------|
| W1 | |

#### ステップ4 — W2：APIキー無しで Lumina Review が止まるか

キーはまだ退避したまま。

1. **③** の Works 参照 → `デスクトップ/LuminaManualCheck/2026/202608`
2. 「Lumina Review を開始」を押す

**見てほしいこと:** **「APIキーがありません」** が出て、進捗バーが長く動かないこと。

| # | 結果 |
|---|------|
| W2 | |

キーを戻す（必須）:

```bash
test -f ~/.openai_api_key.bak_waveA && mv ~/.openai_api_key.bak_waveA ~/.openai_api_key && echo "キーを戻しました" || echo "戻すバックアップがありません"
```

#### ステップ5 — W3：撮って出し除外が見えるか

キーを戻したあと、必要なら Console をいったん閉じて開き直す。

1. Works に `…/2026/202608` を選ぶ（ログに「撮って出し除外」と出ればよい）
2. 「Lumina Review を開始」→ **確認ダイアログ**を読む（まだ「いいえ」で止めてよい）

**見てほしいこと:**

- 対象枚数の内訳に `_dev` と撮って出しがある
- **「_dev 優先で撮って出し除外: 1 枚」**（または `A.jpg` の名前）が出る

| # | 結果 |
|---|------|
| W3 | |

（ここで本番の Review までは不要。W5 の完了文を見たいときだけ「はい」で実行。API 利用あり）

#### ステップ6 — W4：閉じるときに記録確認が出るか

1. ① で `OM202608` を選ぶ
2. **ドライラン OFF**、**M1 のみ ON**（M2/M3 は OFF）、「スクリーニングを開始」→ 完了まで待つ  
   （JPEG に Rating が書かれます。確認用フォルダなので問題ありません）
3. **「DxO修正後を記録」は押さない**
4. ウィンドウの赤丸で閉じる

**見てほしいこと:** **「記録の確認」** と「後で記録しても大丈夫です」が出る。  
「いいえ」ならウィンドウが残る。「はい」なら終了。

| # | 結果 |
|---|------|
| W4 | |

#### ステップ7 — 結果の伝え方

次をコピーして、チャットか PR #10 に貼ってください。

```text
Wave A Mac 確認
ブランチ: cursor/lumina-ux-wave-a-c35c
W1:
W2:
W3:
W4:
W5:
W6:
気づいたこと（イメージと違う点）:
```

各行は `PASS` / `FAIL` / `SKIP` ＋短いメモで十分です。  
**あなたの役割は「画面がイメージどおりか」の判定だけ**です。直しはこちらで行います。

