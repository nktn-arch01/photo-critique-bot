# Phase D — 応答評価（`lens=self`）

実 API で講評品質を確認するゲート。CI では実行しない。

関連: `docs/PHASE_A_CHECKLIST.md` / `scripts/phase_d_eval.py`

---

## 前提（ブロッカー）

| 必要 | 状態の目安 |
|------|------------|
| `OPENAI_API_KEY` | 環境 Secrets または `~/.openai_api_key` / シェル環境変数 |
| 評価用写真 4〜8枚 | `eval/phase_d/images/` に配置（下表のスロット） |
| 本ブランチのコード | `cursor/lumina-self-lens-prompts-e0e5` 相当 |

### API キー動作確認（Cloud Agent 向け）

シェルに `OPENAI_API_KEY` が出なくても、**`~/.openai_api_key` があればアプリは動く**（`ai_vision.get_openai_client()` がファイルを読む）。次の3点を確認する。

```bash
test -f ~/.openai_api_key && echo "keyfile=yes" || echo "keyfile=no"
test -n "$OPENAI_API_KEY" && echo "OPENAI_API_KEY=set" || echo "OPENAI_API_KEY=unset"
cd /workspace && ~/.venv/bin/python -c "from ai_vision import get_openai_client; get_openai_client(); print('key OK')"
```

| 出力の意味 | 目安 |
|------------|------|
| `keyfile=yes` | ファイル経路でキー利用可 |
| `OPENAI_API_KEY=unset` | Start Script / Runtime Secrets がシェルに載らない場合あり（**問題にならない**） |
| `key OK` | Phase D の実 API 呼び出しに進んでよい |

---

## 評価用写真の選定（推奨セット）

最低 **4枚（P01〜P04）**。可能なら **6〜8枚**。

| ID | カテゴリ | 選定の狙い | 主に見る観点 |
|----|----------|------------|--------------|
| P01 | person | 人物がいる（しぐさ・視線・佇まいが読める） | D-person, D-role |
| P02 | light | 光・反射・陰影が主役 | D-score-meaning, D-title |
| P03 | ambiguity | ブレ／露出過不足／ピント甘めなど「曖昧さ」がある | D-exif, D-advice |
| P04 | subject_label | 花・空・海など「被写体名ラベル」に逃げやすい被写体 | D-title |
| P05 | no_person | 人物なしの風景／静物 | D-person（該当なし扱いで OK）, D-summary |
| P06 | time_temptation | 夕方っぽい光など時間帯ラベルに誘惑されやすい | D-title, 自動: 時間帯禁止語 |
| P07 | detail | 質感・細部寄りの一枚 | D-score-meaning |
| P08 | intent | 撮影意図がはっきりしている（任意で `manifest` に intent を書く） | D-advice, D-summary |

### ファイル配置

```text
eval/phase_d/
  manifest.json          … スロット定義（リポジトリにコミット可）
  images/                … 実写真（gitignore。ローカル／エージェントに置く）
    P01_person.jpg
    P02_light.jpg
    ...
  out/                   … 実行結果（gitignore）
```

命名は `manifest.json` の `filename` に合わせる。拡張子は jpg / jpeg / png / heic 可。  
`P04` だけ `P04_subject_label.jpg` のように manifest と名前が違っても、**先頭が `P04` ならスクリプトが拾う**（`scripts/phase_d_eval.py`）。

### Mac の手元フォルダ → クラウド VM（`/workspace`）へ

Cloud Agent のディスクは **GitHub から clone したリポジトリ**が `/workspace` です。  
Mac の `/Users/.../photo_ai/...` は **自動では同期されません**（「Move to Cloud」も未コミットのファイルは運ばない）。

| 方法 | 向いている人 | 手順の要点 |
|------|--------------|------------|
| **A. ローカル clone にコピーして `git add -f` → push（確実）** | デスクトップで `photo-critique-bot` を clone している人 | 下の「方法 A」参照 |
| **B. 一時 HTTPS URL + `curl`** | Git に写真を載せたくないとき | Dropbox / Drive「リンクを知っている人」等の直リンクをエージェントに渡し、VM で保存してもらう |
| **C. チャット添付** | 小さな画像の確認用のみ | **Phase D には向かないことが多い**。数 MB 超の JPEG は処理失敗し、成功しても **モデルが見るだけで `/workspace` にファイルが書かれない**ことがある |

#### 方法 A（推奨・確実）

Mac のターミナルで（パスは自分の clone 先に合わせる）:

**重要:** 下の `REPO=` は **GitHub から clone した本物のフォルダ**を指す。`どこか` や `path/to` は仮書きなので、そのままコピペしない。

まず Mac で clone の場所を探す（または新規 clone）:

