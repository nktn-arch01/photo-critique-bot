# Photo AI Critique - システム設計仕様書 & 統合開発ルール (Architecture & ADR)

---

## PART 1: システム設計仕様書 (System Architecture)

### 1. ハイブリッド・システム構造
本システムは、**ローカル環境（デスクトップGUIバッチ処理）** と **クラウド環境（LINE Bot Web サーバー）** が、中央の **「共通コアモジュール（AIエンジン・カード生成）」** を共有するハイブリッド構造で設計されています。

[デスクトップ版 (app_gui.py)]
  ├── 1. JPG + .dop スキャン & EXIF/IPTCメタデータ抽出 (前回選択フォルダ復元機能付き)
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
  │      ├── Storage (cards) へ PNG アップロード ➔ Public URL 取得
  │      └── DB (critique_logs / user_settings) へ ログ保存 & モード取得
  └── 5. LINE Messaging API ➔ 画像カード + テキスト Push 送信

[外部監視 (UptimeRobot)]
  └── 5分おき GET /health ➔ Render 無料枠サーバーのスリープ回避

### 2. ファイル役割定義 (コンポーネント構成)

#### ① 共通コアモジュール (Shared Core)
- `critique_engine.py`: OpenAI Vision API (`gpt-4o-mini`) 呼び出し。2段階分離生成（Phase 1: カード用4項目確定 ➔ Phase 2: 本文【1】〜【7】生成）、動的スコア評価、モード分岐 (`compact`/`full`) を担う核心エンジン。
- `generate_critique_card.py`: Pillow による 1080×1350px 講評カード画像生成。表記揺れを許容する柔軟なテキストパース機能を搭載。
- `fonts/Noto_Sans_JP/static/NotoSansJP-Regular.ttf`: カード描画用確定日本語バイナリフォント (5.5MB)。

#### ② デスクトップ版コンポーネント (Desktop Environment)
- `app_gui.py`: Tkinter GUIコンソール。前回フォルダ自動記憶（`.photo_ai_config.json`）、実行前確認ダイアログ、リアルタイム進捗表示、処理対象親フォルダ直接オープン機能を備えた安全設計。
- `log_manager.py`: `DesktopLogManager` クラス。`##` と `■` の表記揺れを吸収する正規表現パースを備え、ローカルファイル群へ構造化出力。
- `PhotoAICritique.command`: ダブルクリック起動シェルスクリプト（Gatekeeper属性の自動解除機能付き）。
- `fix_dop_names.py` / `FixDopNames.command`: DxO PhotoLab 用 `.dop` サイドカーファイル名補正ツール。

#### ③ LINE Bot クラウドコンポーネント (Cloud / Render Environment)
- `main.py`: FastAPI Web サーバー。LINE Webhook ハンドリング、BackgroundTasks、`/health` エンドポイント、例外応方案内。
- `supabase_client.py`: Supabase DB および Storage 操作クライアント。

---

## PART 2: 開発ルール & 統合トラブル回避教訓集 (ADR / Lessons Learned)

### 規則 1: 共通コアモジュールのインターフェース完全性 (単一責任 & 柔軟性)
- **ルール:** `critique_engine.py` の `generate_critique()` は、デスクトップ版から送られる高度なメタデータ（`metadata`, `dop_info`）を全受容しつつ、LINE Bot等から渡される最小限の画像データに対してもエラーなくフォールバック動作する柔軟な引数設計を維持すること。

### 規則 2: 2段階分離生成（2フェーズアーキテクチャ）によるスコア動的化と品質担保
- **ルール:** 長文講評（`mode="full"`）を生成する際は、プロンプト本文を改変せず、**「Phase 1: 評価・カード用4項目（TITLE, SUMMARY, SCORES, CRITIQUE_SUMMARY）の確定」** と **「Phase 2: 確定結果を注入した長文本文（【1】〜【7】）の生成」** の2段階に通信を分離すること。
- **教訓:** 単一プロンプトで長文とスコアを同時生成させると、LLMの注意力が散漫になりスコアが `[4,5,4,4,4]` 等に固定化する。フェーズ分離により20260801最新版プロンプトの厳格な制約（否定語禁止ルール等）を完全維持したまま100%動的なスコア算出が可能となる。

### 規則 3: モード別プロンプト分岐による高速化 (LINE Bot UX)
- **ルール:** `mode="compact"`（簡易版）呼び出し時は、Phase 1（4要素のみ）完了時点で即座にレスポンスを返し、Phase 2 の生成を完全にバイパスすること。
- **教訓:** 簡易版で裏で長文を生成させると 15〜20 秒の不要な待機時間が発生する。バイパスにより 3〜5 秒の超高速レスポンスを実現できる。

### 規則 4: Phase 1 への時間帯ファクト (`time_zone_fact`) 必須注入原則
- **ルール:** Phase 1 のリクエストには、画像データだけでなく必ず撮影日時と時間帯分類（`早朝・黎明`、`夕方・マジックアワー` 等）を渡すこと。
- **教訓:** ファクトデータがない場合、LLMが視覚情報だけで朝焼けを「夕暮れ」と誤認してタイトルを確定させてしまい、Phase 2 の本文講評まで誤認が波及する。

### 規則 5: ハッシュタグ用機材名スペースのアンダースコア自動置換
- **ルール:** `camera_model` や `lens_model` の文字列をハッシュタグ（`#カメラ_` / `#レンズ_`）へ埋め込む際は、Python側で事前にスペースをアンダースコア（`_`）へ自動変換すること。
- **教訓:** `OM 14-150mm F4.0-5.6 II` のようにスペースが含まれると、SNSハッシュタグとして認識される文字列が途中で分断・破損する。

### 規則 6: LLM出力見出しの表記揺れ（`##` と `■`）受容パース
- **ルール:** `log_manager.py` および `generate_critique_card.py` のパース処理では、LLMが `■TITLE:` と出力しても `## ■TITLE:` や `## SCORES:` と出力しても正しく抽出できる柔軟な正規表現（`(?:##\s*)?■?\s*`）を使用すること。

### 規則 7: GUIコンソールの操作安全性と永続化原則
- **ルール:** デスクトップGUI（`app_gui.py`）は、前回選択フォルダの自動記憶（`.photo_ai_config.json`）、一括処理開始前の確認ダイアログ、および処理完了時の「処理対象親フォルダ直接オープン」機能を保持すること。

### 規則 8: 同期・非同期処理の厳格分離 (LINE Webhook)
- **ルール:** LINEの Webhook 内で重いタスクを行う際は、必ず FastAPI の `BackgroundTasks` を使用し、一括送信は `push_message` で行うこと。

### 規則 9: サーバー（Render Free Tier）のスリープ防止
- **ルール:** `/health` エンドポイントを設け、外部監視（UptimeRobot等）から 5分間隔で ping アクセスを送信させること。

### 規則 10: コードブロックおよびアスキーアートツリーの整形維持原則
- **ルール:** ドキュメント（`ARCHITECTURE.md` 等）やスクリプトを作成・更新する際は、多重ネストによるコードブロック破綻やアスキーツリーの改行潰れ（コピペボックス外への漏れ出し）を起こさないよう、インデントとブロック囲みを厳密に保持すること。
- **教訓:** レンダリングの崩れは可読性を著しく損ない、スクリプト実行時の文法エラーや指定不備の原因となる。
