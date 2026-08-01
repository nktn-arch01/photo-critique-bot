# Photo AI Critique - システム設計仕様書 & 開発ルール

---

## PART 1: 設計仕様書 (System Architecture & Specifications)

### 1. システム概要 & アーキテクチャ
LINEで送信された写真をAIが分析し、高精度な「講評カード画像（1080×1350px）」と「講評テキスト（簡易版 / 詳細版）」を自動返信・Supabaseへログ保存するシステム。

[ユーザー (LINE)]
      │
      ├── 1. 写真受信 (ImageMessage) ➔ バックグラウンド非同期処理 (BackgroundTasks)
      │      ├── AI分析エンジン (critique_engine.py) ➔ モード別(compact/full)講評生成
      │      ├── カード画像生成 (generate_critique_card.py)
      │      │      └── 同梱フォント (fonts/Noto_Sans_JP/static/NotoSansJP-Regular.ttf) 描画
      │      ├── Supabase Manager (supabase_client.py)
      │      │      ├── Storage (critique-cards) へ PNG 保存 ➔ Public URL 取得
      │      │      └── DB (critique_logs / user_settings) へ ログ/設定 保存
      │      └── LINE Messaging API ➔ Pushメッセージ送信 (push_message)
      │
      ├── 2. テキスト受信 ("設定") ➔ クイックリプライ即時返信 (reply_message)
      ├── 3. スタンプ受信 (StickerMessage) ➔ 写真送信を促す案内返信
      └── 4. 動画・ファイル等受信 ➔ 非対応フォーマットのガイダンス返信

[外部監視 (UptimeRobot)]
      │ (5分おき GET /health)
      ▼
[FastAPI / Render サーバー] (Port 10000) ➔ 常時スリープ回避

### 2. 技術スタック & 監視
- Web/API: Python 3.14 / FastAPI / Uvicorn
- ホスティング: Render (Web Services Free Tier)
- 常時稼働監視: UptimeRobot (HTTP GET /health 5分間隔)
- DB / ストレージ: Supabase (PostgreSQL + Supabase Storage)
- AIエンジン: OpenAI API (gpt-4o-mini)
- 画像処理: Pillow (PIL)
- 外部連携: LINE Messaging API (line-bot-sdk)

必須環境変数:
- LINE_CHANNEL_ACCESS_TOKEN: LINE Messaging API チャネルアクセストークン
- LINE_CHANNEL_SECRET: LINE Messaging API チャネルシークレット
- SUPABASE_URL: Supabase プロジェクト URL
- SUPABASE_SERVICE_ROLE_KEY: Supabase サービスロールキー（管理者用）
- OPENAI_API_KEY: OpenAI API キー

### 3. ローカルファイル構成
/Users/t_nktn/photo_ai/
├── main.py                     # FastAPIエントリーポイント・LINE Webhook受信用
├── generate_critique_card.py   # 講評カード画像 (1080x1350) 描画モジュール
├── critique_engine.py          # AI写真分析・講評テキスト生成（簡易/詳細対応）
├── supabase_client.py          # Supabase DB/Storage操作クライアント
├── app_gui.py                  # デスクトップ版 GUI (PhotoAICritique.command用)
├── requirements.txt            # 依存ライブラリ一覧
├── ARCHITECTURE.md             # 本設計仕様書・開発ルール集
└── fonts/                      # リポジトリ同梱フォントディレクトリ
    └── Noto_Sans_JP/
        └── static/
            └── NotoSansJP-Regular.ttf  # ★メイン描画用フォント (5.5MB TrueType バイナリ)

### 4. データベース & ストレージ仕様 (Supabase)

#### 4.1 テーブル user_settings
- user_id (text, Primary Key) : LINE ユーザー ID
- mode (text) : 'simple' (簡易版) または 'full' (詳細版)
- updated_at (timestamptz) : 更新日時

#### 4.2 テーブル critique_logs
- id (int8, BigInt, Primary Key / Auto Increment)
- line_user_id (text)
- image_url (text)
- title (text) : 写真タイトル
- summary (text) : 総合要約（■SUMMARY）
- scores_json (jsonb) : 各スコア（5項目）
- critique_summary (text) : カード用キャッチコピー（■CRITIQUE_SUMMARY）
- full_critique_text (text) : 全文講評テキスト
- card_image_url (text) : 生成カード画像の Public URL
- created_at (timestamptz)

#### 4.3 Storage バケット critique-cards
- 用途: 生成されたカード画像 (PNG) を保存し、LINE 送信用の Public URL を発行する (Public 設定)。

