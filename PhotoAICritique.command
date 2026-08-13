#!/bin/bash
export PATH="/usr/local/bin:/opt/homebrew/bin:~/.pyenv/shims:$PATH"
CD_PATH="$(dirname "$0")"
cd "$CD_PATH" || exit 1

# 起動時の Gatekeeper ブロック属性を自動削除
xattr -d com.apple.quarantine PhotoAICritique.command 2>/dev/null

echo "=============================================="
echo "  Photo AI 講評バッチ（レガシー）"
echo "=============================================="
echo "日常の本番は「Lumina Notes Console」です。"
echo "  → LuminaNotesConsole.command"
echo ""
echo "このアプリは旧・一括講評用です（フォルダ一括で"
echo "カード／ノートを付ける）。普段は使いません。"
echo "=============================================="
echo ""

python3 app_gui.py
status=$?
exit "$status"
