# Lumina Notes Console — UX 改善計画（再レビュー後）

更新日: 2026-08-12  
位置づけ: PR #9（6901909）マージ後のコード再レビューに基づく **改善計画と Wave 分割**。  
根拠: [`R1A_DESKTOP_WALKTHROUGH_BACKLOG.md`](R1A_DESKTOP_WALKTHROUGH_BACKLOG.md) §1–2 / [`R1A_DESKTOP_OPS_POLICY.md`](R1A_DESKTOP_OPS_POLICY.md) / [`LUMINA_NOTES_SERVICE_CONCEPT.md`](LUMINA_NOTES_SERVICE_CONCEPT.md) / [`ARCHITECTURE.md`](../ARCHITECTURE.md) 規則1（3段階レビュー）

関連チェックリスト: [`R1A_MAC_MANUAL_CHECKLIST.md`](R1A_MAC_MANUAL_CHECKLIST.md)

---

## 0. 再レビュー要約

### すでに効いている改修（触らない）

| 系統 | 内容 |
|------|------|
| C1/C2/C3UX | ドライラン H3 拒否、完了メッセージ分岐、Rating 凡例・月バッチ時のイベント除外警告 |
| 命名 Wave 1–3 | Console / Lumina* 出力 / screening_* / console_gui 等（旧名 alias 削除は次々回） |
| H1–H3 / M1–M5 / P1 / L1–L5 | 設定マージ、H3 安全化、Works YYYYMM ゲート、UI after 等 |

### 残る本質的な痛み（根本原因）

| 領域 | 根本原因 | 表層症状 |
|------|----------|----------|
| **ストレス** | 深い輪の手順（アプリ→DxO→アプリ→Works）が「暗黙の契約」のまま | どこまでやればよいか不安・失敗がバッチ途中で出る |
| **Lumina Notes UX** | 表層が選別／評価語彙寄りで、対話ブランドが弱い | Rating・★・長文講評が「採点アプリ」に見える |
| **AI フィードバック質** | プロンプトに「評価／採点」が残り、カードのヒーローが ★ | モデルが審判者モードに寄りやすい／ユーザーが点数を成果と誤解 |

運用契約（Works 月のみ・コピーなし・イベントは別バッチ）は **変えない**。変えるのは「見える化・事前確認・語彙・次の一手」。

---

## 1. 3段階レビュー（方針）

### レビュー1 — 根本原因と構造

- **不正な状態を始めから拒否する**: API キー無しで M2/M3・Lumina Review を開始できない（途中失敗をなくす）。
- **黙ってスキップしない**: `_dev` 優先で撮って出しを外すとき、枚数と名前を確認ダイアログ／ログに出す（§2.6）。
- **手順の必須感を UI で解く**: 終了時に「DxO修正後を記録」未実施なら任意確認（ops §5）。順序は強制しない。
- **AI は審判ではなく伴走**: 出力フォーマット（SCORES 行・JSON キー）は維持し、**指示語彙だけ**を観察／熱量／対話へ寄せる。

### レビュー2 — 一貫性・共通化

- API 事前確認は `ai_vision.get_openai_client` を単一入口（`app_gui` と同型）。
- Works 対象の要約は `lumina_review` に置き、GUI／将来 CLI が共有。
- セッション未記録判定は `delta_log.summarize_session` / `has_post_h3` を使う（独自フラグを増やさない）。
- プロンプト語彙は `critique_prompts` / `shortlist_antenna`（screening 再エクスポート経由）に閉じる。

### レビュー3 — 将来性・自動テスト

- `summarize_works_review_selection` のオフラインテスト（_dev 優先＋ SOOC スキップ列挙）。
- プロンプトに「審判語」が復活しないことの軽い契約テスト（任意フレーズ）。
- Mac 手動は既存チェックリストに Wave A 追記行のみ。

---

## 2. Wave 分割

### Wave A（本 PR・今回実装）— ストレス低減＋見える化＋語彙

| ID | 内容 | §対応 | 初心者向け文言の方針 |
|----|------|-------|----------------------|
| **A1** | Console で M2/M3 または Lumina Review 開始前に API キー事前確認 | §2.5 | 「APIキーがありません」＋置き場所だけ |
| **A2** | Works 対象要約: `_dev` / 撮って出し / `_dev` 優先で除外した撮って出し | §2.6 | 確認ダイアログに短い内訳 |
| **A3** | 終了時: 書き込み済みセッションに `post_h3` が無ければ任意確認 | §2.7 | 「後で記録しても大丈夫です」 |
| **A4** | ヘルプ／ゾーン見出し／完了文を手順番号＋対話語彙へ | §2.1, §1.4 | 短く・評価語を減らす |
| **A5** | Phase2 / M2 プロンプトの「評価・採点」→観察／熱量（ワイヤ形式は不変） | AI質 | ユーザー非表示。モデル向けのみ |
| **A6** | タブ分離（スクリーニング｜Lumina Review）＋単独実行可の文言 | §2.1 / オーナー確認 | 一本道に見せない |

**やらない（Wave A）:** イベント一括ヘルパー、SOOC も同時レビューするトグル、速い輪（R4′）、旧 alias 削除、カードレイアウトの ★ 降格、別ランチャー完全分離（案2）。

### Wave B（本 PR）— 手順のガイド化（タブ分離後）

