#!/bin/bash
export PATH="/usr/local/bin:/opt/homebrew/bin:~/.pyenv/shims:$PATH"
CD_PATH="$(dirname "$0")"
cd "$CD_PATH" || exit 1

# フォルダ選択ダイアログ（AppleScript経由）でパスを取得して実行
TARGET_DIR=$(osascript -e 'POSIX path of (choose folder with prompt "先頭8文字で.dop名をリネームする対象フォルダを選択してください")' 2>/dev/null)

if [ -n "$TARGET_DIR" ]; then
    python3 fix_dop_names.py "$TARGET_DIR"
    osascript -e 'display dialog "✨ リネーム完了！" buttons {"OK"} default button "OK"'
fi
