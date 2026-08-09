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
