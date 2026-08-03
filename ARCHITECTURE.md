# Photo AI Critique - システム設計仕様書 & 統合開発ルール (Architecture & ADR)

---

## PART 1: システム設計仕様書 (System Architecture)

### 1. ハイブリッド・システム構造
本システムは、**ローカル環境（デスクトップGUIバッチ処理 / CLIバッチ）** と **クラウド環境（LINE Bot Web サーバー）** が、中央の **「共通コアモジュール（AIエンジン・テキスト解析・カード生成・スキャナー）」** を共有するハイブリッド構造で設計されています。

[デスクトップ版 (app_gui.py / analyze_folder.py)]
  ├── 1. メタデータ抽出 (scanner.py / extract_file_metadata) ➔ EXIF + .dop(LuaTableParser)
  ├── 2. 共通コア (critique_engine.py) ➔ 2段階分離生成 (mode="full")
  │      ├── Phase 1: 評価・カード項目 (TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY) 確定
  │      └── Phase 2: 長文講評本文 (【1】〜【7】) ＋ 動的ハッシュタグ生成
  ├── 3. 共通テキスト解析 (critique_parser.py) ➔ 構造化データの統一抽出
  ├── 4. 共通コア (generate_critique_card.py) ➔ 1080x1350px カード画像描画
  └── 5. DesktopLogManager (log_manager.py)
         ├── 個別 Markdown ノート (.md) 出力
         ├── 月間テキストログ (.txt) 追記
         ├── 年間統合テキストログ (.txt) 追記
         └── 処理ステータス (.txt) [PROCESSED] 記録

[LINE Bot版 (main.py / Render)]
  ├── 1. LINE Webhook 受信 ➔ BackgroundTasks (非同期処理)
  ├── 2. メタデータ抽出 (scanner.py / extract_file_metadata) ➔ EXIF/時間帯情報の取得
  ├── 3. 共通コア (critique_engine.py) 
  │      ├── compact モード: Phase 1 のみで高速即時返信 (3〜5秒)
  │      └── full モード: Phase 1 ➔ Phase 2 の2段階生成で高品質返信 (15秒)
  ├── 4. 共通テキスト解析 (critique_parser.py) ➔ 表記揺れを100%吸収して解析
  ├── 5. 共通コア (generate_critique_card.py) ➔ カード画像描画
  ├── 6. SupabaseManager (supabase_client.py)
  │      ├── Storage (critique-cards) へ PNG アップロード ➔ Public URL 取得
  │      └── DB (critique_logs / user_settings) へ ログ保存 & モード取得 (`compact` / `full`)
  └── 7. LINE Messaging API ➔ 画像カード + テキスト Push 送信

[外部監視 (UptimeRobot)]
  └── 5分おき GET /health ➔ Render 無料枠サーバーのスリープ回避

---

### 2. ファイル役割定義 (コンポーネント構成)

#### ① 共通コアモジュール (Shared Core)
- `critique_parser.py`: **【中央テキスト解析エンジン】** AIが出力するテキスト（Phase 1 / Phase 2）をパースし、全角記号や記号揺れ（`##`、`■`、`：`、`（）`、`／`）を100%吸収して統一辞書データへ変換する単一責任モジュール。
- `critique_engine.py`: OpenAI Vision API (`gpt-4o-mini`) 呼び出し。2段階分離生成（Phase 1 ➔ Phase 2）、動的スコア評価、モード分岐 (`compact`/`full`) を担うコア。
- `generate_critique_card.py`: Pillow による 1080×1350px 講評カード画像生成。`critique_parser` からデータを受け取り描画。
- `scanner.py`: **【中央メタデータ解析エンジン】** 画像ファイル (JPG/PNG/HEIC) および DxO PhotoLab の `.dop` サイドカーファイルを高精度スキャンする共通モジュール。`extract_file_metadata()` により全環境で一元利用。
- `fonts/Noto_Sans_JP/static/NotoSansJP-Regular.ttf`: カード描画用確定日本語バイナリフォント (5.5MB)。

#### ② デスクトップ版コンポーネント (Desktop Environment)
- `app_gui.py`: Tkinter GUIコンソール。`scanner.py` の `extract_file_metadata()` を利用。前回フォルダ自動記憶、1枚ごとの独立例外処理、リアルタイムログ表示、中断制御対応。
- `analyze_folder.py`: 月別フォルダを一括処理するCLIバッチスクリプト。
- `log_manager.py`: `DesktopLogManager` クラス。`critique_parser` を使用してローカルファイル群へ構造化出力。
- `PhotoAICritique.command`: ダブルクリック起動シェルスクリプト（Gatekeeper属性の自動解除機能付き）。
- `fix_dop_names.py`: DxO PhotoLab 用 `.dop` サイドカーファイル名補正ツール。

