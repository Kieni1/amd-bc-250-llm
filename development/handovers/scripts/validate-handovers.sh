#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
fail=0
for file in \
  00_README_START_HERE.md 01_CURRENT_STATE_AND_NEXT_WORK.md 02_MAIN_CHAT_WORKING_RULES.md \
  03_CORE_FUNCTIONALITY_CHECK.md 04_RELEASE_BUILD_AND_VALIDATION.md 05_TESTING_STRATEGY.md \
  08_GREENFIELD_SIMPLIFICATION_PLAN.md 11_LONG_TERM_ENGINEERING_GUIDELINES.md \
  16_PRODUCT_GOAL_AND_ROADMAP.md 17_RELEASE_CANDIDATE_EXECUTION_GATE.md; do
  [[ -f "$ROOT/$file" ]] || { echo "ERROR: missing retained handover memory: $file" >&2; fail=1; }
done
# Handovers are retained engineering memory, not volatile release identity authority.
# Validate durable safety/engineering content without forcing every RPM bump to
# rewrite historical/current-chat prose.
grep -Fq 'retained engineering memory' "$ROOT/00_README_START_HERE.md" || { echo 'ERROR: handover memory boundary missing' >&2; fail=1; }
grep -Fq 'Do not delete tests' "$ROOT/00_README_START_HERE.md" || { echo 'ERROR: retained-test policy missing' >&2; fail=1; }
grep -Fq 'workflow_dispatch' "$ROOT/04_RELEASE_BUILD_AND_VALIDATION.md" || { echo 'ERROR: GitHub selection authority missing' >&2; fail=1; }
grep -Fq 'RAG/document workflow quality' "$ROOT/16_PRODUCT_GOAL_AND_ROADMAP.md" || { echo 'ERROR: product roadmap memory missing' >&2; fail=1; }
if grep -RIEq '\bC[0-9]+([A-Z-]|\b)|0\.13\.1-1\.9' "$ROOT" --exclude-dir=archive; then
  echo 'ERROR: reconstruction-era milestone/release language remains in active handover memory' >&2
  fail=1
fi
((fail == 0)) || exit 1
echo 'BC-250 retained handover memory validation: PASS'
