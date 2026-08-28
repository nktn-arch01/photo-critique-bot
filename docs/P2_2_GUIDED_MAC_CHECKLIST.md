# P2-2 Guided Web — Mac 手動確認チェックリスト

更新日: 2026-08-28  
対象: **オーナー（コード未経験）**。ターミナルは **コピペ一発** のみ。編集不要。  
ブランチ: `cursor/p2-2-web-concept-f193`  
関連: [`P2_2_WEB_APP_CONCEPT.md`](P2_2_WEB_APP_CONCEPT.md) / [`ARCHITECTURE.md`](../ARCHITECTURE.md)

---

## この文書の使い方

1. 上から **ステップ0 → ステップ5** まで順に実行  
2. 各ステップの **PASS / FAIL** を記入  
3. FAIL があれば、その番号とターミナルに出た文字をそのまま共有  

コードの編集は不要です。

---

## ステップ0 — ターミナルを開く

1. Mac の **ターミナル** を開く  
   - Spotlight（⌘ + スペース）で `ターミナル` と入力して Enter でも可  
2. 黒い画面が出たら、次のステップへ  

| # | 結果 |
|---|------|
| 0 | PASS / FAIL |

---

## ステップ1 — 最新コードを取得する

ターミナルに、次の **6行まとめて** コピーして貼り付け、Enter を1回押してください。

> リポジトリを `~/photo-critique-bot` 以外に置いている場合は、1行目のパスだけ自分の場所に直してください。

```bash
cd ~/photo-critique-bot
git fetch origin
git checkout cursor/p2-2-web-concept-f193
git pull origin cursor/p2-2-web-concept-f193
pwd
git branch --show-current
```

**見てほしいこと**

- エラーが出ない  
- 最後の行が `cursor/p2-2-web-concept-f193`  

| # | 結果 |
|---|------|
| 1 | PASS / FAIL |

---

## ステップ2 — Guided Web を起動する（コピペ一発）

### 方法A（推奨）: ターミナル1行

**すでにステップ1で `cd ~/photo-critique-bot` 済みなら**、次の1行だけ:

```bash
bash scripts/run_guided_web.sh
```

**最初から1行でやる場合**（ステップ1を飛ばすとき用）:

```bash
cd ~/photo-critique-bot && bash scripts/run_guided_web.sh
```

### 方法B: Finder ダブルクリック

Finder でプロジェクトフォルダを開き、**`LuminaNotesGuided.command`** をダブルクリック。

---

**見てほしいこと**

- ターミナルに `=== Lumina Notes Guided ===` と表示される  
- 数秒後、ブラウザが開く  
- Finder に **`LuminaNotesGuided.command`** が無い場合 → ステップ1の `git pull` をやり直すか、ターミナル起動（方法A）を使う  

| # | 結果 |
|---|------|
| 2 | PASS / FAIL |

---

## ステップ3 — ブラウザ画面を確認する（選ぶ）

**操作**

1. **「写真を選ぶ」** をクリック  
2. Mac 上の JPEG 写真を1枚選ぶ  
3. **選んだ写真のプレビュー**がドロップゾーン内に表示される  
4. その下に **JSON 形式のパラメータ**（`image_id`, `time_band` など）が表示される  

> **補足:** `region` / `time_band` が `不明` のときは、写真 EXIF に **GPS が無い** ためです（仕様どおり）。GPS 付き写真で再確認できます。

| # | 確認内容 | PASS の目安 |
|---|----------|-------------|
| 3a | 3画面のラベル | 選ぶ・読む・振り返る が見える |
| 3b | **写真プレビュー** | 選んだ直後に画像が見える |
| 3c | パラメータ JSON | `image` / `camera` が表示される |

| # | 結果 |
|---|------|
| 3 | PASS / FAIL |

---

## ステップ4 — 画面遷移のスモーク（API 講評なしでも可）

1. **「言葉にする」** を押す → **読む** 画面に切り替わる  
2. **「もう一度」** を押す → **選ぶ** に戻る  
3. もう一度写真を選び、**言葉にする** → **この言葉を残す** → **振り返る** 画面へ  
4. **振り返る** で星が **☆☆☆☆☆**（未選択）から始まること  
5. 星を1〜5のどれかをタップ → **★** が付くこと  
6. 星を選ぶまで **「Noteに書き出す」** が押せない（または無効）こと  

| # | 結果 |
|---|------|
| 4 | PASS / FAIL |

---

## ステップ5 — 終了する

Guided を止めるとき、**起動したターミナル** をクリックして:

```text
Control + C
```

（キーボードの `control` キーを押しながら `C`）

**見てほしいこと**: サーバが止まり、ブラウザは更新しても繋がらなくなる。

| # | 結果 |
|---|------|
| 5 | PASS / FAIL |

---

## 初回のみ — OpenAI API キー（講評を動かすとき）

Console と同じです。**まだキーを置いていないときだけ** 実行。

`sk-....` をあなたの実際のキーに置き換えて、**1行コピペ**:

```bash
echo "sk-あなたのキーをここに" > ~/.openai_api_key && chmod 600 ~/.openai_api_key
```

| # | 結果 |
|---|------|
| API | 設定済み / 未設定（講評は後で） |

---

## オフライン自動テスト（任意・開発確認用）

講評 API は使いません。ターミナルで **新しいタブ**（⌘ + T）を開き:

```bash
cd ~/photo-critique-bot
python3 test_offline_suite.py
```

最後に `test_offline_suite: OK` と出れば PASS。

| # | 結果 |
|---|------|
| OT | PASS / FAIL / スキップ |

---

## うまくいかないとき（コピペ一発）

### python3 がない

[python.org](https://www.python.org/downloads/) から Python 3 をインストール後、ステップ2を再実行。

### ポートが使用中

```bash
cd ~/photo-critique-bot && GUIDED_WEB_PORT=8766 bash scripts/run_guided_web.sh
```

ブラウザは `http://127.0.0.1:8766/` を開く。

### すでに起動中

同じ `bash scripts/run_guided_web.sh` を再度実行すると「すでに起動中」と出てブラウザだけ開きます。

---

## 合計 PASS / FAIL（オーナー記入）

| ステップ | 内容 | 結果 |
|----------|------|------|
| 0 | ターミナル起動 | |
| 1 | git pull | |
| 2 | Guided 起動 | |
| 3 | 選ぶ・パラメータ表示 | |
| 4 | 画面遷移・★必須 | |
| 5 | 終了 Ctrl+C | |

**全部 PASS** なら「Guided Mac 確認 PASS」と返信してください。
