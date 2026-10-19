#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mode="${1:-all}"
case "$mode" in
  all|--preflight|--package) ;;
  -h|--help)
    cat <<'HELP'
Usage: scripts/validate.sh [--preflight|--package]
  default       run current-guidance/scope checks plus every repository test module
  --preflight   run release-critical source contracts and release-pipeline tests
  --package     run the package-critical test set declared in release-contract.json
HELP
    exit 0
    ;;
  *) echo "ERROR: unknown validation mode: $mode" >&2; exit 2 ;;
esac

# Syntax-check source-owned shell entrypoints only. Build/vendor/history trees are not product source.
while IFS= read -r -d '' file; do
  bash -n "$file"
done < <(
  find "$ROOT" \
    \( -path "$ROOT/.git" -o -path "$ROOT/.build" -o -path "$ROOT/build" -o -path "$ROOT/dist" \
       -o -path "$ROOT/rpmbuild" -o -path "$ROOT/sources" -o -path "$ROOT/vendor" \
       -o -path "$ROOT/development/handovers/archive" -o -path "$ROOT/development/model-runs" \
       -o -path "$ROOT/development/patchnotes" -o -path "$ROOT/governor-src" -o -path "$ROOT/live-manager-src" \
       -o -path "$ROOT/quality-checks/history" \) -prune -o \
    -type f \( -name '*.sh' -o -path "$ROOT/packaging/bc250" -o -path "$ROOT/install" \) -print0
)

PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate.py
bash scripts/check-clean-core-absence.sh "$ROOT"

test_module_timeout="${BC250_TEST_MODULE_TIMEOUT:-120}"
[[ "$test_module_timeout" =~ ^[1-9][0-9]*$ ]] || {
  echo "BC250_TEST_MODULE_TIMEOUT must be a positive integer (seconds)." >&2
  exit 2
}

run_test_file() {
  local test_file=$1 test_name test_log test_rc test_count
  test_name="$(basename -- "$test_file")"
  test_log="$(mktemp)"
  echo "==> $test_name"
  set +e
  PYTHONDONTWRITEBYTECODE=1 timeout --kill-after=5s "${test_module_timeout}s" \
    python3 -m unittest "$test_file" </dev/null >"$test_log" 2>&1
  test_rc=$?
  set -e
  if ((test_rc != 0)); then
    cat "$test_log" >&2
    rm -f -- "$test_log"
    return "$test_rc"
  fi
  test_count="$(sed -n 's/^Ran \([0-9][0-9]*\) tests\?.*/\1/p' "$test_log" | tail -1)"
  printf 'PASS (%s tests)\n' "${test_count:-count unavailable}"
  rm -f -- "$test_log"
}

run_test_set() {
  local failures=0 test_file
  for test_file in "$@"; do
    run_test_file "$test_file" || failures=$((failures + 1))
  done
  if ((failures != 0)); then
    echo "ERROR: $failures test module(s) failed." >&2
    return 1
  fi
}

mapfile -t all_tests < <(find "$ROOT/tests" -maxdepth 1 -type f -name 'test_*.py' -print | sort)
mapfile -t preflight_tests < <(python3 - <<'PY'
import json
from pathlib import Path
for item in json.loads(Path('release-contract.json').read_text())['validation']['preflight_tests']:
    print(item)
PY
)
mapfile -t package_tests < <(python3 - <<'PY'
import json
from pathlib import Path
# Keep the package hard gate centrally declared rather than duplicated in shell.
for item in json.loads(Path('release-contract.json').read_text())['validation']['package_critical_tests']:
    print(item)
PY
)

if [[ "$mode" == "--preflight" ]]; then
  preflight_failures=0
  bash scripts/check-current-guidance.sh "$ROOT" || preflight_failures=$((preflight_failures + 1))
  python3 development/scope.py check --quiet || preflight_failures=$((preflight_failures + 1))
  if ((preflight_failures != 0)); then
    echo "ERROR: release-critical governance/source checks failed." >&2
    exit 1
  fi
  run_test_set "${preflight_tests[@]}"
  echo "Release-critical preflight passed."
  exit 0
fi

if [[ "$mode" == "--package" ]]; then
  run_test_set "${package_tests[@]}"
  echo "Release-critical package validation passed."
  exit 0
fi

failures=0
bash scripts/check-current-guidance.sh "$ROOT" || failures=$((failures + 1))
python3 development/scope.py check --quiet || failures=$((failures + 1))
run_test_set "${all_tests[@]}" || failures=$((failures + 1))

if ((failures != 0)); then
  echo "Repository validation completed with $failures warning/failure group(s)." >&2
  exit 1
fi

echo "Repository validation passed."
