# Guided のプログラム置き場（photo-critique-bot）を一つに覚える。
# .app がリポジトリ内でもアプリケーションフォルダでも、同じ規則。
# 使い方: source してから guided_root_resolve <この.appの親フォルダ候補>
# 成功時 GUIDED_APP_ROOT を export する。

guided_root_config="${GUIDED_ROOT_FILE:-${HOME}/.lumina_notes/guided_root}"

guided_root_ok() {
  local r="${1:-}"
  [[ -n "$r" && -f "${r}/scripts/run_guided_app.sh" && -f "${r}/guided_web/desktop_window.py" ]]
}

guided_root_save() {
  local r="$1"
  mkdir -p "$(dirname "$guided_root_config")"
  printf '%s\n' "$r" > "$guided_root_config"
}

guided_root_saved() {
  [[ -f "$guided_root_config" ]] || return 1
  local r
  r="$(tr -d '\r\n' < "$guided_root_config")"
  guided_root_ok "$r" || return 1
  printf '%s\n' "$r"
}

guided_root_pick_folder() {
  local picked=""
  if command -v osascript >/dev/null 2>&1; then
    picked="$(osascript -e 'POSIX path of (choose folder with prompt "Lumina Notes のプログラムが入っているフォルダ（photo-critique-bot）を選んでください。")' 2>/dev/null || true)"
  fi
  picked="${picked%$'\r'}"
  picked="${picked%/}"
  printf '%s\n' "$picked"
}

guided_root_should_handoff() {
  local this_app="${1:-}"
  local root="${2:-}"
  local repo_app="${root}/LuminaNotesGuided.app"
  [[ -x "${repo_app}/Contents/MacOS/LuminaNotesGuided" ]] || return 1
  local here there
  here="$(cd "$this_app" && pwd)"
  there="$(cd "$repo_app" && pwd)"
  [[ "$here" != "$there" ]]
}

guided_root_resolve() {
  local candidate="${1:-}"
  GUIDED_APP_ROOT="${GUIDED_APP_ROOT:-}"
  if guided_root_ok "$GUIDED_APP_ROOT"; then
    guided_root_save "$GUIDED_APP_ROOT"
    export GUIDED_APP_ROOT
    return 0
  fi
  if guided_root_ok "$candidate"; then
    GUIDED_APP_ROOT="$candidate"
    guided_root_save "$GUIDED_APP_ROOT"
    export GUIDED_APP_ROOT
    return 0
  fi
  local saved=""
  saved="$(guided_root_saved || true)"
  if guided_root_ok "$saved"; then
    GUIDED_APP_ROOT="$saved"
    export GUIDED_APP_ROOT
    return 0
  fi
  local picked=""
  picked="$(guided_root_pick_folder)"
  picked="${picked%/}"
  if guided_root_ok "$picked"; then
    GUIDED_APP_ROOT="$picked"
    guided_root_save "$GUIDED_APP_ROOT"
    export GUIDED_APP_ROOT
    return 0
  fi
  return 1
}
