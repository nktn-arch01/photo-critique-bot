#!/usr/bin/env bash
# Lumina Notes Guided Web — 起動スクリプト（ターミナルにコピペ一発で実行可）
set -euo pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:${HOME}/.pyenv/shims:${PATH}"
export PYTHONUNBUFFERED=1

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

BOOT_LOG="${TMPDIR:-/tmp}/lumina_guided_boot_${PORT}.log"
: > "$BOOT_LOG"

echo "サーバを起動します（終了は Ctrl+C）…"
export GUIDED_WEB_PORT="$PORT"

python3 -m guided_web.app > >(tee "$BOOT_LOG") 2>&1 &
SERVER_PID=$!

cleanup_server() {
  if kill -0 "$SERVER_PID" 2>/dev/null; then
    kill -INT "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup_server INT TERM

ready=0
for _ in $(seq 1 40); do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "エラー: サーバの起動に失敗しました。"
    echo "---- ログ（${BOOT_LOG}）----"
    cat "$BOOT_LOG" 2>/dev/null || true
    echo "----------------"
    echo "ポート ${PORT} が使われている場合は次を試してください:"
    echo "  GUIDED_WEB_PORT=8766 bash scripts/run_guided_web.sh"
    exit 1
  fi
  if curl -sf "${URL}api/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.25
done

if [ "$ready" -eq 0 ]; then
  echo "エラー: サーバが ${URL} で応答しません（起動確認タイムアウト）。"
  echo "---- ログ（${BOOT_LOG}）----"
  tail -n 50 "$BOOT_LOG" 2>/dev/null || true
  echo "----------------"
  cleanup_server
  exit 1
fi

echo "ブラウザを開きます: ${URL}"
open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true

wait "$SERVER_PID" || true
