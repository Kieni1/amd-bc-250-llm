#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
fail=0
for file in \
  00_README_START_HERE.md 01_CURRENT_STATE_AND_NEXT_WORK.md 02_MAIN_CHAT_WORKING_RULES.md \
  03_CORE_FUNCTIONALITY_CHECK.md 04_RELEASE_BUILD_AND_VALIDATION.md 05_TESTING_STRATEGY.md \
  08_GREENFIELD_SIMPLIFICATION_PLAN.md 11_LONG_TERM_ENGINEERING_GUIDELINES.md \
  16_PRODUCT_GOAL_AND_ROADMAP.md 17_RELEASE_CANDIDATE_EXECUTION_GATE.md; do
  [[ -f "$ROOT/$file" ]] || { echo "ERROR: missing current handover: $file" >&2; fail=1; }
done
NVR="$(python3 - "$ROOT/../.." <<'PY'
import pathlib, re, sys
root=pathlib.Path(sys.argv[1])
version=(root/'VERSION').read_text(encoding='utf-8').strip()
spec=(root/'packaging/bc250-llm-server.spec').read_text(encoding='utf-8')
match=re.search(r'^Release:\s*([^%\s]+)', spec, re.MULTILINE)
assert match
print(f'bc250-llm-server-{version}-{match.group(1)}')
PY
)" || fail=1
grep -Fq "$NVR" "$ROOT/00_README_START_HERE.md" || { echo 'ERROR: current NVR missing' >&2; fail=1; }
grep -Fq 'low-cost core functionality' "$ROOT/01_CURRENT_STATE_AND_NEXT_WORK.md" || { echo 'ERROR: next core check missing' >&2; fail=1; }
grep -Fq 'product roadmap' "$ROOT/01_CURRENT_STATE_AND_NEXT_WORK.md" || { echo 'ERROR: office-intelligence roadmap follow-up missing' >&2; fail=1; }
grep -Fq 'Do not delete tests' "$ROOT/00_README_START_HERE.md" || { echo 'ERROR: retained-test policy missing' >&2; fail=1; }
if grep -RIEq '\bC[0-9]+([A-Z-]|\b)|0\.13\.1-1\.9' "$ROOT" --exclude-dir=archive; then
  echo 'ERROR: reconstruction-era milestone/release language remains in active handovers' >&2
  fail=1
fi
((fail == 0)) || exit 1
echo 'Current BC-250 handover validation: PASS'
