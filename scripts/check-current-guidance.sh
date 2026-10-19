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

identity="$(python3 - "$root" <<'PY'
import json, pathlib, re, sys
root=pathlib.Path(sys.argv[1])
version=(root/'VERSION').read_text(encoding='utf-8').strip()
spec=(root/'packaging/bc250-llm-server.spec').read_text(encoding='utf-8')
version_match=re.search(r'^Version:\s*(\S+)\s*$', spec, re.MULTILINE)
release_match=re.search(r'^Release:\s*([^%\s]+)%\{\?dist\}\s*$', spec, re.MULTILINE)
assert version_match and release_match, 'spec Version/Release missing'
spec_version=version_match.group(1); rpm_release=release_match.group(1)
contract=json.loads((root/'release-contract.json').read_text())
workbench=json.loads((root/'WORKBENCH-STATE.json').read_text())
assert spec_version == version
assert contract['package']['version'] == version
assert contract['package']['rpm_release'] == rpm_release
nvr=f"{contract['package']['name']}-{version}-{rpm_release}"
assert workbench['release']['version'] == version
assert workbench['release']['rpm_release'] == rpm_release
assert workbench['release']['nvr'] == nvr
assert workbench['kind']=='release-workbench'
assert 'checkpoint' not in workbench
assert contract['authority']['primary']['kind']=='github-actions'
assert contract['authority']['primary']['selection_event']=='workflow_dispatch'
print(nvr)
PY
)" || fail=1

if [[ -n "${identity:-}" ]]; then
  need_text development/handovers/00_README_START_HERE.md "$identity" 'current NVR missing from handover'
  need_text development/VALIDATION-MATRIX.md "$identity" 'current NVR missing from validation matrix'
  need_text TLDR.md "$identity" 'current NVR missing from TLDR'
fi
need_text Makefile 'Run blocking Ruff and ShellCheck release preflight' 'make help must describe lint as blocking'
need_text development/VALIDATION-MATRIX.md 'configured rpmlint failure' 'validation matrix omits blocking rpmlint semantics'
need_text development/handovers/16_PRODUCT_GOAL_AND_ROADMAP.md 'bounded cleanup only where it removes real ownership/risk' 'product roadmap missing bounded simplification semantics'
need_text development/handovers/01_CURRENT_STATE_AND_NEXT_WORK.md 'low-cost core functionality' 'next core-functionality round missing'
need_text development/handovers/01_CURRENT_STATE_AND_NEXT_WORK.md 'product roadmap' 'office-intelligence roadmap follow-up missing'
need_text development/handovers/04_RELEASE_BUILD_AND_VALIDATION.md 'workflow_dispatch' 'selected GitHub authority rule missing'
need_text development/handovers/05_TESTING_STRATEGY.md 'Do not delete' 'test-retention rule missing'
need_text development/handovers/11_LONG_TERM_ENGINEERING_GUIDELINES.md 'Do not equate fewer tests' 'long-term test guideline missing'
need_text development/handovers/08_GREENFIELD_SIMPLIFICATION_PLAN.md 'not a transition phase and not the product roadmap' 'simplification must remain opportunistic rather than a prerequisite phase'
need_text development/handovers/01_CURRENT_STATE_AND_NEXT_WORK.md 'cleanup is not a prerequisite phase' 'current work must move directly to the product roadmap after baseline'
need_text development/TESTING-STRATEGY.md 'move directly into the product roadmap' 'testing strategy still orders a simplification phase before product work'

for stale in \
  'before starting the next simplification round' \
  'upcoming simplification round' \
  'Bounded simplification before the office-intelligence roadmap' \
  'freeze known-good stock-core baseline, then simplify'; do
  if grep -RIFq -- "$stale" \
      "$root/WORKBENCH-STATE.json" \
      "$root/development/TESTING-STRATEGY.md" \
      "$root/development/VALIDATION-MATRIX.md" \
      "$root/development/handovers/00_README_START_HERE.md" \
      "$root/development/handovers/01_CURRENT_STATE_AND_NEXT_WORK.md" \
      "$root/development/handovers/06_RUNTIME_AND_MODELS.md" \
      "$root/development/handovers/08_GREENFIELD_SIMPLIFICATION_PLAN.md"; then
    echo "ERROR: stale simplification-first guidance remains: $stale" >&2
    fail=1
  fi
done

if grep -RIEq '\bC[0-9]+([A-Z-]|\b)|0\.13\.1-1\.9' "$root/development/handovers" --exclude-dir=archive ; then
  echo 'ERROR: reconstruction-era milestone/release language remains in active handovers' >&2
  fail=1
fi

((fail == 0)) || exit 1
echo 'Current clean-core guidance check: PASS'
