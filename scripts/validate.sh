#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

shell_file_list="$(mktemp)"
trap 'rm -f -- "$shell_file_list"' EXIT
find "$ROOT" \
  \( -path "$ROOT/.git" -o -path "$ROOT/build" -o -path "$ROOT/dist" \
     -o -path "$ROOT/rpmbuild" -o -path "$ROOT/sources" \
     -o -path "$ROOT/governor-src" -o -path "$ROOT/unlock-src" \
     -o -path "$ROOT/live-manager-src" \) -prune -o \
  -type f \( -name '*.sh' -o -path "$ROOT/packaging/bc250" \
     -o -path "$ROOT/install" \) -print0 > "$shell_file_list"
mapfile -d '' shell_files < "$shell_file_list"
for file in "${shell_files[@]}"; do
  bash -n "$file"
done

PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
echo "Repository validation passed."
