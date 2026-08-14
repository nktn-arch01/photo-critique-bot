# Photo AI Critique - システム設計仕様書 & 統合開発ルール (Architecture & ADR)

---

## PART 1: システム設計仕様書 (System Architecture)

### 1. ハイブリッド・システム構造
本システムは、**ローカル環境（デスクトップGUIバッチ処理 / CLIバッチ）** と **クラウド環境（LINE Bot Web サーバー）** が、中央の **「共通コアモジュール（テキスト解析・カード生成・スキャナー）」** を共有するハイブリッド・マルチAI構造で設計されています。

処理の目的に応じて最適化された異なるAIプロバイダを採用しています。
- **デスクトップ版**: OpenAI `gpt-4o-mini`（従量払い / 待機時間なしの一括バッチ）
- **LINE Bot版（ユーザー設定で切替）**:
  - **簡易版 (`compact`)**: OpenAI `gpt-4o-mini` — Phase 1 のみ
  - **詳細版 (`full`)**: OpenAI `gpt-4o-mini` — Phase 1 ➔ Phase 2
  - （Gemini Free Tier はプロジェクト側で `limit: 0` の 429 となり本番 LINE では使用しない。`ai_vision.py` に実装は残し、課金有効化後に `LINE_COMPACT_PROVIDER=gemini` で試験可能）

```text
[デスクトップ版 (app_gui.py / analyze_folder.py)]
  ├── AIプロバイダ: OpenAI API (gpt-4o-mini / 後払い従量課金)
  ├── 1. メタデータ抽出 (scanner.py / extract_file_metadata) ➔ 撮影 EXIF ＋ **JPEG Rating/Description（§0 正）** ＋ `.dop` は空欄時のみフォールバック
  ├── 2. コア生成エンジン (critique_engine.py) ➔ 2段階分離生成 (mode="full")
  │      ├── Phase 1: 時間帯非依存で評価・カード項目 (TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY) 確定
  │      └── Phase 2: 時間帯ファクト保持＋光・陰影具象描写による長文講評本文 (【1】〜【7】) 生成
  ├── 3. 共通テキスト解析 (critique_parser.py) ➔ 構造化データの統一抽出
  ├── 4. 共通コア (generate_critique_card.py) ➔ 1080x1350px カード画像描画
  └── 5. DesktopLogManager (log_manager.py)
         ├── 個別 Markdown ノート (.md) 出力
         ├── 月間テキストログ (.txt) 追記
         ├── 年間統合テキストログ (.txt) 追記
         └── 処理ステータス (.txt) [PROCESSED] 記録

[LINE Bot版 (main.py / Render)]
  ├── 講評生成: critique_engine.generate_critique_for_line(mode) — 簡易・詳細とも OpenAI
  │      ├── compact（簡易版）➔ OpenAI / Phase 1 のみ
  │      └── full（詳細版）➔ OpenAI / Phase 1 ➔ Phase 2
  ├── 1. LINE Webhook 受信 ➔ BackgroundTasks (非同期処理)
  ├── 2. メタデータ抽出 (scanner.py / extract_file_metadata) ➔ EXIF/時間帯情報の取得
  ├── 3. 共通テキスト解析 (critique_parser.py) ➔ 表記揺れを100%吸収して解析
  ├── 4. 共通コア (generate_critique_card.py) ➔ カード画像描画（`card_theme`: `dark` / `light`）
  ├── 5. SupabaseManager (supabase_client.py)
  │      ├── Storage (critique-cards) へ PNG アップロード ➔ Public URL 取得
  │      └── DB (critique_logs / user_settings) へ ログ保存 & カード背景 (`dark`/`light`) 取得
  ├── 6. line_messaging.py ➔ Wave C: カード即時 push のあと対話【1】【2】【3】を3通（1リクエスト最大5通）
  ├── 7. LINE Messaging API ➔ 画像カード + テキスト Push 送信
  └── 8. テキスト「背景」➔ QuickReply でライト/ダーク選択 ➔ `user_settings.card_theme` 保存

[外部監視 (UptimeRobot)]
  └── 5分おき GET /health ➔ Render 無料枠サーバーのスリープ回避
```

