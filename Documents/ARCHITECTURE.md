# Photo AI Critique - システム設計仕様書 & 統合開発ルール (Architecture & ADR)

---

## PART 1: システム設計仕様書 (System Architecture)

### 1. ハイブリッド・システム構造
本システムは、**ローカル環境（デスクトップGUIバッチ処理 / CLIバッチ）** と **クラウド環境（LINE Bot Web サーバー）** が、中央の **「共通コアモジュール（AIエンジン・カード生成・解析スキャナー）」** を共有するハイブリッド構造で設計されています。

[デスクトップ版 (app_gui.py / analyze_folder.py)]
  ├── 1. メタデータ抽出 (scanner.py / ExifTool + PIL + 内蔵Luaパーサーによる二重構造)
  ├── 2. 共通コア (critique_engine.py) ➔ 2段階分離生成 (mode="full")
  │      ├── Phase 1: 評価・カード項目 (TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY) 確定
  │      └── Phase 2: 長文講評本文 (【1】〜【7】) ＋ 動的ハッシュタグ生成
  ├── 3. 共通コア (generate_critique_card.py) ➔ 1080x1350px カード画像描画
  └── 4. DesktopLogManager (log_manager.py)
         ├── 個別 Markdown ノート (.md) 出力
         ├── 月間テキストログ (.txt) 追記
         ├── 年間統合テキストログ (.txt) 追記
         └── 処理ステータス (.txt) [PROCESSED] 記録

[LINE Bot版 (main.py / Render)]
  ├── 1. LINE Webhook 受信 ➔ BackgroundTasks (非同期処理)
  ├── 2. 共通コア (critique_engine.py) 
  │      ├── compact モード: Phase 1 のみで高速即時返信 (3〜5秒)
  │      └── full モード: Phase 1 ➔ Phase 2 の2段階生成で高品質返信 (15秒)
  ├── 3. 共通コア (generate_critique_card.py) ➔ カード画像描画
  ├── 4. SupabaseManager (supabase_client.py)
  │      ├── Storage (critique-cards) へ PNG アップロード ➔ Public URL 取得
  │      └── DB (critique_logs / user_settings) へ ログ保存 & モード取得
  └── 5. LINE Messaging API ➔ 画像カード + テキスト Push 送信

[外部監視 (UptimeRobot)]
  └── 5分おき GET /health ➔ Render 無料枠サーバーのスリープ回避

---

### 2. ファイル役割定義 (コンポーネント構成)

#### ① 共通コアモジュール (Shared Core)
- `critique_engine.py`: OpenAI Vision API (`gpt-4o-mini`) 呼び出し。2段階分離生成（Phase 1: カード用4項目確定 ➔ Phase 2: 本文【1】〜【7】生成）、動的スコア評価、モード分岐 (`compact`/`full`) を担う核心エンジン。
- `generate_critique_card.py`: Pillow による 1080×1350px 講評カード画像生成。`re.IGNORECASE` かつ表記揺れを吸収する正規表現パース機能を搭載。
- `scanner.py`: 画像ファイル (JPG/PNG/HEIC) および DxO PhotoLab の `.dop` サイドカーファイルを高速スキャンするコアモジュール。Python単体で動作する内蔵Luaパーサー (`LuaTableParser`) と PIL EXIF解析を備える。
- `fonts/Noto_Sans_JP/static/NotoSansJP-Regular.ttf`: カード描画用確定日本語バイナリフォント (5.5MB)。

#### ② デスクトップ版コンポーネント (Desktop Environment)
- `app_gui.py`: Tkinter GUIコンソール。前回フォルダ自動記憶（`.photo_ai_config.json`）、1枚ごとの独立例外処理 (一括停止防止)、リアルタイム黒背景ログ表示、中断 (Cancel) 制御、High-DPIスケーリング対応。
- `analyze_folder.py`: 月別フォルダを一括処理するCLIバッチスクリプト。
- `log_manager.py`: `DesktopLogManager` クラス。`##` や `■` の表記揺れを吸収する正規表現パースを備え、ローカルファイル群へ構造化出力。
- `PhotoAICritique.command`: ダブルクリック起動シェルスクリプト（Gatekeeper属性の自動解除機能付き）。
- `fix_dop_names.py`: DxO PhotoLab 用 `.dop` サイドカーファイル名補正ツール。

