# プライバシー & セキュリティ（Photo AI Critique）

個人利用〜小規模 LINE Bot 向けの整理です。**コード変更**と**Supabase / 運用であなたが行うこと**に分けています。

---

## 1. データがどこに残るか

| 場所 | 内容 | リスクの要点 |
|------|------|----------------|
| **Supabase `critique_logs`** | LINE user ID、講評要約、カード URL 等（全文は既定オフ） | Table Editor で閲覧可能（プロジェクト管理者）。**30 日で削除** |
| **Supabase `critique_events`** | 匿名ハッシュ、テーマ、TITLE、要約、スコア、反応 | LINE ID・全文・カードなし。**30 日削除の対象外**（分析用） |
| **Supabase `user_settings`** | （旧）LINE user ID、mode、card_theme | **新規書き込みなし。** 空にしてよい（`supabase/empty_user_settings.sql`） |
| **Supabase Storage `critique-cards`** | 講評カード PNG | **Public バケットだと URL 漏洩で第三者も閲覧可能** |
| **Render ログ** | エラー・処理状況（user ID はマスク済み） | Render アカウント保持者が閲覧 |
| **OpenAI** | 送信した画像・プロンプト | [OpenAI データポリシー](https://openai.com/policies) に従う（API 利用規約の確認） |
| **LINE** | ユーザーが送った写真・メッセージ | LINE 側の保持 |
| **デスクトップ（ローカル）** | 月別フォルダ内 MD/TXT/カード | PC・バックアップの管理 |

---

## 2. コードで入れた補強（リポジトリ内）

| 機能 | 説明 |
|------|------|
| **`privacy_utils.py`** | ログ用 user ID マスク、Storage パス用ハッシュ、分析用 `user_hash` |
| **Storage パス** | `{16文字ハッシュ}/{message_id}_card.png`（生の LINE ID をパスに含めない） |
| **Render ログ** | `line_user_id` 全文を出さない |
| **環境変数** | 下表（Render に設定可能） |

### Render 環境変数（任意）

| 変数 | 既定 | 意味 |
|------|------|------|
| `CRITIQUE_SAVE_DB` | `true` | `false` で **DB への講評ログ insert をスキップ**（モード設定は継続） |
| `CRITIQUE_SAVE_FULL_TEXT` | `false` | `true` のときだけ DB に講評**全文**を保存。既定はタイトル・要約・スコア・反応のみ。既に入っている全文は自動では消えず、30日削除または手動更新が必要。 |
| `ANALYTICS_HASH_SALT` | `lumina-analytics` | 分析テーブル `user_hash` 用。`STORAGE_PATH_SALT` と**同じ値にしない**。変更すると同一ユーザーの集計が切れる。 |
| `SUPABASE_CARD_SIGNED_SECONDS` | 未設定 | 設定すると **署名付き URL**（Private バケット向け）。例: `604800`（7日） |
| `STORAGE_PATH_SALT` | 固定文字列 | Storage フォルダハッシュ用（変更するとパスが変わる） |

---

## 3. Supabase で推奨する設定（あなたの作業）

1. **`supabase/security_recommendations.sql`** を SQL Editor で必要に応じて実行  
2. **Storage `critique-cards` を Private に** → Render に `SUPABASE_CARD_SIGNED_SECONDS=604800`  
3. **Table Editor へのアクセス** … 信頼できるアカウントのみ、2FA 有効化  
4. **Service Role Key** … Render のみ。GitHub・スクショに載せない  
5. **保持期間** … **`retention_purge.py`** + GitHub Actions **`Monthly retention purge`**（`.github/workflows/retention-purge.yml`）で **30 日超**の `critique_logs` と `critique-cards` を毎月自動削除。**`critique_events` は削除しない。** 手動は `DRY_RUN=true python retention_purge.py`  
6. **分析テーブル** … **`supabase/add_critique_events.sql`** を SQL Editor で1回実行  
7. **利用者への説明** … LINE Bot 利用時に「写真は AI 解析・カード生成のため外部サービスに送信される」旨をプロフィールや固定文で告知  
8. **旧 `user_settings`** … LINE が白カード固定になったあと **`supabase/empty_user_settings.sql`** で中身を空にする  

### GitHub Actions 用 Secrets（月次削除）

| Secret | 内容 |
|--------|------|
| `SUPABASE_URL` | プロジェクト URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service Role（Render と同じキー。**リポジトリにコミットしない**） |

初回: GitHub → **Actions** → **Monthly retention purge** → **Run workflow** → `dry_run=true` で件数確認 → 問題なければ `dry_run=false`。

---

## 4. 優先度付き対応計画

### すぐ（高）

- [ ] Storage が **Public** か確認 → 可能なら **Private + 署名 URL**（上記 env）  
- [ ] Supabase / Render / OpenAI / LINE の **パスワード・2FA**  
- [ ] `SUPABASE_SERVICE_ROLE_KEY` がリポジトリに無いことを確認（`.env` は gitignore）  

### 中期的（中）

- [x] ログ保持 **既定は全文を保存しない**（`CRITIQUE_SAVE_FULL_TEXT=true` でオプトイン）  
- [x] 分析用匿名テーブル **`critique_events`**（LINE ID・全文・カードなし）  
- [ ] 不要になった Storage / DB 行の **月次削除**（`retention_purge.py` + GitHub Secrets 設定済みか確認）  
- [ ] LINE 友だち向け **簡易プライバシー説明**（固定メッセージ）  

### 低（余裕があれば）

- [ ] OpenAI **Zero Data Retention** 等、契約プランに応じた設定確認  
- [ ] デスクトップ側ログの **ディスク暗号化**（FileVault 等は Mac 標準）  

---

## 5. デスクトップ版

- API キー: `~/.openai_api_key` … ファイル権限 `chmod 600` 推奨  
- 出力ノートに **EXIF・撮影意図** が含まれる … 共有フォルダに置かない  

---

変更後は LINE でカード送信が届くか確認してください（Private + 署名 URL 時は特に重要）。
