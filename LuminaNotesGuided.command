#!/bin/bash
export PATH="/usr/local/bin:/opt/homebrew/bin:${HOME}/.pyenv/shims:${PATH}"
CD_PATH="$(dirname "$0")"
cd "$CD_PATH" || exit 1

xattr -d com.apple.quarantine LuminaNotesGuided.command 2>/dev/null

exec bash scripts/run_guided_web.sh
