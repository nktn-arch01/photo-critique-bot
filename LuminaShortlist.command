#!/bin/bash
# 互換スタブ: 旧ランチャー名。新規は LuminaNotesConsole.command を使う。
CD_PATH="$(dirname "$0")"
cd "$CD_PATH" || exit 1
exec "$CD_PATH/LuminaNotesConsole.command"
