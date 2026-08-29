-- 分析用の匿名テーブル（LINE user ID・講評全文・カード URL は持たない）
-- Supabase → SQL Editor で 1 回実行してください。
-- 30 日削除（retention_purge）の対象外。長く残して利用状況とプロンプト改善に使う。

CREATE TABLE IF NOT EXISTS public.critique_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  user_hash text NOT NULL,
  card_theme text,
  title text,
  critique_summary text,
  scores_json jsonb,
  user_reaction text
);

CREATE INDEX IF NOT EXISTS critique_events_user_hash_created_at_idx
  ON public.critique_events (user_hash, created_at DESC);

COMMENT ON TABLE public.critique_events IS
  'Anonymous LINE usage events. No LINE user ID, full critique text, or card URL.';

ALTER TABLE public.critique_events ENABLE ROW LEVEL SECURITY;
