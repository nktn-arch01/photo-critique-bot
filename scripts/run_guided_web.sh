#!/usr/bin/env bash
# Lumina Notes Guided Web — 起動スクリプト（ターミナルにコピペ一発で実行可）
# サーバは前面で動かす。Control+C がそのプロセスに届き、確実に止まる。
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

listening_pids() {
  lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN -t 2>/dev/null || true
}

stop_listening() {
  local pids
  pids="$(listening_pids)"
  if [[ -z "$pids" ]]; then
    return 0
  fi
  echo "サーバを停止します…"
  # bash 3.2 互換（Mac 標準）
  echo "$pids" | while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    kill -TERM "$pid" 2>/dev/null || true
  done
  for _ in 1 2 3 4 5 6 7 8; do
    [[ -z "$(listening_pids)" ]] && break
    sleep 0.25
  done
  echo "$pids" | while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    kill -KILL "$pid" 2>/dev/null || true
  done
}

if [[ -n "$(listening_pids)" ]]; then
  echo "前のサーバを止めて、最新のプログラムで起動し直します…"
  stop_listening
  if [[ -n "$(listening_pids)" ]]; then
    echo "エラー: 前のサーバを停止できませんでした。"
    echo "ポート ${PORT} が使われている場合は次を試してください:"
    echo "  GUIDED_WEB_PORT=8766 bash scripts/run_guided_web.sh"
    exit 1
  fi
fi

export GUIDED_WEB_PORT="$PORT"
OPEN_URL="${URL}?v=$(date +%s)"

opener() {
  for _ in $(seq 1 40); do
    if curl -sf "${URL}api/health" >/dev/null 2>&1; then
      echo "ブラウザを開きます: ${URL}"
      open "$OPEN_URL" 2>/dev/null || xdg-open "$OPEN_URL" 2>/dev/null || true
      return 0
    fi
    sleep 0.25
  done
  echo "エラー: サーバが ${URL} で応答しません（起動確認タイムアウト）。"
  echo "ポート ${PORT} が使われている場合は次を試してください:"
  echo "  GUIDED_WEB_PORT=8766 bash scripts/run_guided_web.sh"
  return 1
}

echo "サーバを起動します（終了は Control+C）…"
opener &
OPENER_PID=$!

cleanup_opener() {
  kill "$OPENER_PID" 2>/dev/null || true
  wait "$OPENER_PID" 2>/dev/null || true
}

# python は前面。Control+C は uvicorn に届く。
set +e
python3 -m guided_web.app
status=$?
set -e
cleanup_opener

if [[ "$status" -ne 0 && "$status" -ne 130 && "$status" -ne 143 ]]; then
  echo "エラー: サーバの起動に失敗しました。"
  echo "ポート ${PORT} が使われている場合は次を試してください:"
  echo "  GUIDED_WEB_PORT=8766 bash scripts/run_guided_web.sh"
  exit 1
fi
exit "$status"
