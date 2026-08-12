#!/bin/bash
export PATH="/usr/local/bin:/opt/homebrew/bin:~/.pyenv/shims:$PATH"
CD_PATH="$(dirname "$0")"
cd "$CD_PATH" || exit 1

# 起動時の Gatekeeper ブロック属性を自動削除
xattr -d com.apple.quarantine LuminaNotesConsole.command 2>/dev/null

python3 console_gui.py
status=$?

# .command ダブルクリック起動時: Console 終了後にこの Terminal ウィンドウを閉じる
# （既存のターミナルから python3 console_gui.py を直接起動した場合はこのスクリプトを通らない）
osascript >/dev/null 2>&1 <<'EOF' &
tell application "Terminal"
  try
    close front window
  end try
end tell
EOF

exit "$status"
