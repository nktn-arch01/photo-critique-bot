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
  ├── 1. メタデータ抽出 (scanner.py / extract_file_metadata) ➔ EXIF + .dop(正規表現優先+Luaパース補完)
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
  ├── 4. 共通コア (generate_critique_card.py) ➔ カード画像描画
  ├── 5. SupabaseManager (supabase_client.py)
  │      ├── Storage (critique-cards) へ PNG アップロード ➔ Public URL 取得
  │      └── DB (critique_logs / user_settings) へ ログ保存 & モード取得 (`compact` / `full`)
  ├── 6. line_messaging.py ➔ 詳細版は ## 【1./【4./【6. 見出しで4分割して push（1リクエスト最大5通）
  └── 7. LINE Messaging API ➔ 画像カード + テキスト Push 送信

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
- `critique_parser.py`: **【中央テキスト解析エンジン】** AIが出力するテキスト（Phase 1 / Phase 2）をパースし、全角記号や記号揺れ（`##`、`■`、`：`、`（）`、`／`）を100%吸収して統一辞書データへ変換する単一責任モジュール。
- `critique_prompts.py`: Phase 1 / Phase 2 プロンプトの**単一ソース**（OpenAI・Gemini 共通。出力フォーマットは `critique_parser` と整合）。
- `ai_vision.py`: Vision API アダプタ層。`openai` / `gemini` を環境変数・モデル名で差し替え可能。
- `critique_engine.py`: 2段階分離生成のオーケストレーション。デスクトップは `generate_critique_openai`、LINE は `generate_critique_for_line`（compact→Gemini、full→OpenAI）。
- `line_messaging.py`: 詳細版は講評見出し（## 【1./【4./【6.）で4通に分割。push は5通/リクエスト上限で batched 送信。
- `generate_critique_card.py`: Pillow による 1080×1350px 講評カード画像生成。`critique_parser` からデータを受け取り描画。
- `scanner.py`: **【中央メタデータ解析エンジン】** 画像ファイル (JPG/PNG/HEIC) および DxO PhotoLab の `.dop` サイドカーファイルを高精度スキャンする共通モジュール。正規表現優先＋Luaパース補完の多層防御構造を採用。
- `fonts/Noto_Sans_JP/static/NotoSansJP-Regular.ttf`: カード描画用確定日本語バイナリフォント (5.5MB)。

#### ② デスクトップ版コンポーネント (Desktop Environment)
- `app_gui.py`: Tkinter GUIコンソール。OpenAI APIによる爆速処理。選択フォルダ自動記憶（`~/.photo_ai_config.json`＝ユーザーホーム直下）、独立例外処理、リアルタイムログ表示、中断制御対応。
- `analyze_folder.py`: 月別フォルダを一括処理するCLIバッチスクリプト。
- `log_manager.py`: `DesktopLogManager` クラス。ローカルファイル群（Markdown, txt）への構造化出力。
- `PhotoAICritique.command`: ダブルクリック起動シェルスクリプト（Gatekeeper属性の自動解除機能付き）。
- `fix_dop_names.py`: DxO PhotoLab 用 `.dop` サイドカーファイル名補正ツール。

#### ③ LINE Bot クラウドコンポーネント (Cloud / Render Environment)
- `main.py`: FastAPI Web サーバー。Gemini 2.0 Flash を呼び出し、LINE Webhook ハンドリング、BackgroundTasks、`/health` エンドポイントを制御。
- `supabase_client.py`: Supabase DB (`user_settings`, `critique_logs`) および Storage (`critique-cards`) 操作クライアント。環境変数 `SUPABASE_SERVICE_ROLE_KEY` を参照。

---

## PART 2: 開発・運用フローと統合トラブル回避教訓集 (ADR / Lessons Learned)

### 開発・運用スタイル規定
- **開発・テスト時**: ターミナルからのコピペ一発実行（CLIテストや単体テストスクリプト）で動作確認を行う。
- **push 前（任意・推奨）**: API キー不要の `python3 test_offline_suite.py`（パーサー・処理済み判定・LINE 4分割）。GitHub Actions `Offline tests` ワークフローが同内容を main で自動実行。
- **本番の手動確認**: デスクトップ GUI または LINE で代表1枚（簡易/詳細）— OpenAI 実呼び出しは CI では行わない。
- **本番運用時**: `PhotoAICritique.command` をダブルクリックし、GUI（`app_gui.py`）から対象フォルダを選択して実行する。

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

