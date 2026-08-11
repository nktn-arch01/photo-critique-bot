# R1′-A Mac 手動確認チェックリスト

更新日: 2026-08-11  
位置づけ: **オーナーが Mac 実機で GUI／実フォルダを確認する手順**。Cloud Agent では実行不可。  
関連: [`R1A_DESKTOP_OPS_POLICY.md`](R1A_DESKTOP_OPS_POLICY.md) / [`R1A_IMPLEMENTATION_BREAKDOWN.md`](R1A_IMPLEMENTATION_BREAKDOWN.md) / [`IPTC_SYNC_VERIFICATION.md`](IPTC_SYNC_VERIFICATION.md)

**用語（2026-08-11）:** 旧「短絡／短絡バッチ」→ **スクリーニング**、旧「痕跡生成」→ **Lumina Review**。

結果の書き方: 各行の **結果** に `PASS` / `FAIL` / `SKIP` と短いメモを書く。完了したら本ファイルか PR コメントに貼る。

---

## 0. 事前準備（5〜10分）

### 0.1 ブランチを取り込む

Mac のリポジトリで（パスは自分の clone 先に合わせる）:

```bash
cd /path/to/photo-critique-bot
git fetch origin
git checkout cursor/lumina-dialogue-workflow-spec-e779
git pull origin cursor/lumina-dialogue-workflow-spec-e779
```

または PR #7 が `main` にマージ済みなら `main` でよい。

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

## 1. スクリーニング GUI 起動

Finder で `LuminaShortlist.command` をダブルクリック（またはターミナルで `python3 shortlist_gui.py`）。

| # | 確認 | 結果 |
|---|------|------|
| S1 | ウィンドウ「Lumina Notes スクリーニング」が開く | |

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
| F6 | `…/2026/写真分析ログ_2026.txt` など年フォルダ側に年次が出る（既存仕様どおり） | |

---

## 8. L3 — RatingPercent のみ（任意・技術確認）

API／GUI ではなくターミナルで十分:

```bash
# フィクスチャの1枚で Rating を消し、Percent だけ残す例
IMG=~/Desktop/LuminaManualCheck/OM202608/sample_a.jpg
exiftool -overwrite_original -Rating= -XMP:Rating= -RatingPercent=60 "$IMG"
python3 -c "
from iptc_rating_io import read_shortlist_meta
from pathlib import Path
import os
p=Path(os.path.expanduser('$IMG'))
print(read_shortlist_meta(p).rating)  # 期待: 3
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
