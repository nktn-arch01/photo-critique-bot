#!/usr/bin/env bash
# Lumina Notes Guided — Mac .app 起動（ターミナルは出さない）
# サーバは .command と同じ python3。画面は /usr/bin/open。
# Dock 用本体は osacompile した束内の applet（/usr/bin/osascript へ exec しない）。
set -euo pipefail

export PATH="/Library/Frameworks/Python.framework/Versions/Current/bin:/usr/local/bin:/opt/homebrew/bin:${HOME}/.pyenv/shims:${PATH}"
export PYTHONUNBUFFERED=1

ROOT="${GUIDED_APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"
export GUIDED_APP_ROOT="$ROOT"

PORT="${GUIDED_WEB_PORT:-8765}"
APP="${ROOT}/LuminaNotesGuided.app"
SERVER_ONLY=0
if [[ "${1:-}" == "--server-only" ]]; then
  SERVER_ONLY=1
fi

alert() {
  local msg="$1"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display dialog \"${msg}\" buttons {\"OK\"} default button 1 with title \"Lumina Notes Guided\"" >/dev/null 2>&1 || true
  fi
  echo "エラー: ${msg}" >&2
}

listening_pids() {
  lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN -t 2>/dev/null || true
}

stop_listening() {
  local pids
  pids="$(listening_pids)"
  if [[ -z "$pids" ]]; then
    return 0
  fi
  echo "前のサーバを停止します…"
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

ensure_dock_applet() {
  local host src tmp
  host="${APP}/Contents/MacOS/applet"
  src="${ROOT}/guided_web/mac_dock_host.jxa"
  if [[ -x "$host" && "$src" -ot "$host" ]]; then
    return 0
  fi
  if ! command -v osacompile >/dev/null 2>&1; then
    return 1
  fi
  echo "Dock 用の本体を用意しています…"
  tmp="$(mktemp -d)"
  if ! osacompile -s -l JavaScript -o "${tmp}/LNDock.app" "$src"; then
    rm -rf "$tmp"
    return 1
  fi
  mkdir -p "${APP}/Contents/Resources/Scripts"
  cp "${tmp}/LNDock.app/Contents/MacOS/applet" "$host"
  cp "${tmp}/LNDock.app/Contents/Resources/Scripts/main.scpt" \
    "${APP}/Contents/Resources/Scripts/main.scpt"
  chmod +x "$host"
  xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
  rm -rf "$tmp"
  [[ -x "$host" ]]
}

if [[ "$SERVER_ONLY" -eq 0 ]]; then
  stop_listening || true
  if ensure_dock_applet && [[ -x "${APP}/Contents/MacOS/applet" ]]; then
    echo "Dock 本体を起動します…"
    exec "${APP}/Contents/MacOS/applet"
  fi
  alert "Dock 用の本体を作れませんでした。保険の LuminaNotesGuided.command をダブルクリックしてください。"
  exit 1
fi

if [[ -z "${GUIDED_SERVER_LOGIN:-}" ]] && command -v zsh >/dev/null 2>&1; then
  export GUIDED_SERVER_LOGIN=1
  exec zsh -lc 'source "$HOME/.zprofile" >/dev/null 2>&1 || true; source "$HOME/.zshrc" >/dev/null 2>&1 || true; cd "$GUIDED_APP_ROOT" && exec bash "$GUIDED_APP_ROOT/scripts/run_guided_app.sh" --server-only'
fi

if ! command -v python3 >/dev/null 2>&1; then
  alert "Python 3 が見つかりません。python.org から Python 3 を入れてから、もう一度開いてください。"
  exit 1
fi

if [[ -z "${OPENAI_API_KEY:-}" && ! -f "${HOME}/.openai_api_key" ]]; then
  if command -v zsh >/dev/null 2>&1; then
    _k="$(zsh -lic 'printenv OPENAI_API_KEY' 2>/dev/null || true)"
    if [[ -n "${_k}" ]]; then
      export OPENAI_API_KEY="${_k}"
    fi
  fi
fi

echo "=== Lumina Notes Guided.app ==="
echo "フォルダ: $ROOT"
echo "python3: $(command -v python3)"
GUIDED_PY=(bash "${ROOT}/scripts/guided_python.sh")
"${GUIDED_PY[@]}" --version 2>&1 || true
"${GUIDED_PY[@]}" -c "import platform; print('python_machine', platform.machine())" 2>&1 || true

if ! "${GUIDED_PY[@]}" -c "import fastapi, uvicorn, PIL"; then
  echo "依存パッケージを入れています…"
  "${GUIDED_PY[@]}" -m pip install python-multipart fastapi uvicorn pillow || true
fi
if ! "${GUIDED_PY[@]}" -c "import fastapi, uvicorn, PIL"; then
  alert "必要な部品を入れられませんでした。保険の LuminaNotesGuided.command をダブルクリックしてください。"
  exit 1
fi

if [[ -n "$(listening_pids)" ]]; then
  echo "前のサーバを止めて、最新のプログラムで起動し直します…"
  stop_listening
fi

export GUIDED_WEB_PORT="$PORT"

echo "サーバを起動して画面を開きます（終了は Dock から）…"
set +e
bash "${ROOT}/scripts/guided_python.sh" -m guided_web.desktop_window
status=$?
set -e

if [[ "$status" -ne 0 && "$status" -ne 130 && "$status" -ne 143 ]]; then
  alert "Guided を起動できませんでした。保険の LuminaNotesGuided.command をダブルクリックしてください。"
  exit 1
fi
exit "$status"
