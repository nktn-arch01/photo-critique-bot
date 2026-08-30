#!/usr/bin/env bash
# LuminaNotesGuided.app をアプリケーションフォルダへ置く。
# プログラム本体は photo-critique-bot のまま。置き場だけ覚える。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../LuminaNotesGuided.app/Contents/Resources/guided_root.sh
source "${ROOT}/LuminaNotesGuided.app/Contents/Resources/guided_root.sh"

if ! guided_root_ok "$ROOT"; then
  echo "エラー: photo-critique-bot フォルダで実行してください。" >&2
  exit 1
fi

guided_root_save "$ROOT"

DEST_DIR="${GUIDED_APPLICATIONS_DIR:-/Applications}"
DEST="${DEST_DIR}/LuminaNotesGuided.app"
SRC="${ROOT}/LuminaNotesGuided.app"

mkdir -p "$DEST_DIR"
rm -rf "$DEST"
if command -v ditto >/dev/null 2>&1; then
  ditto "$SRC" "$DEST"
else
  cp -R "$SRC" "$DEST"
fi
chmod +x "${DEST}/Contents/MacOS/LuminaNotesGuided"
xattr -dr com.apple.quarantine "$DEST" 2>/dev/null || true

echo "アプリケーションに置きました。"
echo "$DEST"
echo "次は「アプリケーション」フォルダの Lumina Notes Guided を開いてください。"
