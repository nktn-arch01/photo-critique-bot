# Photo AI Critique - システム設計仕様書 & 統合開発ルール (Architecture & ADR)

---

## PART 1: システム設計仕様書 (System Architecture)

### 1. ハイブリッド・システム構造
本システムは、**ローカル環境（デスクトップGUIバッチ処理）** と **クラウド環境（LINE Bot Web サーバー）** が、中央の **「共通コアモジュール（AIエンジン・カード生成）」** を共有するハイブリッド構造で設計されています。

```
[デスクトップ版 (app_gui.py)]
  ├── 1. JPG + .dop スキャン & EXIF/IPTCメタデータ抽出
  ├── 2. 共通コア (critique_engine.py) ➔ フル解説プロンプト (mode="full") 生成
  ├── 3. 共通コア (generate_critique_card.py) ➔ 1080x1350px カード画像描画
  └── 4. DesktopLogManager (log_manager.py)
         ├── 個別 Markdown ノート (.md) 出力
         ├── 月間テキストログ (.txt) 追記
         ├── 年間統合テキストログ (.txt) 追記
         └── 処理ステータス (.txt) [PROCESSED] 記録

[LINE Bot版 (main.py / Render)]
  ├── 1. LINE Webhook 受信 ➔ BackgroundTasks (非同期処理)
  ├── 2. 共通コア (critique_engine.py) ➔ モード別 (compact: 3〜5秒 / full: 15秒) 生成
  ├── 3. 共通コア (generate_critique_card.py) ➔ カード画像描画
  ├── 4. SupabaseManager (supabase_client.py)
  │      ├── Storage (cards) へ PNG アップロード ➔ Public URL 取得
  │      └── DB (critique_logs / user_settings) へ ログ保存 & モード取得
  └── 5. LINE Messaging API ➔ 画像カード + テキスト Push 送信

[外部監視 (UptimeRobot)]
  └── 5分おき GET /health ➔ Render 無料枠サーバーのスリープ回避
```

### 2. ファイル役割定義 (コンポーネント構成)

#### ① 共通コアモジュール (Shared Core)
- `critique_engine.py`: OpenAI Vision API (`gpt-4o-mini`) 呼び出し。EXIF/.dop メタデータ注入プロンプト、動的スコア評価、モード分岐 (`compact`/`full`) を担う。
- `generate_critique_card.py`: Pillow による 1080×1350px 講評カード画像生成。
- `fonts/Noto_Sans_JP/static/NotoSansJP-Regular.ttf`: カード描画用確定日本語バイナリフォント (5.5MB)。

#### ② デスクトップ版コンポーネント (Desktop Environment)
- `app_gui.py`: Tkinter GUI。フォルダ選択、並列バッチ処理制御、EXIF/.dop メタデータ抽出。
- `log_manager.py`: `DesktopLogManager` クラス。ローカルファイル（Markdownノート、月間/年間ログ、ステータス）への構造化出力。
- `PhotoAICritique.command`: ダブルクリック起動シェルスクリプト。
- `fix_dop_names.py` / `FixDopNames.command`: DxO PhotoLab 用 `.dop` サイドカーファイル名補正ツール。

#### ③ LINE Bot クラウドコンポーネント (Cloud / Render Environment)
- `main.py`: FastAPI Web サーバー。LINE Webhook ハンドリング、BackgroundTasks、`/health` エンドポイント、例外応方案内（スタンプ・動画など）。
- `supabase_client.py`: Supabase DB (`user_settings`, `critique_logs`) および Storage (`cards`) 操作クライアント。
- `requirements.txt`: クラウド環境ライブラリ依存構成。

---

## PART 2: 開発ルール & 統合トラブル回避教訓集 (ADR / Lessons Learned)

### 規則 1: 共通コアモジュールのインターフェース完全性 (単一責任 & 柔軟性)
- **ルール:** `critique_engine.py` の `generate_critique()` は、デスクトップ版から送られる高度なメタデータ（`metadata`, `dop_info`）を全受容しつつ、LINE Bot等から渡される最小限の画像データに対してもエラーなくフォールバック動作する柔軟な引数設計を維持すること。
- **教訓:** クラウドWeb化の過程でプロンプト引数を削ると、デスクトップ版の講評品質が著しく低下（先祖返り）する。

### 規則 2: プロンプトにおける動的スコア評価の徹底 (テンプレート固定化防止)
- **ルール:** プロンプト内の `■SCORES:` フォーマット指定には、固定の数値例（例: `★★★★☆ (4/5)`）を記述せず、プレースホルダー表記（例: `[写真に応じた★評価] ([1〜5の数値]/5)`）と「毎回独自に算出せよ」という厳格指示を入れること。
- **教訓:** 具体例をプロンプトに書くと、LLMが形式固定と誤認識し、全ての画像で毎回まったく同じスコアをコピー＆ペースト出力してしまう。

### 規則 3: モード別プロンプト分岐による高速化 (LINE Bot UX)
- **ルール:** `mode="compact"`（簡易版）呼び出し時は、長文解説（【1】〜【7】）の生成指示を切り捨て、カード生成用の4要素（`■TITLE`, `■SUMMARY`, `■SCORES`, `■CRITIQUE_SUMMARY`）のみを出力させて `max_tokens=500` に絞ること。
- **教訓:** 簡易版で裏で長文を生成させると 15〜20 秒の不要な待機時間が発生する。分岐により 3〜5 秒の超高速レスポンスを実現できる。

### 規則 4: デスクトップ版ログ出力構造の保全
- **ルール:** デスクトップ版のバッチ処理結果は、`DesktopLogManager` を通して以下の出力順序を絶対維持すること。
  `ファイル名` ➔ `■TITLE` ➔ `■SUMMARY` ➔ `■SCORES` ➔ `■CRITIQUE_SUMMARY` ➔ `講評本文(【1】〜【7】)` ➔ `=== メタデータブロック ===`
- **教訓:** ログ構造が崩れると、過去の分析ノートの互換性や視認性が損なわれる。

### 規則 5: 確定バイナリフォントの同梱原則
- **ルール:** 日本語フォントは物理的な実体ファイル（`NotoSansJP-Regular.ttf`）を Git リポジトリ内に保持して参照すること。
- **教訓:** 起動時のネットワーク動的ダウンロードは、アクセス制限等によるファイル破損（文字化け・豆腐化）を引き起こす。

### 規則 6: 同期・非同期処理の厳格分離 (LINE Webhook)
- **ルール:** LINEの Webhook 内で重いタスク（AI解析・カード描画・Storage保存）を行う際は、必ず FastAPI の `BackgroundTasks` を使用し、LINE への一括送信は `push_message` で行うこと。
- **教訓:** 同期的に処理を行うと LINE の `reply_token` がタイムアウト失効し、ユーザーへの返信が失敗する。

### 規則 7: サーバー（Render Free Tier）のスリープ防止
- **ルール:** `/health` エンドポイントを設け、外部監視（UptimeRobot等）から 5分間隔で ping アクセスを送信させること。
- **教訓:** 15分無操作によるサーバー休眠を防ぐことで、1枚目の写真送信時のタイムアウト・レスポンス遅延（30秒〜1分）を100%回避できる。

### 規則 8: 未対応メディアのガイダンス自動返答
- **ルール:** LINE でスタンプ、動画、音声、ファイル等が受信された場合、サイレント無視せず「写真（JPEG/PNG）を送信してください」という親切な自動案内メッセージを即座に返答すること。
- **教訓:** 応答がないとユーザーはシステム障害と誤認し、利便性が低下する。
