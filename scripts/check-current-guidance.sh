#!/usr/bin/env bash
set -Eeuo pipefail
root="${1:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
fail=0

need_file() {
  [[ -f "$root/$1" ]] || { echo "ERROR: missing current guidance file: $1" >&2; fail=1; }
}
need_text() {
  local file=$1 text=$2 label=$3
  grep -Fq -- "$text" "$root/$file" || { echo "ERROR: $label" >&2; fail=1; }
}

for file in \
  VERSION release-contract.json WORKBENCH-STATE.json \
  development/handovers/00_README_START_HERE.md \
  development/handovers/01_CURRENT_STATE_AND_NEXT_WORK.md \
  development/handovers/02_MAIN_CHAT_WORKING_RULES.md \
  development/handovers/03_CORE_FUNCTIONALITY_CHECK.md \
  development/handovers/04_RELEASE_BUILD_AND_VALIDATION.md \
  development/handovers/05_TESTING_STRATEGY.md \
  development/handovers/08_GREENFIELD_SIMPLIFICATION_PLAN.md \
  development/handovers/11_LONG_TERM_ENGINEERING_GUIDELINES.md; do
  need_file "$file"
done

[[ "$(cat "$root/VERSION")" == "0.14.1" ]] || { echo 'ERROR: VERSION must be 0.14.1' >&2; fail=1; }
grep -Eq '^Version:[[:space:]]+0\.14\.1$' "$root/packaging/bc250-llm-server.spec" || { echo 'ERROR: spec Version mismatch' >&2; fail=1; }
grep -Eq '^Release:[[:space:]]+1%\{\?dist\}$' "$root/packaging/bc250-llm-server.spec" || { echo 'ERROR: spec Release mismatch' >&2; fail=1; }

python3 - "$root" <<'PY' || fail=1
import json, pathlib, sys
root=pathlib.Path(sys.argv[1])
contract=json.loads((root/'release-contract.json').read_text())
workbench=json.loads((root/'WORKBENCH-STATE.json').read_text())
assert contract['package']['version']=='0.14.1'
assert contract['package']['rpm_release']=='1'
assert workbench['release']['nvr']=='bc250-llm-server-0.14.1-1'
assert workbench['kind']=='release-workbench'
assert 'checkpoint' not in workbench
assert contract['authority']['primary']['kind']=='github-actions'
assert contract['authority']['primary']['selection_event']=='workflow_dispatch'
PY

need_text development/handovers/00_README_START_HERE.md 'bc250-llm-server-0.14.1-1' 'current NVR missing from handover'
need_text development/handovers/01_CURRENT_STATE_AND_NEXT_WORK.md 'low-cost core functionality' 'next core-functionality round missing'
need_text development/handovers/01_CURRENT_STATE_AND_NEXT_WORK.md 'product roadmap' 'office-intelligence roadmap follow-up missing'
need_text development/handovers/04_RELEASE_BUILD_AND_VALIDATION.md 'workflow_dispatch' 'selected GitHub authority rule missing'
need_text development/handovers/05_TESTING_STRATEGY.md 'Do not delete' 'test-retention rule missing'
need_text development/handovers/11_LONG_TERM_ENGINEERING_GUIDELINES.md 'Do not equate fewer tests' 'long-term test guideline missing'

if grep -RIEq '\bC[0-9]+([A-Z-]|\b)|0\.13\.1-1\.9' "$root/development/handovers" --exclude-dir=archive --exclude='SHA256SUMS.txt'; then
  echo 'ERROR: reconstruction-era milestone/release language remains in active handovers' >&2
  fail=1
fi

((fail == 0)) || exit 1
echo 'Current clean-core guidance check: PASS'
