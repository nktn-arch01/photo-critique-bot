#!/usr/bin/env bash
# Lumina Notes Guided Web — 起動スクリプト（ターミナルにコピペ一発で実行可）
set -euo pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:${HOME}/.pyenv/shims:${PATH}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${GUIDED_WEB_PORT:-8765}"
URL="http://127.0.0.1:${PORT}/"

echo "=== Lumina Notes Guided ==="
echo "フォルダ: $ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "エラー: python3 が見つかりません。Python 3 をインストールしてください。"
  exit 1
fi

echo "依存パッケージを確認しています…"
python3 -m pip install -q python-multipart fastapi uvicorn pillow 2>/dev/null || \
  python3 -m pip install python-multipart fastapi uvicorn pillow

if curl -sf "${URL}api/health" >/dev/null 2>&1; then
  echo "すでに起動中です: ${URL}"
  open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true
  exit 0
fi

echo "サーバを起動します（終了は Ctrl+C）…"
export GUIDED_WEB_PORT="$PORT"

(
  for _ in $(seq 1 40); do
    if curl -sf "${URL}api/health" >/dev/null 2>&1; then
      echo "ブラウザを開きます: ${URL}"
      open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true
      exit 0
    fi
    sleep 0.25
  done
  echo "警告: サーバの起動確認がタイムアウトしました。手動で開いてください: ${URL}"
) &

exec python3 -m guided_web.app
