#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export GUIDED_WEB_PORT="${GUIDED_WEB_PORT:-8765}"
python3 -m guided_web.app &
PID=$!
sleep 1
open "http://127.0.0.1:${GUIDED_WEB_PORT}/"
echo "Lumina Notes Guided — http://127.0.0.1:${GUIDED_WEB_PORT}/ (PID $PID)"
wait $PID