---

### 2. 環境変数 & 認証キー設計 (Environment Variables)

| 実行環境 | 変数名 | 必須度 | 説明 |
| :--- | :--- | :--- | :--- |
| **デスクトップ (ローカル)** | `OPENAI_API_KEY` | 必須 | `~/.zshrc` または `~/.openai_api_key` から取得。`gpt-4o-mini` の呼び出しに使用。 |
| **LINE Bot (Render)** | `OPENAI_API_KEY` | 必須 | 簡易版・詳細版とも OpenAI 講評生成に使用。 |
| **LINE Bot (Render)** | `GEMINI_API_KEY` | 任意 | `LINE_COMPACT_PROVIDER=gemini` 時のみ。通常は未使用。 |
| **LINE Bot (Render)** | `GEMINI_MODEL` | 任意 | 上記 Gemini 試験時のモデル名。 |
| **LINE Bot (Render)** | `SUPABASE_URL` | 必須 | Supabase プロジェクトの接続 URL。 |
| **LINE Bot (Render)** | `SUPABASE_SERVICE_ROLE_KEY` | 必須 | Supabase の管理者権限キー（RLS非依存で安全にログ記録）。 |
| **LINE Bot (Render)** | `LINE_CHANNEL_SECRET` | 必須 | LINE Messaging API チャンネルシークレット。 |
| **LINE Bot (Render)** | `LINE_CHANNEL_ACCESS_TOKEN` | 必須 | LINE Messaging API アクセストークン。 |

---

### 3. ファイル役割定義 (コンポーネント構成)