| ID | 内容 | メモ |
|----|------|------|
| **B1** | スクリーニングタブに薄い流れ案内（強制ウィザードなし）。①〜⑤全体導線はタブ独立と矛盾するため採用しない | §2.1 適応 |
| **B2** | 月フォルダで「配下イベントも順に実行」チェック（既定OFF） | §2.2–2.3 |
| **B3** | Lumina Review 完了後に Works フォルダを開くか確認 | `desktop_ui.open_in_file_manager` |
| **B4** | Review エラー理由を完了ダイアログに要約 | `summarize_review_errors` |

### Wave B 受け入れ条件

- [x] 月＋イベントでチェック ON → 月→イベント順にログが出る — **Mac B2 PASS**
- [x] チェック OFF → 従来どおり月直下のみ — **Mac B2b PASS**
- [x] Review 完了で「Works フォルダを開きますか？」— **Mac B3 PASS**
- [x] エラーがある完了文にファイル名が出る — オフライン＋ **Mac B4 PASS**
- [x] `python3 test_offline_suite.py` PASS（2026-08-12）
- [x] `plan_screening_units` オフライン PASS
- [x] B1 薄い流れ案内 — **Mac B1 PASS**
- [x] Mac: Wave B B1–B4 / B2b すべて PASS（2026-08-12・オーナー確認）

### Wave C（製品・AI 質の中期）— カード／対話／JPEG Phase1 正

オーナー見直し（2026-08-12）後の確定方針。見た目・ランチャー統一は延期。

| ID | 内容 | 状態 |
|----|------|------|
| C0 | H3「DxO修正後を記録」を UI から削除。Console 終了時に自動記録 | 実装 |
| C1 | カード見た目（★降格等） | **延期**（β公開前） |
| C2 | LINE 案2: カード即時 → 短命 Phase1 → 対話【1〜3】追従。モード統合 | 実装 |
| C3 | スクリーニング「カード」生成（Rating 3/4）＋ Description へ Phase1 4項目 | 実装 |
| C3′ | Lumina Review: 埋め込み Phase1 再利用。ログは従来 Full【1〜7】。未埋め込みは書戻し | 実装 |
| C4 | 「そう思う／違う」UI | **不做**（DxO Rating 修正＝反応。H3 が記録） |
| C5 | Photo AI 講評と Console の一本化 | **延期** |

**チャネル契約の違い:**

- LINE 返信: カード＋【1〜3】のみ（CRITIQUE_SUMMARY テキスト通なし）
- Desktop Works 分析ログ: 従来どおり ファイル名／TITLE／SUMMARY／SCORES／CRITIQUE_SUMMARY／【1〜7】／メタデータ

**IPTC Description（Wave C 拡張）:** `TITLE:` `SUMMARY:` `SCORES:` `CRITIQUE_SUMMARY:` を `[M2]`/`[M3]` と共存（ブロック置換）。DxO 一覧・Works 移動後の正本。

---

## 3. Wave A 受け入れ条件

- [x] M2/M3 ON でキー無し → 開始前にエラー（バッチ途中で落ちない）— **Mac W1 PASS**
- [x] Lumina Review でキー無し → 同上 — **Mac W2 PASS**
- [x] `_dev` と撮って出しが両方あるフォルダで、確認文に「撮って出し除外 N」が出る — **Mac W3 PASS**＋オフラインテスト
- [x] 書き込みスクリーニング後・未記録のまま閉じると確認が出る（キャンセルで残れる）— **Mac W4 PASS**
- [x] `python3 test_offline_suite.py` PASS（2026-08-12）
- [x] Mac: Wave A W1–W6 PASS（2026-08-12・オーナー確認）。W5 文言の細かい見直しは後回し可
- [x] A6 タブ分離（スクリーニング｜Lumina Review）— **Mac W6 PASS**

---

## 4. 変更履歴

| 日付 | 内容 |
|------|------|
| 2026-08-12 | 初版。PR #9 後再レビュー。Wave A 実装対象を確定 |
| 2026-08-12 | Wave A6: タブ分離＋文言（オーナー確認: 案1+案3）。W4 PASS 記録 |
| 2026-08-12 | Mac 手動: W1–W6 すべて PASS（W5 細かい文言は後続可）。PR #10 を main へマージ |
| 2026-08-12 | Wave B 実装（B1 適応・B2–B4） |
| 2026-08-12 | Mac 手動: Wave B B1 / B2 / B2b / B3 / B4 すべて PASS |
| 2026-08-12 | 監査修正: 単位間中止の誤「完了」、イベント未記録 H3 の終了案内、ops 文書整合 |
| 2026-08-12 | Mac 監査フォロー F1/F2 PASS。Wave B 完了（PR #11 マージ） |
| 2026-08-12 | Wave C 方針確定・実装: H3 自動、スクリーニングカード＋IPTC Phase1、LINE 案2、Review Phase1 再利用 |
| 2026-08-12 | Mac Wave C: C0/C0b/C3/C3′ PASS。追記: Review カード省略・深さUI削除・.command で Terminal 終了。**C2 LINE 実機 PASS（後追い）** |
| 2026-08-12 | やり残し ToDo を [`R1A_REMAINING_TODO.md`](R1A_REMAINING_TODO.md) に3分類で切り出し |
