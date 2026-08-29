-- LINE はカード白固定・講評はカード＋対話に統一したため、user_settings は使わない。
-- 既存の LINE user ID を消す。コードを Render に載せてから 1 回実行。
-- テーブル自体は残してよい（空のまま）。

TRUNCATE TABLE public.user_settings;
