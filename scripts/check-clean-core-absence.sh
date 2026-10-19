#!/usr/bin/env bash
set -euo pipefail

root=${1:-.}
root=$(cd "$root" && pwd)

patterns='gfx1013|GFX1013|private RADV|/opt/bc250-gfx1013|PATCHED_BOOT_UNVERIFIED|STOCK_REBOOT_REQUIRED|stage-boot|patched amdgpu'

# Active/current surfaces. Do not scan WORKBENCH-STATE.json here: it is allowed to
# name deleted files and historical cleanup work. Validate its active schema/state
# separately in source tests.
paths=()
for p in cmd config tests docs README.md TLDR.md install uninstall.sh Makefile development/DEVELOPMENT-SCOPE.json development/VALIDATION-MATRIX.md development/TESTING-STRATEGY.md; do
  [[ -e "$root/$p" ]] && paths+=("$root/$p")
done

[[ ${#paths[@]} -gt 0 ]] || { echo "ERROR: no expected source surfaces found" >&2; exit 2; }

set +e
matches=$(grep -RsnE \
  --exclude='CHANGELOG.md' \
  --exclude-dir=patchnotes \
  --exclude-dir=archive \
  --exclude-dir=development/handovers/archive \
  "$patterns" "${paths[@]}" 2>/dev/null)
rc=$?
set -e

if [[ $rc -eq 0 && -n "$matches" ]]; then
  echo "ERROR: active clean-core surfaces still contain GFX-owned/current references:" >&2
  printf '%s\n' "$matches" >&2
  exit 1
fi
[[ $rc -eq 1 || $rc -eq 0 ]] || exit "$rc"

# Inspect only the active portion of the spec. Historical %changelog entries are
# evidence and are allowed to mention removed GFX work.
spec="$root/packaging/bc250-llm-server.spec"
if [[ -f "$spec" ]]; then
  set +e
  spec_matches=$(sed '/^%changelog/,$d' "$spec" | grep -nE "$patterns")
  spec_rc=$?
  set -e
  if [[ $spec_rc -eq 0 && -n "$spec_matches" ]]; then
    echo "ERROR: active RPM spec still contains GFX-owned references:" >&2
    printf '%s\n' "$spec_matches" >&2
    exit 1
  fi
  [[ $spec_rc -eq 1 || $spec_rc -eq 0 ]] || exit "$spec_rc"
fi

for forbidden in \
  "$root/gfx1013" \
  "$root/cmd/system/gfx1013.sh" \
  "$root/cmd/benchmark/gfx1013-ab.py" \
  "$root/docs/GFX1013.md"; do
  [[ ! -e "$forbidden" ]] || { echo "ERROR: GFX-owned path remains: ${forbidden#$root/}" >&2; exit 1; }
done

echo "Clean-core active-surface GFX absence check: PASS"
