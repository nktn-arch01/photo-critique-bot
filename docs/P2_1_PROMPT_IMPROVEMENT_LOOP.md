# P2-1: プロンプト改善ループ（Q2 / Q3 / Q5）

更新日: 2026-08-13  
対象: モデル変更やプロンプト調整のときに回す、**オフライン中心**の手順。

---

## 一文で

**契約テストで審判語・時間帯・人物分岐の再発を防ぎ**、H3 差分と LINE 反応の集計を見て、**人手で**プロンプトを直す。

自動でプロンプトを書き換えません。

---

## Q2 — 審判語の回帰

| もの | 場所 |
|------|------|
| 契約の正本 | [`prompt_contracts.py`](../prompt_contracts.py) |
| オフラインテスト | `test_offline_suite.py` の `test_prompt_contracts_*` |

変更したら必ず:

```bash
python3 test_offline_suite.py
```

---

## Q3 — Phase D 残課題の再発防止

| もの | 場所 |
|------|------|
| テキスト fixture（画像不要） | [`eval/phase_d/fixtures/`](../eval/phase_d/fixtures/) |
| 実 API 評価（任意） | [`scripts/phase_d_eval.py`](../scripts/phase_d_eval.py) + ローカル JPEG |

普段は offline suite だけで十分です。モデルを上げたときだけ:

1. `eval/phase_d/images/` に P01–P04 を置く  
2. `python3 scripts/phase_d_eval.py --mode both --required-only`  
3. [`PHASE_D_FINDINGS.md`](PHASE_D_FINDINGS.md) の合格条件で人手確認  

---

## Q5 — 改善材料の集計

### A. Desktop H3（人が直した Rating）

スクリーニング後、DxO で直して Console を閉じると `_lumina/sessions/*.json` に `h3_delta` が残ります。

```bash
python3 scripts/summarize_h3_deltas.py --dir ~/OM2026/OM202606
# または
python3 scripts/summarize_h3_deltas.py --sessions eval/fixtures_q5/sample_session_with_h3.json --md
```

見るポイント: `2->4` や `0->2` など**多い遷移**。M2/M3 の説明や閾値の見直し候補。

### B. LINE 反応（いいね／もう少し／いまいち）

1. Supabase → **`critique_events`** を JSON または CSV で書き出し（`user_reaction`, `title`, `critique_summary` があれば十分。LINE user ID は無い）  
2. 実行:

```bash
python3 scripts/summarize_user_reactions.py --input ~/Downloads/critique_events.json --md
```

見るポイント: `weak` / `mixed` の TITLE・CRITIQUE_SUMMARY の傾向。

---

## ループの回し方（推奨）

1. 集計を見る（H3 / 反応）  
2. 直したい指示を `critique_prompts.py` / `critique_lens.py` に反映  
3. `prompt_contracts.py` の禁止／必須語を必要なら更新  
4. `python3 test_offline_suite.py`  
5. （任意）Phase D 実 API  

---

## Mac 確認（コピペ）

```bash
cd /path/to/photo-critique-bot
git checkout main
git pull origin main
python3 test_offline_suite.py
python3 scripts/summarize_h3_deltas.py --sessions eval/fixtures_q5/sample_session_with_h3.json
python3 scripts/summarize_user_reactions.py --input eval/fixtures_q5/sample_reactions.json
```

すべてエラーなく表が出れば OK です。