#### ① 共通コアモジュール (Shared Core)
- `critique_lens.py`: **【対話レンズ定義】** `self`（本人対話 / Lumina Notes）の system ロール・スコア軸（内部キー＋表示名＋AI用深層基準）の単一ソース。`mode`（compact/full）とは直交。将来 `audience` 等を追加可能。免責文は空（カード非表示）。
- `critique_parser.py`: **【中央テキスト解析エンジン】** AIが出力するテキスト（Phase 1 / Phase 2）をパースし、全角記号や記号揺れ（`##`、`■`、`：`、`（）`、`／`）を100%吸収して統一辞書データへ変換する単一責任モジュール。スコアは旧ラベル互換のうえ正規化表示名へ揃える。
- `critique_prompts.py`: Phase 1 / Phase 2 プロンプトの**単一ソース**（OpenAI・Gemini 共通。出力フォーマットは `critique_parser` と整合。レンズ固有スタンスは `critique_lens` から注入）。
- `ai_vision.py`: Vision API アダプタ層。`openai` / `gemini` を環境変数・モデル名で差し替え可能。`system_prompt` で伴走者ロールを渡す。
- `critique_engine.py`: 2段階分離生成のオーケストレーション。デスクトップは `generate_critique_openai`、LINE は `generate_critique_for_line`（本番は compact/full とも OpenAI）。`lens` 引数（既定 `self`）。`phase1_override` で JPEG 埋め込み Phase1 を注入可。
- `card_theme.py`: カード背景テーマ（`dark` / `light`）の識別子・パレット・正規化の**単一ソース**。
- `generate_critique_card.py`: Pillow による 1080×1350px 講評カード画像生成。`critique_parser` からデータを受け取り描画。`theme` 引数でライト/ダーク切替。Desktop / LINE 共通。全周 50px 余白。読み順は写真 → TITLE → SUMMARY → CRITIQUE_SUMMARY（全幅・主役の言葉）→ SCORES（小さく二次、右下ロゴ帯）。写真領域は文字帯を除いて最大化（縦横比維持）。カード上のスコアは★のみ（`(n/5)` は出さない。ログは星＋数字）。免責文は出さない。
- `scanner.py`: **【中央メタデータ解析エンジン】** 撮影 EXIF（exiftool→PIL）と講評用メタの単一入口。**Rating / user_intent は JPEG 正**（`iptc_rating_io`）。`.dop` は空欄時フォールバックのみ（正規表現＋Lua）。
- `fonts/Noto_Sans_JP/static/NotoSansJP-Regular.ttf`: カード描画用確定日本語バイナリフォント (5.5MB)。
- `docs/PHASE_A_CHECKLIST.md`: Lumina Notes 感性対話刷新の Phase A ゲート（v1 / v1.1 / 将来）。
- `docs/LUMINA_NOTES_SERVICE_CONCEPT.md`: **【将来サービス構想・E1】** 二速度（速い輪＝当日〜習慣の対話／深い輪＝週・イベントの振り返りと章）。最初に届ける類型はミラーレス派。機能仕様・実装詳細は含まない。
- `docs/R1_DEEP_LOOP_SPEC.md`: **【R1′ 深い輪 機能仕様】** 第一波 R1′-A は JPEG への IPTC Rating／説明書き込みバッチが中心。人の確認と Works 書き出しは DxO 等。メタ一次ソースは JPEG（同期成立時は dop/xmp 不使用）。
- `docs/IPTC_SYNC_VERIFICATION.md`: JPEG Rating/Description 検証。**ファイル側＋DxO／プレビュー一方向＋双方向 PASS（2026-08-11）。§0 運用確定。**
- `docs/R1A_IMPLEMENTATION_BREAKDOWN.md`: R1′-A 実装タスク分解（T0–T10）。**T0–T10 完了**。
- `docs/CURRENT_APP_MAP.md`: **【いまの全体図】** Wave A/B/C 後の入口・2タブ・JPEG Phase1・LINE／Desktop 契約の地図。
- `docs/R1A_REMAINING_TODO.md`: **【やり残し ToDo】** ストレス低減／Lumina Notes UX／AI 質の未着手・延期項目。
- `docs/R1A_DESKTOP_WALKTHROUGH_BACKLOG.md`: **【検討課題】** デスクトップ・ウォークスルー（コンセプト緊張・UX・潜在バグ）。P1/M1–M5/L1–L5 対応済み。UX Wave A 計画は `docs/R1A_UX_IMPROVEMENT_PLAN.md`。
- `docs/R1A_UX_IMPROVEMENT_PLAN.md`: **【UX 改善計画】** 再レビュー後の Wave A/B/C（ストレス低減・Lumina Notes 語彙・AI 質）。
- `docs/R1A_MAC_MANUAL_CHECKLIST.md`: **【Mac 手動確認】** オーナー向け GUI／実フォルダ手順（PASS/FAIL 記入）。
- `docs/R1A_NAMING_CLEANUP.md`: **【命名整理】** 旧 shortlist／trace／評価カード等の棚卸しと段階改修案。
- `docs/R1A_DESKTOP_OPS_POLICY.md`: **【運用方針・確定】** オリジナル `XX` 機種接頭辞、Works 月 `YYYYMM` のみ・手動、コピーなし、Lumina Review ログ配置、記録 UI。
- `iptc_rating_io.py`: **【スクリーニングメタ単一ソース】** JPEG 内 Rating / Description の読み書き（exiftool）。`RatingPercent` のみでも復元。`[M2]`/`[M3]` ブロック置換。Wave C: Phase1（`TITLE`/`SUMMARY`/`SCORES`/`CRITIQUE_SUMMARY`）も Description にブロック置換。`.dop`/`.xmp` 非依存。公式 API: `ScreeningMeta` / `read_screening_meta` / `write_screening_decision` / `upsert_phase1_blocks`（旧 `Shortlist*` は alias）。
- `phase1_jpeg.py`: Phase1 講評テキスト ↔ JPEG Description の橋渡し（スクリーニングカード・Lumina Review 共用）。
- `screening_cards.py`: スクリーニング単位の Rating 3/4 向け Compact カード生成＋ Phase1 IPTC 書込。
- `line_messaging.py`: Wave C 以降、LINE 対話は ## 【1./【2./【3. で3通分割（カードは別途 Image）。旧4分割は legacy フォールバック。
- `library_unit.py`: **【ライブラリ単位】** 月 `YYYYMM|XXYYYYMM` / イベント `YYYYMMDD_名前|XXYYYYMMDD_名前`。Works は `YYYYMM` のみ。規則外サブフォルダはイベントにしない。`is_screening_jpeg`（旧 `is_shortlist_jpeg` は alias）。
- `shortlist_mechanical.py` / `screening_mechanical.py`: **【M1 機械選別】** ブレ／露出の足切り＋低速SS・開放・意図的アンダーの意図保護。Rating 0/1。閾値は `MechanicalConfig`。（`screening_*` は Wave 3 再エクスポート）
- `shortlist_antenna.py` / `screening_antenna.py`: **【M2 アンテナ】** 5軸軽量 Vision＋バッチ内相対熱量。合格 Rating=2＋`[M2]`。★絶対ゲート禁止。
- `shortlist_diversity.py` / `screening_diversity.py`: **【M3 多様性】** 品質×多様性の貪欲選抜。余白 Rating=3／上位=4＋`[M3]`。タグ語彙・執着ブーストは設定化。
- `shortlist_pipeline.py` / `screening_pipeline.py`: **【スクリーニングパイプライン】** M1→M2→M3 オーケストレーション。`ScreeningPipeline`（旧 `ShortlistPipeline` は alias）。講評バッチとは別導線。
- `delta_log.py`: **【監査ログ】** `{unit}/_lumina/sessions/{id}.json`。`pre_h3` / `post_h3` / `h3_delta`（DxO前後・判定改善）。schema `lumina.shortlist_session.v1` 維持。
- `desktop_config.py`: **【共有設定】** `~/.photo_ai_config.json` の merge 読書き。`card_theme` / `force_overwrite` は講評／Lumina Reviewで共有。
- `desktop_ui.py`: **【UI安全予約】** ウィンドウ破棄後の `after` を握りつぶす（スクリーニング／講評 GUI 共通）。
- `prepare_mac_manual_fixtures.py`: Mac 手動確認用の最小フォルダ／JPEG を Desktop に生成。
- `shortlist_gui.py` / `console_gui.py`: **【Lumina Notes Console】** スクリーニング + Lumina Review の統合 GUI（タブ分離。Review は単独実行可）。講評 `app_gui` とは別。公式起動は `console_gui.py`。
- `LuminaNotesConsole.command`: **Lumina Notes Console** のダブルクリック起動（公式ランチャー・日常の本番）。
- `run_screening.py`: スクリーニング CLI（公式）。
- `lumina_review.py`: **【Works Lumina Review】** `{stem}_dev.jpg` 優先／撮って出しフォールバック。`LuminaReviewRunner` / `list_works_review_targets`。コピーなし。
- `trace_from_works.py`: 旧モジュール名の互換再エクスポート。
- `run_lumina_review.py`: Works Lumina Review CLI（公式）。
- `scripts/iptc_sync_verify.py`: `iptc_rating_io` を使う Rating/Description ラウンドトリップ検証。

