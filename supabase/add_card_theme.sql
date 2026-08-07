-- カード背景テーマ列を user_settings に追加（LINE「背景」設定用）
-- 識別子: dark（既定）/ light
-- Supabase SQL Editor で1回実行してください。

ALTER TABLE IF EXISTS public.user_settings
  ADD COLUMN IF NOT EXISTS card_theme text NOT NULL DEFAULT 'dark';

COMMENT ON COLUMN public.user_settings.card_theme IS
  'Card background theme: dark | light';