### 5. 各データ項目の定義と出力ルール
1. TITLE: 写真タイトル ➔ カード画像上部 & LINE返信見出し
2. SUMMARY: 写真全体の総合要約 ➔ カード画像見出し下部
3. SCORES: 5項目の評価点 ➔ カード画像中央 (★記号 + 1〜5数値で写真別に動的評価)
4. CRITIQUE_SUMMARY: カード下部解説文 ➔ カード画像最下部 & 簡易版LINE返信本文

---

## PART 2: 開発ルール & トラブル回避教訓集 (ADR)

### 規則 1: リソース・バイナリ（フォントファイル）管理の決定性
- ルール: 日本語フォントは、検証済みの実体（約5.5MBの.ttf）を物理的に Git リポジトリ（fonts/）へコミット・同梱して送信すること。
- 教訓: サーバー起動時・実行時の動的ダウンロード (curl/urllib) は、ネットワーク制限やエラーページの取得によりファイルが破損し、文字化け（豆腐化）の根源となる。

### 規則 2: Supabase セキュリティ & 最小権限原則
- ルール: SUPABASE_SERVICE_ROLE_KEY を使用するバックエンド設計において、一般公開用の anon キーに全開放ポリシーを設定しないこと。service_role ロールに対してのみ全権限 (GRANT) と RLS ポリシーを付与する。
- 教訓: anon の全開放は Supabase のスキャナーにより警告メールが送信される。service_role 専用権限に集約すれば警告も停止し、書き込みも確実に成功する。

### 規則 3: LINE Messaging API の同期・非同期分離
- ルール: 
  - 重い処理（AI画像解析・カード生成）: FastAPIの BackgroundTasks へ投入し、完了後に push_message で送信。
  - 軽い処理（設定ボタン・テキスト返信）: reply_message（同期返信）を使用。
- 教訓: 同期処理で重いタスクを実行すると、LINEの reply_token がタイムアウト失効しエラーとなる。

### 規則 4: 個人情報保護とストレージクリーンアップ
- ルール: ユーザー画像および一時カード画像は、必ず tempfile.mkdtemp() 内で処理し、finally: shutil.rmtree(temp_dir, ignore_errors=True) で処理成否を問わず 100% 即時物理消去すること。

### 規則 5: プロンプトにおける固定サンプル数値のテンプレート化防止
- ルール: プロンプト内でフォーマット指定を行う際、具体例の数値（例: ★★★★☆ (4/5)）を直接埋め込まず、プレースホルダー形式（例: [写真に応じた★評価] ([1〜5の数値]/5)）と明示的な動的評価ルールを記述すること。
- 教訓: フォーマット指定文に数値例を直接書くと、LLM（特に gpt-4o-mini）がその行を不変のテンプレートと誤認識し、画像解析結果と無関係に固定スコアを出力し続けてしまう。

### 規則 6: モード別プロンプト分離による応答高速化
- ルール: ユーザーが選択した出力モード（簡易版/詳細版）に応じて、AIプロンプトおよび max_tokens を切り替えること。
  - 簡易版 (compact): 長文解析（【1】〜【7】）を生成せず、カード生成に必要な4項目のみを出力 (max_tokens=500)。
  - 詳細版 (full): 全文講評テキストを出力 (max_tokens=4096)。
- 教訓: 簡易版モード時に詳細文章を裏で生成させると15〜20秒の無駄な待機時間が発生する。プロンプトを分岐させることで、簡易版のレスポンス時間を 3〜5 秒へ大幅短縮可能。

### 規則 7: サーバー（Render Free Tier）のスリープ回避とヘルスチェック
- ルール: FastAPI に /health エンドポイントを実装し、外部 ping サービス（UptimeRobot等）から 5分間隔で HTTP GET リクエストを送信させること。
- 教訓: 無料サーバーは15分無操作でスリープ状態になり、復帰に30秒〜1分かかるため1枚目の写真返信でタイムアウト・遅延が発生する。定期ヘルスチェックにより24時間即時応答を維持できる。

### 規則 8: 未対応メディア・例外メッセージのユーザーガイダンスハンドリング
- ルール: LINE Webhook 内で、画像メッセージ以外のイベント（StickerMessage や動画・音声・ファイル等の非対応タイプ）を明示的に判定し、適切なガイダンス文面言及を即座に返答すること。
- 教訓: 未判定のメッセージタイプをサイレント無視すると、ユーザーはシステム障害と誤解する。親切な導線案内（「静止画JPEG/PNGを送信してください」）を返すことでUXが向上する。