#### ③ LINE Bot クラウドコンポーネント (Cloud / Render Environment)
- `main.py`: FastAPI Web サーバー。LINE Webhook ハンドリング、BackgroundTasks、`/health` エンドポイント、例外応方案内。
- `supabase_client.py`: Supabase DB (`user_settings`, `critique_logs`) および Storage (`critique-cards`) 操作クライアント。

---

## PART 3: 開発・運用フローと統合トラブル回避教訓集 (ADR / Lessons Learned)

### 開発・運用スタイル規定
- **開発・テスト時**: ターミナルからコピペ一発実行によるコマンドライン（CLI）テストまたは単体テストスクリプトを使用する。
- **本番運用時**: `PhotoAICritique.command` をダブルクリックし、GUI（`app_gui.py`）から対象フォルダを選択して実行する。ユーザ側でのコードや設定ファイルの直接変更は行わない。

---

### 設計・開発ルール (10箇条)

### 規則 1: 共通コアモジュールのインターフェース完全性
- **ルール:** `critique_engine.py` の `generate_critique()` は、デスクトップ版から送られる高度なメタデータ（`metadata`, `dop_info`）を全受容しつつ、LINE Bot等から渡される最小限の画像データに対してもエラーなくフォールバック動作する柔軟な引数設計を維持すること。

### 規則 2: 2段階分離生成（2フェーズアーキテクチャ）によるスコア動的化と品質担保
- **ルール:** 長文講評（`mode="full"`）を生成する際は、プロンプト本文を改変せず、**「Phase 1: 評価・カード用4項目（TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY）の確定」** と **「Phase 2: 確定結果を注入した長文本文（【1】〜【7】）の生成」** の2段階に通信を分離すること。

### 規則 3: モード別プロンプト分岐と識別子の統一 (`compact` / `full`)
- **ルール:** 簡易版呼び出し時は `mode="compact"` を使用し、Phase 1 完了時点で即座にレスポンスを返すこと。LINE Bot設定、Supabase DB、共通コア間でモード識別子に `"simple"` 等の不統一な文字列を使用しないこと。

### 規則 4: Phase 1 への時間帯ファクト (`time_zone_fact`) 必須注入原則
- **ルール:** Phase 1 のリクエストには、画像データだけでなく必ず撮影日時と時間帯分類（`早朝・黎明`、`夕方・マジックアワー` 等）を渡すこと。

### 規則 5: ハッシュタグ用機材名スペースのアンダースコア自動置換
- **ルール:** 機材文字列をハッシュタグへ埋め込む際は、Python側で事前にスペースをアンダースコア（`_`）へ自動変換すること（例: `OM_14-150mm`）。

### 規則 6: LLM出力見出しの表記揺れ受容パース原則
- **ルール:** `log_manager.py`, `generate_critique_card.py`, `main.py` のすべてのパース処理では、LLMが `■TITLE:` と出力しても `## ■TITLE:` や `TITLE:` と出力しても正しく抽出できる正規表現 `(?:##\s*)?■?\s*` および `re.IGNORECASE` を使用すること。

### 規則 7: GUIコンソールの操作安全性・一括処理堅牢性・設定永続化
- **ルール:** デスクトップGUI（`app_gui.py`）は、選択フォルダの自動記憶（`.photo_ai_config.json`）、確認ダイアログ、リアルタイムログ表示、中断制御を保持すること。また、一括処理ループ内の1枚でエラーが発生しても全体を停止させず、エラーログを出力して次の画像処理へ継続させる独立 `try...except` 構造にすること。

### 規則 8: 同期・非同期処理の厳格分離 (LINE Webhook)
- **ルール:** LINEの Webhook 内で重いタスクを行う際は、必ず FastAPI の `BackgroundTasks` を使用し、一括送信は `push_message` で行うこと。

### 規則 9: サーバー（Render Free Tier）のスリープ防止
- **ルール:** `/health` エンドポイントを設け、外部監視から 5分間隔で ping アクセスを送信させること。

### 規則 10: メタデータ抽出の二重フォールバック構造
- **ルール:** メタデータ解析時は `exiftool` バイナリの実行を第一候補とし、ローカル環境に同ツールが存在しない場合は Python 内蔵の PIL 処理および `scanner.py` 内の `LuaTableParser` へ安全にフォールバックすること。