### 規則 5: 時間帯ラベル依存の脱却と「光・陰影具象描写」プロンプト原則
- **Phase 1（カード用要素）**: 時間帯の先入観によるAIのハルシネーションを防ぐため、プロンプトには時間帯データをあえて与えず、直接的な時間帯単語（「朝日」「夕日」「夕焼け」「夕暮れ」「夕映え」「夕景」「夜景」「黄昏」）の使用を【一切厳禁】とすること。
- **Phase 2（長文本文）**: 撮影者の背景意図を読み解くため時間帯ファクト（`time_zone_fact`）は提示するが、単語の連呼を厳禁とし、「光の照射角度」「明暗のコントラスト」「色彩グラデーション」「シャドウの深度」など具体性のある光の表現へ変換させること。

### 規則 6: ハッシュタグ用機材名スペースのアンダースコア自動置換
- 機材文字列をハッシュタグへ埋め込む際は、Python側で事前にスペースをアンダースコア（`_`）へ自動変換すること（例: `OM_14-150mm`）。

### 規則 7: テキスト解析の一元化原則 (DRY原則)
- AI出力テキストのパース処理（見出し、スコア、要約、本文の抽出）はすべて `critique_parser.py` の `parse_critique_text()` を経由すること。各ファイルで個別に `re.search` を記述しないこと。

### 規則 8: メタデータ抽出の一元化原則 (DRY原則) と多層防御解析
- 写真ファイルからの EXIF 情報および `.dop` サイドカーファイルの抽出処理は、すべて `scanner.py` の `extract_file_metadata()` を経由すること。`metadata_extractor.py` は後方互換ラッパのみ（新規コードから呼ばない）。DxO PhotoLab のバージョン更新に備え、`.dop` の抽出処理は「テキスト直読の正規表現（Regex）を最優先とし、`LuaTableParser` で二次補完する多層防御構造」を維持すること。

### 規則 9: GUIコンソールの操作安全性・一括処理堅牢性・設定永続化
- デスクトップGUI（`app_gui.py`）は、選択フォルダの自動記憶（`~/.photo_ai_config.json`）、確認ダイアログ、リアルタイムログ表示、中断制御を保持すること。一括処理ループ内の1枚でエラーが発生しても全体を停止させず、次の画像処理へ継続させる独立 `try...except` 構造にすること。

### 規則 10: 同期・非同期処理の厳格分離 (LINE Webhook)
- LINEの Webhook 内で重いタスクを行う際は、必ず FastAPI の `BackgroundTasks` を使用し、一括送信は `push_message` で行うこと。
- 画像受信時は Webhook 処理内で `reply_message` により **解析中の即時返信** を行い、完了通知（カード・講評）は `push_message` で送ること（`reply_token` の失効対策）。

### 規則 11: サーバー（Render Free Tier）のスリープ防止
- `/health` エンドポイントを設け、外部監視（UptimeRobot等）から 5分間隔で GET アクセスを送信させること。

### 規則 12: メタデータ抽出の二重フォールバック構造
- メタデータ解析時は `scanner.py` 内で **`exiftool -json -n` を第一候補**とし、未インストールまたは失敗時は **PIL（`_getexif`）** へフォールバックすること。`.dop` は正規表現優先＋ `LuaTableParser` 補完（規則8）。

### 規則 13: DBキー名および権限管理の安定性維持
- Supabase 接続時の環境変数には `SUPABASE_SERVICE_ROLE_KEY` を優先使用し、バックエンドからの書き込み権限エラー（RLSブロック）を防止すること。既存のコードベースと環境変数の命名互換性を損なわない設計を維持すること。

---

## PART 3: プライバシー & セキュリティ（概要）

詳細・チェックリストは **`PRIVACY_AND_SECURITY.md`** を参照。

- LINE user ID・講評・カードは Supabase（DB / Storage）に保存される。Storage が Public の場合、URL を知る第三者も画像を閲覧し得る。
- コード側: ログの ID マスク、`privacy_utils.py`、Storage パスのハッシュ化、任意で DB 全文保存オフ / 署名付き URL。
- 運用側: バケット Private 化、キー管理、保持期間・削除、`supabase/security_recommendations.sql`。