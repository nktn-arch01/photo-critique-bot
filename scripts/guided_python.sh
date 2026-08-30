#!/usr/bin/env bash
# Guided 用 python3。Apple Silicon では必ず arm64 で動かす。
#
# Finder の .app は Rosetta（x86_64）で起動することがある。
# そのままだと、Terminal で入れた arm64 の部品（pydantic など）を読めない。
# `.command` と同じ python3 を、アーキテクチャだけ揃える。
set -euo pipefail

py="$(command -v python3 || true)"
if [[ -z "${py}" ]]; then
  echo "python3 が見つかりません。" >&2
  exit 127
fi

if [[ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" == "1" ]] && command -v arch >/dev/null 2>&1; then
  if arch -arm64 "${py}" -c "import sys" >/dev/null 2>&1; then
    exec arch -arm64 "${py}" "$@"
  fi
fi

exec "${py}" "$@"