#### ③ LINE Bot クラウドコンポーネント (Cloud / Render Environment)
- `main.py`: FastAPI Web サーバー。LINE Webhook ハンドリング、BackgroundTasks、`/health` エンドポイント。`scanner.py` でメタデータ抽出し、`critique_parser` を利用して応答作成。
- `supabase_client.py`: Supabase DB (`user_settings`, `critique_logs`) および Storage (`critique-cards`) 操作クライアント。`critique_parser` を利用してログ保存。

---

## PART 2: 開発・運用フローと統合トラブル回避教訓集 (ADR / Lessons Learned)

### 開発・運用スタイル規定
- **開発・テスト時**: ターミナルからのコピペ一発実行（CLIテストや単体テストスクリプト）で動作確認を行う。
- **本番運用時**: `PhotoAICritique.command` をダブルクリックし、GUI（`app_gui.py`）から対象フォルダを選択して実行する。

---

### 設計・開発ルール (11箇条)

### 規則 1: 共通コアモジュールのインターフェース完全性
- **ルール:** `critique_engine.py` の `generate_critique()` は、デスクトップ版から送られる高度なメタデータ（`metadata`, `dop_info`）を全受容しつつ、LINE Bot等から渡される最小限の画像データに対してもエラーなくフォールバック動作する引数設計を維持すること。

### 規則 2: 2段階分離生成（2フェーズアーキテクチャ）によるスコア動的化と品質担保
- **ルール:** 長文講評（`mode="full"`）を生成する際は、プロンプト本文を改変せず、**「Phase 1: 評価・カード用4項目（TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY）の確定」** と **「Phase 2: 確定結果を注入した長文本文（【1】〜【7】）の生成」** の2段階に通信を分離すること。

### 規則 3: モード別プロンプト分岐と識別子の統一 (`compact` / `full`)
- **ルール:** 簡易版呼び出し時は `mode="compact"` を使用し、Phase 1 完了時点で即座にレスポンスを返すこと。LINE Bot設定、Supabase DB、共通コア間でモード識別子に `"simple"` 等の不統一な文字列を使用しないこと。

### 規則 4: Phase 1 への時間帯ファクト (`time_zone_fact`) 必須注入と「夕日誤認バイアス」の防護
- **ルール:** Phase 1 のリクエストには、画像データだけでなく必ず撮影日時と時間帯分類（`time_zone_fact`）を渡すこと。また、LINE送信等で EXIF 情報が削除され時間帯が「不明」となった場合は、AIが水面の光やシルエットを見て勝手に「夕日・夕焼け・夕暮れ・夕映え・夕景・黄昏」と決めつけることを強力に禁止し、「光の質感・コントラスト・グラデーション」を描写させるプロンプト制約を自動適用すること。

### 規則 5: ハッシュタグ用機材名スペースのアンダースコア自動置換
- **ルール:** 機材文字列をハッシュタグへ埋め込む際は、Python側で事前にスペースをアンダースコア（`_`）へ自動変換すること（例: `OM_14-150mm`）。

### 規則 6: テキスト解析の一元化原則 (DRY原則)
- **ルール:** AI出力テキストのパース処理（見出し、スコア、要約、本文の抽出）はすべて `critique_parser.py` の `parse_critique_text()` を経由すること。各ファイルで個別に `re.search` を記述しないこと。

### 規則 7: メタデータ抽出の一元化原則 (DRY原則)
- **ルール:** 写真ファイルからの EXIF 情報および `.dop` サイドカーファイルの抽出処理は、すべて `scanner.py` の `extract_file_metadata()` を経由すること。`app_gui.py` や `main.py` 等で個別に独自の正規表現や抽出処理を記述しないこと。

### 規則 8: GUIコンソールの操作安全性・一括処理堅牢性・設定永続化
- **ルール:** デスクトップGUI（`app_gui.py`）は、選択フォルダの自動記憶（`.photo_ai_config.json`）、確認ダイアログ、リアルタイムログ表示、中断制御を保持すること。また、一括処理ループ内の1枚でエラーが発生しても全体を停止させず、エラーログを出力して次の画像処理へ継続させる独立 `try...except` 構造にすること。

### 規則 9: 同期・非同期処理の厳格分離 (LINE Webhook)
- **ルール:** LINEの Webhook 内で重いタスクを行う際は、必ず FastAPI の `BackgroundTasks` を使用し、一括送信は `push_message` で行うこと。

### 規則 10: サーバー（Render Free Tier）のスリープ防止
- **ルール:** `/health` エンドポイントを設け、外部監視から 5分間隔で ping アクセスを送信させること。

### 規則 11: メタデータ抽出の二重フォールバック構造
- **ルール:** メタデータ解析時は `exiftool` バイナリの実行を第一候補とし、ローカル環境に同ツールが存在しない場合は Python 内蔵の PIL 処理および `scanner.py` 内の `LuaTableParser` へ安全にフォールバックすること。