#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mode="${1:-all}"
case "$mode" in
  all|--preflight) ;;
  -h|--help)
    echo "Usage: scripts/validate.sh [--preflight]"
    echo "  default       run source preflight plus deterministic tests"
    echo "  --preflight   run cheap source/structure checks only"
    exit 0
    ;;
  *) echo "ERROR: unknown validation mode: $mode" >&2; exit 2 ;;
esac

shell_file_list="$(mktemp)"
trap 'rm -f -- "$shell_file_list"' EXIT
find "$ROOT" \
  \( -path "$ROOT/.git" -o -path "$ROOT/build" -o -path "$ROOT/dist" \
     -o -path "$ROOT/rpmbuild" -o -path "$ROOT/sources" -o -path "$ROOT/development" \
     -o -path "$ROOT/governor-src" \
     -o -path "$ROOT/live-manager-src" \) -prune -o \
  -type f \( -name '*.sh' -o -path "$ROOT/packaging/bc250" \
     -o -path "$ROOT/install" \) -print0 > "$shell_file_list"
mapfile -d '' shell_files < "$shell_file_list"
for file in "${shell_files[@]}"; do
  bash -n "$file"
done

PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate.py

if [[ "$mode" == "--preflight" ]]; then
  echo "Repository preflight passed."
  exit 0
fi

# Isolate test modules so module-level mocks, environment changes, and cleanup
# cannot leak into later modules. A generous per-module timeout keeps a broken
# subprocess test from hanging validation indefinitely while still leaving the
# exact module visible in CI logs.
test_module_timeout="${BC250_TEST_MODULE_TIMEOUT:-120}"
[[ "$test_module_timeout" =~ ^[1-9][0-9]*$ ]] || {
  echo "BC250_TEST_MODULE_TIMEOUT must be a positive integer (seconds)." >&2
  exit 2
}
for test_file in "$ROOT"/tests/test_*.py; do
  echo "==> $(basename -- "$test_file")"
  PYTHONDONTWRITEBYTECODE=1 timeout --kill-after=5s "${test_module_timeout}s" \
    python3 -m unittest "$test_file"
done

echo "Repository validation passed."