```bash
# 既存 clone を探す（見つかればそのパスが答え）
mdfind -name photo-critique-bot 2>/dev/null | head -20
ls -la ~/photo-critique-bot ~/.cursor/worktrees 2>/dev/null
# Cursor デスクトップで開いているフォルダなら、そのパスを使う

# 見つからないときは新規 clone（例: ホーム直下）
cd ~
git clone https://github.com/nktn-arch01/photo-critique-bot.git
REPO="$HOME/photo-critique-bot"
```

写真を入れて push:

```bash
# ★ 上で決めた本物のパスを入れる（例）
REPO="$HOME/photo-critique-bot"
SRC="$HOME/photo_ai/eval/phase_d/images"

# 誤って作った空フォルダを消す場合（中身が写真コピーだけなら）
# rm -rf "$HOME/どこか"

mkdir -p "$REPO/eval/phase_d/images"
cp "$SRC"/P01_person.jpg "$SRC"/P02_light.jpg \
   "$SRC"/P03_ambiguity.jpg "$SRC"/P04_subject_label.jpg \
   "$REPO/eval/phase_d/images/"

cd "$REPO"
test -d .git || { echo "ERROR: ここは git リポジトリではありません: $REPO"; exit 1; }

git fetch origin
git checkout cursor/lumina-self-lens-prompts-e0e5
git pull origin cursor/lumina-self-lens-prompts-e0e5

git add -f eval/phase_d/images/P01_person.jpg \
           eval/phase_d/images/P02_light.jpg \
           eval/phase_d/images/P03_ambiguity.jpg \
           eval/phase_d/images/P04_subject_label.jpg
git commit -m "chore: add Phase D eval photos (force-add, gitignored path)"
git push -u origin HEAD
```

その後 Cloud Agent に「`git pull` して Phase D を実行して」と送る。

**注意:** `-f` で push すると **GitHub の履歴にも写真が残る**。公開リポでは使わない。終わったら削除コミットで消せるが、履歴には残る。

**できないこと:** Finder からクラウドのフォルダツリーへ直接ドロップする UI は現状ない。

---

## ルーブリック（観点 ID）

| ID | 自動/人手 | 合格の目安 |
|----|-----------|------------|
| D-axis-names | **自動** | 新5軸（または正規化後の表示名）が揃う |
| D-time-ban | **自動** | 朝日／夕日／夕焼け 等の禁止語が TITLE・SUMMARY・本文に無い |
| D-forbid-fix | **自動** | 「修正」「改善」「失敗」等が Phase2 に無い（full 時） |
| D-title-len | **自動** | TITLE がおおむね15文字以内 |
| D-role | 人手 | 採点者口調ではなく伴走・編集者 |
| D-score-meaning | 人手 | 技術出来ではなくアンテナの向き／純度 |
| D-title | 人手 | 被写体ラベルではなく仮説的・詩的 |
| D-summary | 人手 | 無意識の意図への仮説／対話のきっかけ |
| D-person | 人手 | しぐさ・視線・物語（人物なし写真は N/A 可） |
| D-exif | 人手 | 心の揺れ／曖昧さの肯定（full） |
| D-advice | 人手 | 問いかけで循環（full） |

### 合格ライン（v1 提案）

- 評価した枚数のうち **75%以上** が「自動すべて PASS」かつ「人手観点の欠格が0」（N/A 除く）
- 最低セット P01〜P04 を必ず含む
- `compact` でカード用品質、`full` で本文品質（コストを抑えるなら P01〜P04 のみ full、他は compact）

---

## 実行手順

```bash
# 1) 写真を eval/phase_d/images/ に置く（manifest の filename と一致）

# 2) API キー
export OPENAI_API_KEY='…'
# または: echo '…' > ~/.openai_api_key

# 3) 依存（venv 推奨）
source ~/.venv/bin/activate   # Cloud Agent 環境の場合
# または: source .venv/bin/activate

# 4) 評価実行
python3 scripts/phase_d_eval.py --mode both
# compact のみ: --mode compact
# 特定スロット: --ids P01,P02,P03,P04

# 5) 結果
# eval/phase_d/out/<timestamp>/report.md
# eval/phase_d/out/<timestamp>/<id>_critique.txt
# eval/phase_d/out/<timestamp>/<id>_card.png
```

`report.md` の人手欄（`[ ] PASS / [ ] FAIL`）を埋め、合否を確定する。

---

## 不合格時の戻し方

1. 自動 FAIL（軸名・禁止語）→ プロンプト／パーサーを修正（Phase B/C）  
2. 人手 FAIL（口調・仮説性）→ `critique_lens` / `critique_prompts` のスタンス文言を微修正し、同じ写真で再評価  
3. モデル能力不足が疑われる場合のみ v2（gpt-4o）を検討 — v1 ではプロンプト調整を優先
