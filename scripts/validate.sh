#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mode="${1:-all}"
case "$mode" in
  all|--preflight|--package) ;;
  -h|--help)
    cat <<'EOF'
Usage: scripts/validate.sh [--preflight|--package]
  default       strict developer validation: governance plus the lean test suite
  --preflight   release-critical source contracts only
  --package     release-critical core smoke/contracts for RPM %check
EOF
    exit 0
    ;;
  *) echo "ERROR: unknown validation mode: $mode" >&2; exit 2 ;;
esac

# Syntax only for source-owned shell entrypoints. Generated, vendored, historical
# development and build trees are deliberately outside this gate.
while IFS= read -r -d '' file; do
  bash -n "$file"
done < <(
  find "$ROOT" \
    \( -path "$ROOT/.git" -o -path "$ROOT/.build" -o -path "$ROOT/build" -o -path "$ROOT/dist" \
       -o -path "$ROOT/rpmbuild" -o -path "$ROOT/sources" -o -path "$ROOT/development" \
       -o -path "$ROOT/governor-src" -o -path "$ROOT/live-manager-src" \
       -o -path "$ROOT/quality-checks/history" \) -prune -o \
    -type f \( -name '*.sh' -o -path "$ROOT/packaging/bc250" -o -path "$ROOT/install" \) -print0
)

PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate.py
bash scripts/check-clean-core-absence.sh "$ROOT"

if [[ "$mode" == "--preflight" ]]; then
  echo "Release-critical preflight passed."
  exit 0
fi

if [[ "$mode" == "--package" ]]; then
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_core.py </dev/null
  echo "Release-critical package validation passed."
  exit 0
fi

failures=0
bash scripts/check-current-guidance.sh "$ROOT" || failures=$((failures + 1))
python3 development/scope.py check --quiet || failures=$((failures + 1))
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py' </dev/null || failures=$((failures + 1))

if ((failures != 0)); then
  echo "Repository validation completed with $failures warning/failure group(s)." >&2
  exit 1
fi

echo "Repository validation passed."
