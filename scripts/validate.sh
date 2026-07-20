#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mapfile -d '' shell_files < <(
  find "$ROOT" \
    \( -path "$ROOT/.git" -o -path "$ROOT/build" -o -path "$ROOT/dist" \
       -o -path "$ROOT/rpmbuild" -o -path "$ROOT/sources" \
       -o -path "$ROOT/governor-src" -o -path "$ROOT/unlock-src" \
       -o -path "$ROOT/live-manager-src" \) -prune -o \
    -type f \( -name '*.sh' -o -path "$ROOT/packaging/bc250" \) -print0
)
for file in "${shell_files[@]}"; do
  bash -n "$file"
done

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck --external-sources --severity=warning "${shell_files[@]}"
else
  echo "NOTE: shellcheck is not installed; syntax checks still ran." >&2
fi

PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v

if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$ROOT" diff --check
fi

echo "Repository validation passed."
