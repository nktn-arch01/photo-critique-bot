-- 講評ログにユーザー反応（LINE Quick Reply）を保存
-- 値: good | mixed | weak（いいね / もう少し / いまいち）
-- Supabase SQL Editor で1回実行してください。
-- Q5（H3／反応をプロンプト改善材料にするループ）の入力になる。

ALTER TABLE IF EXISTS public.critique_logs
  ADD COLUMN IF NOT EXISTS user_reaction text NULL;

COMMENT ON COLUMN public.critique_logs.user_reaction IS
  'LINE user reaction after dialogue: good | mixed | weak';
