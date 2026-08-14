# やり残し ToDo（Wave A/B/C 後）— 再レビュー確定版

更新日: 2026-08-13  
位置づけ: 初回ウォークスルー／UX 再レビュー由来のやり残しを、**オーナー再レビュー（2026-08-13）**で優先度・実装順を確定したもの。  
根拠: [`R1A_DESKTOP_WALKTHROUGH_BACKLOG.md`](R1A_DESKTOP_WALKTHROUGH_BACKLOG.md) / [`R1A_UX_IMPROVEMENT_PLAN.md`](R1A_UX_IMPROVEMENT_PLAN.md) / [`CURRENT_APP_MAP.md`](CURRENT_APP_MAP.md)

**完了済み（参考）:** Wave A/B/C。ホットフィックス H1–H3 / M1–M5 / L1–L5。**S4** LINE 統合実機 PASS（2026-08-12）。  
**P1 一式＋N2** 実装済み（2026-08-13）: S1 / S6 / S7 / U2 / S5（薄い入口 alias） / N2。  
**P2-1 基盤** 実装済み（2026-08-13）: Q2 / Q3 fixture / Q5 集計（[`P2_1_PROMPT_IMPROVEMENT_LOOP.md`](P2_1_PROMPT_IMPROVEMENT_LOOP.md)）。

**実装順の約束（専門家確認）:**

- P1 内は **上から順**（案内 → 役割一本化 → 最後に alias 削除）。`S5` を先にしない。
- **U2（P1）** はランチャー／README／起動案内の役割一本化まで。旧 `app_gui` の大規模統合は混ぜない。
- **P2-1**（モデル変更時）と **P2-2**（公開向け UI）は独立。モデル作業を UI 刷新の前提にしない。

---

## 実装順一覧（再レビュー確定）

### P1 — 完了（2026-08-13）

| ID | 内容 | 状態 |
|----|------|------|
| S1 | オリジナル → Works の置き方ガイドを常時出す（`_dev`／月フォルダ） | **DONE** — Console 両タブに固定表示 |
| S6 | スクリーニング失敗・中止時の「次の一手」一文 | **DONE** |
| S7 | フォルダ名エラーを具体例つきで早く拒否 | **DONE** — `library_unit` 共通文言 |
| U2 | Photo AI 講評と Console の役割一本化（旧 C5） | **DONE** — ランチャー／ウィンドウ案内のみ（大規模統合なし） |
| S5 | 旧名 alias 削除（薄い入口） | **DONE** — `LuminaShortlist.command` / `run_shortlist.py` / `run_trace_works.py` 削除。`shortlist_*.py` 本体の改名は後続 |

### P2-LINE — 完了（2026-08-13）

| ID | 内容 | 状態 |
|----|------|------|
| **N2** | LINE: 対話【1〜3】のあと Quick Reply 3段階（👍いいね／💭もう少し／😐いまいち）。`critique_logs.user_reaction`（good/mixed/weak） | **DONE** — 運用前に `supabase/add_user_reaction.sql` を1回実行。Q5 の材料 |

### P2-1 — AI モデル変更を検討するタイミングで（基盤 DONE 2026-08-13）

| ID | 内容 | 状態 |
|----|------|------|
| Q2 | プロンプト審判語の回帰テスト強化 | **DONE（オフライン契約）** — `prompt_contracts.py` + suite |
| Q3 | Phase D 残課題の再発防止 | **DONE（fixture）** — `eval/phase_d/fixtures/`。実 API 再評価はモデル変更時に任意 |
| Q5 | H3 差分＋LINE `user_reaction` をプロンプト改善材料にするループ | **DONE（集計）** — `scripts/summarize_*.py`。手順は [`P2_1_PROMPT_IMPROVEMENT_LOOP.md`](P2_1_PROMPT_IMPROVEMENT_LOOP.md)。自動書き換えはしない |

モデルを上げるときの作業: 上記契約を通したうえで任意で `phase_d_eval.py` を再実行。

### P2-2 — 公開向けの洗練 UI とまとめて

**体験憲章（合意済み 2026-08-13）:** [`P2_2_PUBLIC_UX_CHARTER.md`](P2_2_PUBLIC_UX_CHARTER.md)  
**ブランド正本:** [`brand/LuminaNotes_BrandBook_02.pdf`](brand/LuminaNotes_BrandBook_02.pdf)  
**シェル合意:** ローカル Web（クラウドでライブラリ正本にしない）。Guided＝顔／Console＝パワー／LINE＝友達の速い輪。

