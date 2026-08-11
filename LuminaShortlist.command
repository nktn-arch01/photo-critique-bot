#!/bin/bash
export PATH="/usr/local/bin:/opt/homebrew/bin:~/.pyenv/shims:$PATH"
CD_PATH="$(dirname "$0")"
cd "$CD_PATH" || exit 1

# 起動時の Gatekeeper ブロック属性を自動削除
xattr -d com.apple.quarantine LuminaShortlist.command 2>/dev/null

python3 shortlist_gui.py
