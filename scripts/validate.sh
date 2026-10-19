#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mode="${1:-all}"
case "$mode" in
  all|--preflight|--package) ;;
  -h|--help)
    echo "Usage: scripts/validate.sh [--preflight|--package]"
    echo "  default       run source preflight plus all deterministic repository tests"
    echo "  --preflight   run cheap source/current-guidance plus host release-pipeline contracts"
    echo "  --package     run package-context deterministic tests, excluding host release-pipeline contracts"
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

PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate.py
bash scripts/check-clean-core-absence.sh "$ROOT"
bash scripts/check-current-guidance.sh "$ROOT"

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

release_pipeline_rel="$(python3 scripts/release-contract.py field validation.release_pipeline_test)"
release_pipeline_test="$ROOT/$release_pipeline_rel"
if [[ "$mode" == "--preflight" ]]; then
  run_test_file "$release_pipeline_test"
  echo "Repository preflight passed."
  exit 0
fi

for test_file in "$ROOT"/tests/test_*.py; do
  if [[ "$mode" == "--package" && "$test_file" == "$release_pipeline_test" ]]; then
    continue
  fi
  run_test_file "$test_file"
done

if [[ "$mode" == "--package" ]]; then
  echo "Package validation passed."
else
  echo "Repository validation passed."
fi