| ID | 内容 | メモ |
|----|------|------|
| **N1（新規）** | 開発 UI から公開向け洗練 UI へ（ローカル FastAPI＋ブラウザ） | 親テーマ。憲章 §3–4 |
| U4 | 表層の評価語彙を対話語彙へ | **DONE（Console）** — `console_ui_copy.py`。Guided は後続 |
| Q4 | CRITIQUE_SUMMARY を「次の撮影への問い」寄りに | **DONE（Phase 2）** — 見所＋もう一度見る／次のシャッター。N-03 定型は禁止 |
| U1 | カードで要約／問い上位・★二次（旧 C1） | **DONE（Phase 2）** — 読み順 TITLE→SUMMARY→CRITIQUE_SUMMARY→★ |
| Q1 | カード描画で ★ を下げ要約を主役に | **DONE（Phase 2）** — ★ 20px、言葉 26–28px。手順は [`P2_2_PHASE2_CARD.md`](P2_2_PHASE2_CARD.md) |
| Q7 | M2「相対熱量」をユーザー向け一言で | **DONE（Console）** — 「見返す」説明に包含 |
| S3 | ヘルプ／完了文の言い回し磨き（W5 後回し分） | **DONE（Console）** |

### P3-1

| ID | 内容 | メモ |
|----|------|------|
| S8 | HIF 等 JPEG 以外の方針を決めて文書化 | |

### P3-2

| ID | 内容 | メモ |
|----|------|------|
| Q6 | レンズ将来拡張（`audience` 等）は仕様のみ | 実装は後 |

---

## 不要（再レビューで外したもの）

| ID | 内容 | 理由（オーナー） |
|----|------|------------------|
| U3 | Rating 0–4 と DxO 星の説明強化 | JPEG＝Lumina／RAW＝ユーザー評価で分離可能 |
| S2 | 撮って出しと `_dev` の同時 Review 選択 | 通常運用はどちらか一方 |
| U5 | 速い輪（R4′）の製品設計 | DxO での Rating 修正で達成 |
| U6 | 初回がスクリーニング偏重にならない導線 | ユーザーのワークフロー次第 |
| U7 | 同意 UI を作らず H3 使い方だけ決める | 専用 UI は不要。LINE 反応は **N2** |

---

## テーマ別インデックス（参照用）

| テーマ | 残っている ID |
|--------|----------------|
| ストレス低減 | S8（S1/S5/S6/S7 完了。S2 不要／S4 完了） |
| Lumina Notes UX | N1（U1/U2/U4 完了。U3/U5/U6/U7 不要） |
| AI フィードバック質 | Q6（Q1–Q5/Q7 のオフライン基盤または Phase 2 は完了） |

---

## 意図的にやらない（従来どおり）

| 項目 | 理由 |
|------|------|
| Works への自動コピー | 運用契約 |
| 長期 Phase1 content-hash キャッシュ | JPEG Description 正本 |
| GPT ストリーム前後半分割 | βでは複雑さ勝ち |
| 強制ウィザード（①〜⑤全体） | タブ独立と矛盾 |
| デスクトップの「そう思う／違う」専用 UI | 不要（上記 U7） |

---

## 変更履歴

| 日付 | 内容 |
|------|------|
| 2026-08-12 | 初版（3分類） |
| 2026-08-12 | S4 LINE PASS |
| 2026-08-13 | オーナー再レビュー反映: P1／P2-1／P2-2／P3・不要を確定。N1（洗練 UI）追加。実装順の約束を追記 |
| 2026-08-13 | N2 を LINE Quick Reply（対話後・3段階＋DB列）として追加 |
| 2026-08-13 | P1（S1/S6/S7/U2/S5）＋N2 実装完了を反映 |
| 2026-08-13 | P2-1: Q2/Q3/Q5 オフライン基盤（契約・fixture・集計）を完了 |
| 2026-08-13 | P2-2: 公開 UX 憲章を合意（ブランドブック 02・一文・表面・ローカル Web） |
| 2026-08-13 | P2-2 Phase 1: Console 言葉（U4/S3/Q7） |
| 2026-08-14 | P2-2 Phase 2: カード主役化（U1/Q1）＋ CRITIQUE_SUMMARY 2拍（Q4） |
