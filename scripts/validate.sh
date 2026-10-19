#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mode="${1:-all}"
case "$mode" in
  all|--preflight|--package) ;;
  -h|--help)
    echo "Usage: scripts/validate.sh [--preflight|--package]"
    echo "  default       strict developer validation: governance/current-guidance plus all deterministic tests"
    echo "  --preflight   release-critical source contracts plus host release-pipeline tests"
    echo "  --package     small release-critical package test set for RPM %check"
    exit 0
    ;;
  *) echo "ERROR: unknown validation mode: $mode" >&2; exit 2 ;;
esac

shell_file_list="$(mktemp)"
trap 'rm -f -- "$shell_file_list"' EXIT
find "$ROOT" \
  \( -path "$ROOT/.git" -o -path "$ROOT/.build" -o -path "$ROOT/build" -o -path "$ROOT/dist" \
     -o -path "$ROOT/rpmbuild" -o -path "$ROOT/sources" -o -path "$ROOT/development" \
     -o -path "$ROOT/governor-src" -o -path "$ROOT/live-manager-src" \) -prune -o \
  -type f \( -name '*.sh' -o -path "$ROOT/packaging/bc250" -o -path "$ROOT/install" \) -print0 > "$shell_file_list"
mapfile -d '' shell_files < "$shell_file_list"
for file in "${shell_files[@]}"; do
  bash -n "$file"
done

# Hard release/source checks only. Development-scope hashes and current-guidance
# checks belong to strict developer validation, not to RPM artifact production.
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
    if ! run_test_file "$test_file"; then
      failures=$((failures + 1))
    fi
  done
  if ((failures != 0)); then
    echo "ERROR: $failures test module(s) failed." >&2
    return 1
  fi
}

release_pipeline_rel="$(python3 scripts/release-contract.py field validation.release_pipeline_test)"
release_pipeline_test="$ROOT/$release_pipeline_rel"

if [[ "$mode" == "--preflight" ]]; then
  run_test_set "$release_pipeline_test"
  echo "Release-critical preflight passed."
  exit 0
fi

if [[ "$mode" == "--package" ]]; then
  mapfile -t package_tests < <(python3 - <<'PY'
import json
from pathlib import Path
root = Path.cwd()
data = json.loads((root / "release-contract.json").read_text(encoding="utf-8"))
for relative in data["validation"]["package_critical_tests"]:
    print(root / relative)
PY
  )
  run_test_set "${package_tests[@]}"
  echo "Release-critical package validation passed."
  exit 0
fi

# Strict developer validation remains available, but is deliberately not part of
# make release-gate. It aggregates all failures so one run exposes the whole set.
governance_failures=0
if ! bash scripts/check-current-guidance.sh "$ROOT"; then
  governance_failures=$((governance_failures + 1))
fi
if ! python3 development/scope.py check --quiet; then
  governance_failures=$((governance_failures + 1))
fi

mapfile -t all_tests < <(printf '%s\n' "$ROOT"/tests/test_*.py)
test_failures=0
if ! run_test_set "${all_tests[@]}"; then
  test_failures=1
fi

if ((governance_failures != 0 || test_failures != 0)); then
  echo "Repository validation completed with warnings/failures: governance=$governance_failures tests=$test_failures" >&2
  exit 1
fi

echo "Repository validation passed."
