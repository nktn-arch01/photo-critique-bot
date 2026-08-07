# AGENTS.md

このリポジトリで作業する AI エージェント / 開発者向けの運用メモです。
システム設計思想・開発ルール（13箇条）・プライバシー方針などの詳細は必ず
`ARCHITECTURE.md`（と `PRIVACY_AND_SECURITY.md`）を参照してください。ここには
それらを**重複させず**、日々の運用で迷いやすい非自明なポイントだけをまとめます。

## テスト運用（必須の習慣）

- **コードを変更したら、作業を終える前に必ずオフライン回帰テストを実行する。**
  `python3 test_offline_suite.py`（API キー不要・数秒）。期待する最終行は
  `test_offline_suite: OK`。
- GitHub への push / Pull Request では GitHub Actions の `Offline tests`
  ワークフローが同じテストを自動実行する（`.github/workflows/offline-tests.yml`）。
- 本番の実講評（OpenAI などの実 API 呼び出し）は CI では行わない。手動での代表
  1枚確認に留める（`ARCHITECTURE.md` PART2「開発・運用スタイル規定」に従う）。
- カード生成やパーサーなど共通コアを変更したときは、リグレッション防止のため
  対応する自動テストの追加を検討する（規則1のレビュー3＝自動テスト）。

## Cursor Cloud specific instructions

- **Python 仮想環境はリポジトリ外の `/home/ubuntu/.venv`（= `"$HOME/.venv"`）にある。**
  `/workspace` 内に venv を作ると、Cloud Agent 起動時の git チェックアウトで壊れる
  ため、必ずリポジトリ外に置くこと。Python 実行は `"$HOME/.venv/bin/python"`、
  依存追加は `"$HOME/.venv/bin/pip"` を使う。
- **LINE Bot Web サーバー**は環境の start スクリプトで自動起動する
  （`uvicorn main:app --host 0.0.0.0 --port 8000`）。手動起動する場合は
  `cd /workspace && "$HOME/.venv/bin/uvicorn" main:app --host 0.0.0.0 --port 8000`。
  動作確認は `curl -s http://localhost:8000/health`（認証不要で 200 が返る）。
- `exiftool` はインストール済み（EXIF 抽出の第一候補。`scanner.py` 規則12）。未導入
  環境では PIL にフォールバックするため、無くても動作は継続する。
- **実際の講評生成や Supabase 保存にはシークレットが必要**：`OPENAI_API_KEY`,
  `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `LINE_CHANNEL_SECRET`,
  `LINE_CHANNEL_ACCESS_TOKEN`。これらは Cloud Agent の **Secrets** に登録する
  （本番 Render の環境変数とは別管理で、自動連携はされない）。未設定でも `/health`
  とオフラインテストは動作する。
