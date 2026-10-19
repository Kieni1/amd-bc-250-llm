#!/usr/bin/env bash
set -u -o pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BC250_RELEASE_BUILD_DIR:-${BC250_BUILD_DIR:-$ROOT/build}}"
TOPDIR="${BC250_RELEASE_RPM_TOPDIR:-$ROOT/rpmbuild}"
DISTDIR="${BC250_RELEASE_DISTDIR:-$ROOT/dist}"
SOURCE_CACHE_DIR="${BC250_RELEASE_SOURCE_CACHE:-${BC250_SOURCE_DIR:-$ROOT/sources}}"
GFX_CACHE_DIR="${BC250_RELEASE_GFX_CACHE:-${BC250_GFX1013_CACHE_ROOT:-$SOURCE_CACHE_DIR/gfx1013}}"
OUT="${BC250_RELEASE_DIAGNOSTICS_DIR:-$BUILD_DIR/release-diagnostics}"
MAKE_ARGS=(
  "BUILD_DIR=$BUILD_DIR"
  "TOPDIR=$TOPDIR"
  "DISTDIR=$DISTDIR"
  "SOURCE_CACHE_DIR=$SOURCE_CACHE_DIR"
  "GFX_CACHE_DIR=$GFX_CACHE_DIR"
)
mkdir -p "$OUT"
: >"$OUT/summary.tsv"

failures=0
skips=0

run_gate() {
  local name=$1
  shift
  local log="$OUT/$name.log" rc
  printf '\n===== %s =====\n' "$name"
  set +e
  (cd "$ROOT" && "$@") > >(tee "$log") 2>&1
  rc=$?
  if ((rc == 0)); then
    printf 'PASS\t%s\n' "$name" | tee -a "$OUT/summary.tsv"
  else
    printf 'FAIL(%d)\t%s\n' "$rc" "$name" | tee -a "$OUT/summary.tsv"
    failures=$((failures + 1))
  fi
  return 0
}

skip_gate() {
  local name=$1 reason=$2
  printf 'SKIP\t%s\t%s\n' "$name" "$reason" | tee -a "$OUT/summary.tsv"
  skips=$((skips + 1))
}

# Clean once before creating diagnostics so later checks cannot erase earlier logs.
(cd "$ROOT" && make "${MAKE_ARGS[@]}" clean)
mkdir -p "$OUT"
: >"$OUT/summary.tsv"

run_gate sources make "${MAKE_ARGS[@]}" sources
run_gate sources-check make "${MAKE_ARGS[@]}" sources-check
run_gate gfx1013-kernel-build-check env BC250_GFX1013_DIAGNOSTICS_DIR="$OUT/gfx1013-kernel" make "${MAKE_ARGS[@]}" gfx1013-kernel-build-check
run_gate gfx1013-mesa-build-check make "${MAKE_ARGS[@]}" gfx1013-mesa-build-check
run_gate lint make "${MAKE_ARGS[@]}" lint
run_gate preflight make "${MAKE_ARGS[@]}" preflight
run_gate rpm make "${MAKE_ARGS[@]}" rpm </dev/null

shopt -s nullglob
binary_rpms=("$DISTDIR"/*.x86_64.rpm)
source_rpms=("$DISTDIR"/*.src.rpm)
if ((${#binary_rpms[@]})); then
  run_gate rpmlint rpmlint -c packaging/rpmlint.toml "${binary_rpms[@]}" "${source_rpms[@]}"
  run_gate check-rpm-payload make "${MAKE_ARGS[@]}" check-rpm-payload
else
  skip_gate rpmlint 'no binary RPM produced'
  skip_gate check-rpm-payload 'no binary RPM produced'
fi
if ((${#source_rpms[@]})); then
  run_gate check-srpm-rebuild make "${MAKE_ARGS[@]}" check-srpm-rebuild
else
  skip_gate check-srpm-rebuild 'no SRPM produced'
fi

printf '\n===== release diagnostics summary =====\n'
column -t -s $'\t' "$OUT/summary.tsv" 2>/dev/null || cat "$OUT/summary.tsv"
printf 'Logs: %s\n' "$OUT"
if ((failures)); then
  printf 'Diagnostic run found %d failing gate(s); %d dependent gate(s) skipped.\n' "$failures" "$skips" >&2
  exit 1
fi
printf 'Diagnostic run passed; %d dependent gate(s) skipped.\n' "$skips"
