-- Supabase ダッシュボード > SQL Editor で実行する推奨設定（任意）
-- サービスロールキーは RLS をバイパスするため、RLS は「将来 anon キーを使う場合」の保険。

-- 1. RLS を有効化（テーブルが存在する場合）
ALTER TABLE IF EXISTS public.user_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.critique_logs ENABLE ROW LEVEL SECURITY;

-- 2. anon / authenticated からの直接読み取りを禁止（ポリシー未作成＝拒否）
--    バックエンド（service_role）のみ Table Editor / API 経由で操作。

-- 3. Storage: critique-cards バケットを Private に変更し、
--    Render 環境変数 SUPABASE_CARD_SIGNED_SECONDS=604800 （7日）などを設定。
--    Public バケットのままでは URL を知る第三者がカード画像を閲覧可能。

-- 4. 定期削除（保持 30 日・推奨）
--    リポジトリの retention_purge.py と GitHub Actions「Monthly retention purge」を使用。
--    手動 SQL の例（GitHub Actions 未使用時）:
-- DELETE FROM public.critique_logs WHERE created_at < now() - interval '30 days';
-- Storage はダッシュボードまたは retention_purge.py の Storage API 削除に合わせる。