#### ② デスクトップ版コンポーネント (Desktop Environment)
- `app_gui.py`: **レガシー**一括講評 GUI。OpenAI API。選択フォルダ・カード背景テーマの自動記憶（`~/.photo_ai_config.json`）。日常運用は Console。
- `analyze_folder.py`: 月別フォルダを一括処理するCLIバッチスクリプト。
- `log_manager.py`: `DesktopLogManager` クラス。ローカルファイル群（Markdown, txt）への構造化出力。Wave 2 以降の公式名は `{ym}Luminaノート/カード/ログ`（旧「写真分析*」「評価カード」は読込フォールバック）。
- `PhotoAICritique.command`: レガシー講評バッチのダブルクリック起動（起動時に Console へ誘導。Gatekeeper属性の自動解除機能付き）。
- `fix_dop_names.py`: DxO PhotoLab 用 `.dop` サイドカーファイル名補正ツール。

#### ③ LINE Bot クラウドコンポーネント (Cloud / Render Environment)
- `main.py`: FastAPI Web サーバー。LINE Webhook ハンドリング、BackgroundTasks、`/health`。カード＋対話【1〜3】のあと反応 Quick Reply。
- `line_reactions.py`: LINE 反応ラベル（いいね／もう少し／いまいち）↔ `good`/`mixed`/`weak`。
- `prompt_contracts.py`: **【プロンプト契約】** 審判語禁止・時間帯禁止・人物分岐のオフライン回帰正本（P2-1 Q2/Q3）。
- `scripts/summarize_h3_deltas.py` / `scripts/summarize_user_reactions.py`: H3 差分・LINE 反応の集計（Q5。自動書き換えなし）。手順は `docs/P2_1_PROMPT_IMPROVEMENT_LOOP.md`。
- `docs/P2_2_PUBLIC_UX_CHARTER.md`: **【公開 UX 憲章】** ブランドブック準拠の体験合意（Guided／Console／LINE、ローカル Web）。`docs/brand/LuminaNotes_BrandBook_02.pdf`。
- `docs/P2_2_PHASE2_CARD.md`: **【P2-2 Phase 2】** カード読み順（言葉が先・★二次）と CRITIQUE_SUMMARY の2拍。
- `supabase_client.py`: Supabase DB (`user_settings`, `critique_logs`) および Storage (`critique-cards`)。`card_theme` と `critique_logs.user_reaction` を永続化。列追加 SQL: `supabase/add_card_theme.sql` / `supabase/add_user_reaction.sql`。
- `retention_purge.py`: **30 日超**の `critique_logs` 行と `critique-cards` オブジェクトを削除。GitHub Actions `Monthly retention purge` で毎月実行（Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`）。

---

## PART 2: 開発・運用フローと統合トラブル回避教訓集 (ADR / Lessons Learned)

### 開発・運用スタイル規定
- **開発・テスト時**: ターミナルからのコピペ一発実行（CLIテストや単体テストスクリプト）で動作確認を行う。
- **push 前（任意・推奨）**: API キー不要の `python3 test_offline_suite.py`（パーサー・処理済み判定・LINE 対話3分割・カード生成レイアウト）。GitHub Actions `Offline tests` ワークフローが同内容を main で自動実行。カード見た目を変える変更では、同スイートのカード自動チェック（サイズ 1080×1350・破損なし・主要文字/写真の描画）を必ず更新・通過させる（規則1レビュー3）。
- **本番の手動確認**: デスクトップ GUI または LINE で代表1枚（簡易/詳細）— OpenAI 実呼び出しは CI では行わない。
- **本番運用時（Desktop）**: `LuminaNotesConsole.command` をダブルクリックし、スクリーニング／Lumina Review を実行する。旧一括講評は `PhotoAICritique.command`（レガシー）。

---

### 設計・開発ルール (13箇条)

### 規則 1: 根本対策と「3段階レビュー」原則（発展性・保守性・一貫性の担保）
- 障害修正や仕様変更において、単なる条件分岐の増設や局所的なフラグ対応といった**「場当たり的な対策（対症療法）」は厳禁**とする。
- すべての対策案は以下の**「3段階レビュー」**の視点を通過させ、長期的なコード品質と運用堅牢性を担保すること。
  1. **レビュー 1（根本原因と構造改革）**: 発生現象の「対症療法」を削ぎ落とし、問題の根本原因を深掘りする。「不正な状態そのものを表現・許容できない構造」へ変更する。
  2. **レビュー 2（全体一貫性と共通化）**: 特定箇所のみの例外処理にせず、既存システム全体の設計思想・命名規則に沿った汎用的な共通モジュールやミドルウェアに抽象化する。
  3. **レビュー 3（発展性と自動テスト）**: 将来の機能拡張に耐えうるよう設定とロジックを分離し、再発（リグレッション）を自動で防ぐテストケースをセットで構築する。
  
### 規則 2: マルチAI環境の通信・引数完全性
- デスクトップ版（OpenAI）とクラウド版（Gemini）で利用するAIサービスが異なっても、共通パーサー（`critique_parser.py`）やカード生成（`generate_critique_card.py`）へ渡す辞書データ構造は完全に一致させること。
- **プロバイダ選定方針**: デスクトップ・LINE（簡易/詳細）とも本番は **OpenAI**。Gemini Free Tier は Google 側クォータ（429 / limit:0）のため LINE では呼ばない。将来課金後に `LINE_COMPACT_PROVIDER=gemini` で試験可能。方針変更は `generate_critique_for_line()`。

### 規則 3: 2段階分離生成（2フェーズアーキテクチャ）によるスコア動的化と品質担保
- 長文講評（`mode="full"`）を生成する際は、**「Phase 1: 評価・カード用4項目（TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY）の確定」** と **「Phase 2: 確定結果を注入した長文本文（【1】〜【7】）の生成」** の2段階に通信を分離すること。

### 規則 4: モード別プロンプト分岐と識別子の統一 (`compact` / `full`)
- 簡易版呼び出し時は `mode="compact"` を使用し、Phase 1 完了時点で即座にレスポンスを返すこと。LINE Bot設定、Supabase DB、共通コア間でモード識別子に `"simple"` 等の不統一な文字列を使用しないこと。

### 規則 4a: 対話レンズ識別子 (`lens`) — `mode` との直交
- **`mode`**: 生成の深さ（`compact` / `full`）。**`lens`**: 対話の型（v1 は `self`＝本人の写真との対話 / Lumina Notes）。両者を混ぜない。
- レンズ定義（system ロール・スコア軸）は `critique_lens.py` を単一ソースとする。プロンプト本文の共通フォーマットは `critique_prompts.py`、スタンスはレンズから注入。
- スコア軸は内部キー（`framing` / `sensitivity` / `story` / `technical` / `sense`）を固定する。**表示名**（カード・SCORES 出力・日英併記）と **深層基準**（AI のみ・観測対象＋★1/3/5アンカー・ユーザー非提示）を分離する。
- v1 表示名: `眼差の輪郭 (Contours of the Eyes)` / `感情の陰影 (Nuances of Emotion)` / `物語の気配 (Signs of the Story)` / `表現の意図 (Intent of Expression)` / `感性の兆し (Signs of Sensibility)`。
- ★は深層基準アンカーへの当てはめ（観測可能な証拠のみ、迷ったら低め）。カードに免責文は出さない。カードのスコア行は★のみ描画し、`(n/5)` は Desktop / テキストログ側に残す。旧表示名はパーサー別名で受理し正規化する。

- 将来: `audience`（第三者・展示／コンテスト）や企画文から軸を自動設計する `rubric_source=brief_generated` を追加しうる。製品形態（別アプリ vs モード切替）は未決定。詳細は `docs/PHASE_A_CHECKLIST.md`。

### 規則 4b: カード背景テーマ識別子の統一 (`dark` / `light`)
- カード背景は `card_theme.py` の `dark` / `light` のみを用いる（日本語ラベル「ダーク」「ライト」は表示・LINE文言用。永続化・API引数は英小文字識別子）。
- デスクトップは GUI で実行前選択し `~/.photo_ai_config.json` の `card_theme` に保存。LINE は「背景」送信 → QuickReply → `user_settings.card_theme` に保存。描画は必ず `create_critique_card(..., theme=)` 経由。

### 規則 5: 時間帯ラベル依存の脱却と「光・陰影具象描写」プロンプト原則
- **撮影時刻の単一ソース**: `scanner.py` は EXIF **`DateTimeOriginal`（なければ SubSecDateTimeOriginal）のみ**を撮影時刻とする。`CreateDate` / `ModifyDate` / `FileModifyDate` は現像・書き出し時刻になり得るため採用しない（欠損時は `不明`）。
- **`time_zone_fact` の語彙**: 時計帯の中立ヒント（例: `04-07時帯（…）`）のみ。ラベル自体に「朝日」「夕景」「夜景」「黄昏」「早朝」「夜間」等の禁止語を含めない（プロンプトへ禁止語を注入して自己矛盾させない）。
- **Phase 1（カード用要素）**: 時間帯の先入観を防ぐため日時・時計帯をプロンプトに与えず、時間帯単語の使用を【一切厳禁】とする。暗い画面でも「夜」「夕」と推測して書かせない。
- **Phase 2（長文本文）**: 撮影日時と時計帯ヒントは提示するが、画面の印象でヒントを上書きするラベル貼りを禁じ、「光の照射角度」「明暗のコントラスト」「色彩グラデーション」「シャドウの深度」など具体性のある光の表現へ変換させること。

### 規則 6: ハッシュタグ用機材名スペースのアンダースコア自動置換
- 機材文字列をハッシュタグへ埋め込む際は、Python側で事前にスペースをアンダースコア（`_`）へ自動変換すること（例: `OM_14-150mm`）。

### 規則 7: テキスト解析の一元化原則 (DRY原則)
- AI出力テキストのパース処理（見出し、スコア、要約、本文の抽出）はすべて `critique_parser.py` の `parse_critique_text()` を経由すること。各ファイルで個別に `re.search` を記述しないこと。

### 規則 8: メタデータ抽出の一元化原則 (DRY原則) と JPEG 正
- 写真ファイルからのメタ抽出は、すべて `scanner.py` の `extract_file_metadata()` を経由すること。`metadata_extractor.py` は後方互換ラッパのみ（新規コードから呼ばない）。
- **Rating / Description（user_intent）は JPEG 内を一次ソース**とする（`iptc_rating_io.read_screening_meta`）。§0 同期 PASS 後、`.dop` / `.xmp` は講評必須経路に使わない。
- `.dop` は JPEG 側が空のときの**フォールバックのみ**（レガシー資産）。抽出実装は正規表現優先＋ `LuaTableParser` 補完を維持する。
- 講評プロンプト注入（`CritiquePromptContext`）は `metadata`（JPEG 正）を優先し、`dop_info` は補助とする。

### 規則 9: GUIコンソールの操作安全性・一括処理堅牢性・設定永続化
- デスクトップGUI（`app_gui.py`）は、選択フォルダの自動記憶（`~/.photo_ai_config.json`）、確認ダイアログ、リアルタイムログ表示、中断制御を保持すること。一括処理ループ内の1枚でエラーが発生しても全体を停止させず、次の画像処理へ継続させる独立 `try...except` 構造にすること。

### 規則 10: 同期・非同期処理の厳格分離 (LINE Webhook)
- LINEの Webhook 内で重いタスクを行う際は、必ず FastAPI の `BackgroundTasks` を使用し、一括送信は `push_message` で行うこと。
- 画像受信時は Webhook 処理内で `reply_message` により **解析中の即時返信** を行い、完了通知（カード・講評）は `push_message` で送ること（`reply_token` の失効対策）。

### 規則 11: サーバー（Render Free Tier）のスリープ防止
- `/health` エンドポイントを設け、外部監視（UptimeRobot等）から 5分間隔で GET アクセスを送信させること。

### 規則 12: メタデータ抽出の二重フォールバック構造
- 撮影 EXIF 解析時は `scanner.py` 内で **`exiftool -json -n` を第一候補**とし、未インストールまたは失敗時は **PIL（`_getexif`）** へフォールバックすること。Rating/Description は規則8（JPEG 正）。`.dop` フォールバックは規則8。

### 規則 13: DBキー名および権限管理の安定性維持
- Supabase 接続時の環境変数には `SUPABASE_SERVICE_ROLE_KEY` を優先使用し、バックエンドからの書き込み権限エラー（RLSブロック）を防止すること。既存のコードベースと環境変数の命名互換性を損なわない設計を維持すること。

---

## PART 3: プライバシー & セキュリティ（概要）

詳細・チェックリストは **`PRIVACY_AND_SECURITY.md`** を参照。

- LINE user ID・講評・カードは Supabase（DB / Storage）に保存される。Storage が Public の場合、URL を知る第三者も画像を閲覧し得る。
- コード側: ログの ID マスク、`privacy_utils.py`、Storage パスのハッシュ化、任意で DB 全文保存オフ / 署名付き URL。
- 運用側: バケット Private 化、キー管理、**月次保持削除**（`retention_purge.py` / GitHub Actions）、`supabase/security_recommendations.sql`。