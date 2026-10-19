#!/usr/bin/env bash
set -euo pipefail

root=${1:-.}
root=$(cd "$root" && pwd)
fail=0

report_match() {
  local label=$1 file=$2 regex=$3
  [[ -f "$file" ]] || return 0
  set +e
  local out
  out=$(grep -nEi "$regex" "$file" 2>/dev/null)
  local rc=$?
  set -e
  if [[ $rc -eq 0 && -n "$out" ]]; then
    echo "ERROR: stale current guidance in $label (${file#$root/}):" >&2
    printf '%s\n' "$out" >&2
    fail=1
  elif [[ $rc -ne 1 && $rc -ne 0 ]]; then
    exit "$rc"
  fi
}

require_match() {
  local label=$1 file=$2 regex=$3 description=$4
  if [[ ! -f "$file" ]]; then
    echo "ERROR: missing current guidance file for $label (${file#$root/})" >&2
    fail=1
    return 0
  fi
  set +e
  grep -nEi "$regex" "$file" >/dev/null 2>&1
  local rc=$?
  set -e
  if [[ $rc -eq 1 ]]; then
    echo "ERROR: current guidance contract missing in $label (${file#$root/}): $description" >&2
    fail=1
  elif [[ $rc -ne 0 ]]; then
    exit "$rc"
  fi
}

# Current testing strategy must not instruct the clean-core lane to exercise the
# removed GFX lifecycle. Historical/archive documents are intentionally not scanned.
report_match \
  'development testing strategy' \
  "$root/development/TESTING-STRATEGY.md" \
  'GFX disabled|prepared/enabled-state rollback|prepare --check|one-shot patched boot|BC-250 RADV identity|stale/new-stock-kernel Ollama guard|disable/reset'

# The in-repository handover index/current handovers must not still claim 1.3 is the
# current release target/boundary. Old versioned files may remain as history, but
# current pointers must be replaced or explicitly archived.
report_match \
  'handover index' \
  "$root/development/handovers/README.md" \
  '1\.3.*current|current.*1\.3|current release implementation/device-qualification boundary'

main_handover="$root/development/handovers/MAIN-INTEGRATION-HANDOVER.md"
main_rules="$root/development/handovers/MAIN_CHAT_WORKING_RULES_AND_INSTRUCTIONS.md"
current_work="$root/development/handovers/CURRENT_WORK_CLEAN_CORE_RECONSTRUCTION.md"

report_match \
  'main integration handover' \
  "$main_handover" \
  'Release target:.*0\.13\.1-1\.3|current release target:.*0\.13\.1-1\.3|while fixing the C3 blockers|substantially completes C2'

report_match \
  'main-chat rules' \
  "$main_rules" \
  'Current release target:.*0\.13\.1-1\.3|Release target:.*0\.13\.1-1\.3|active correction base.*reviewed C3 proposition|amd-bc-250-llm-clean-core-C3\(1\)\.zip|08b7c19104a1c29a6fd6c54e7df1fc4688d741420180b78a054e33d11f240d1b'

report_match \
  'current work handover' \
  "$current_work" \
  'C1[^\n]*substantially complete|C2[^\n]*substantially complete'

# Continuity contract: the current authority must positively identify the accepted
# checkpoint/status/next milestone, test baseline and build authority, not merely
# avoid stale text.
require_match \
  'main-chat rules' \
  "$main_rules" \
  'Current C8 source identity:.*bc250-llm-server-0\.14\.1-1.*SOURCE-READY.*GitHub build pending' \
  'C8 must name the new 0.14.1-1 source identity and pending authoritative GitHub build'
require_match \
  'main-chat rules' \
  "$main_rules" \
  'C7 source predecessor:.*C6.*Immutable behavioral predecessor:.*C5-D.*Release-hardening predecessor:.*C5-C.*Classification predecessor:.*C4.*Clean-core structural predecessor:.*C3-R1' \
  'C7/C6, C5-D, C5-C, C4 and C3-R1 must remain identified by their precise predecessor roles'
require_match 'main-chat rules' "$main_rules" '^C0:[[:space:]]*PASS$' 'C0 must be PASS'
require_match 'main-chat rules' "$main_rules" '^C1:[[:space:]]*PASS$' 'C1 must be PASS'
require_match 'main-chat rules' "$main_rules" '^C2:[[:space:]]*PASS$' 'C2 must be PASS'
require_match 'main-chat rules' "$main_rules" '^C3:[[:space:]]*PASS$' 'C3 must be PASS'
require_match 'main-chat rules' "$main_rules" '^C4:[[:space:]]*PASS$' 'C4 must be PASS'
require_match 'main-chat rules' "$main_rules" '^C5-A:[[:space:]]*PASS$' 'C5-A must be PASS'
require_match 'main-chat rules' "$main_rules" '^C5-B:[[:space:]]*PASS$' 'C5-B must be PASS'
require_match 'main-chat rules' "$main_rules" '^C5-C:[[:space:]]*PASS$' 'C5-C must be PASS'
require_match 'main-chat rules' "$main_rules" '^C5-D:[[:space:]]*PASS$' 'C5-D must be PASS'
require_match 'main-chat rules' "$main_rules" '^C6:[[:space:]]*PASS$' 'C6 must be PASS'
require_match 'main-chat rules' "$main_rules" '^C7:[[:space:]]*PASS$' 'C7 must be PASS'
require_match \
  'main-chat rules' \
  "$main_rules" \
  'Active next action:.*C8.*authoritative Fedora 44 GitHub Actions build' \
  'active next work must be the authoritative C8 Fedora 44 GitHub Actions build'
require_match \
  'main-chat rules' \
  "$main_rules" \
  'Current C8 source deterministic baseline:.*619/619.*598/598.*21/21' \
  'current guidance must record the validated C8 source-test baseline'
require_match \
  'main integration handover' \
  "$main_handover" \
  'C8 source identity is now assigned:.*bc250-llm-server-0\.14\.1-1' \
  'integration handover must record the assigned C8 release identity'
require_match 'current work handover' "$current_work" '^## 5\. C1 .* PASS$' 'C1 heading must be PASS'
require_match 'current work handover' "$current_work" '^## 6\. C2 .* PASS$' 'C2 heading must be PASS'
require_match 'current work handover' "$current_work" '^## 9\. C4 .* PASS$' 'C4 heading must be PASS'
require_match 'current work handover' "$current_work" '^## 11\. C6 .* PASS$' 'C6 heading must be PASS'
require_match 'current work handover' "$current_work" '^## 12\. C7 .* PASS$' 'C7 heading must be PASS'
require_match 'current work handover' "$current_work" 'immediate accepted source predecessor is .*C7.*PASS' 'CURRENT_WORK must preserve C7 as the accepted source predecessor'
require_match 'current work handover' "$current_work" 'active next action is the .*C8 authoritative Fedora 44 GitHub Actions build' 'CURRENT_WORK must identify the C8 authoritative GitHub build as the next action'
require_match \
  'current work handover' \
  "$current_work" \
  '1\. \*\*C5-A — PASS — low-risk correctness/supportability:\*\*.*Open WebUI inaccessible-path handling.*maintenance/restore sourceability.*shell nounset fix.*test-isolation fix.*Web interface.*transition wording.*package NEVRA.*Vulkan environment verification' \
  'CURRENT_WORK must preserve the exact completed C5-A correctness/supportability cluster from the donor ledger'
require_match \
  'current work handover' \
  "$current_work" \
  '2\. \*\*C5-B — PASS — model/installer UX:\*\*.*combined-catalog model-install workflow.*hard cancel/no-mutation behavior.*installer grouping.*desired/observed Ollama reconciliation.*one-next-action.*TTY/`NO_COLOR`.*`health` compatibility alias' \
  'CURRENT_WORK must preserve the exact completed C5-B model/installer UX cluster from the donor ledger'
require_match \
  'current work handover' \
  "$current_work" \
  '3\. \*\*C5-C — PASS — release/build hardening:\*\*.*frozen Source0/spec.*clean-source identity recheck.*deterministic archive/build-cache exclusions.*core-only release contract.*split checksum manifests.*unprivileged Fedora build.*package test layering.*transformed payload proof.*machine-readable release evidence' \
  'CURRENT_WORK must preserve the completed C5-C release/build-hardening cluster from the donor ledger'
require_match \
  'current work handover' \
  "$current_work" \
  '4\. \*\*C5-D — PASS — benchmark semantics:\*\*.*visible-response identity.*hidden thinking.*never hashes an empty visible response.*`INCOMPLETE`.*without weakening.*thresholds' \
  'CURRENT_WORK must preserve the completed C5-D benchmark-semantics correction from the donor ledger'
report_match \
  'current work handover' \
  "$current_work" \
  '^###[[:space:]]+Group A|Group A — low-risk UX/supportability|model-install safe cancel/prompt/grammar wording'

# Frozen predecessor identity + current deterministic baseline. C6 may add documentation
# regressions, but it must never rewrite the immutable accepted C5-D freeze.
require_match 'main integration handover' "$main_handover" '25be3783716451c84f54209ae16a38c5de1ef1675c4b579fd02cfff08865c710' 'C5-D archive SHA-256 must remain recorded'
require_match 'main integration handover' "$main_handover" 'e43ab0244de09bc4fc1981db36d956860e6d01715566fe91a9597c869b59e651' 'C5-D canonical manifest must remain recorded'
require_match 'main integration handover' "$main_handover" 'source files:[[:space:]]*362' 'C5-D source-file count must remain recorded'
require_match 'main-chat rules' "$main_rules" '613/613 deterministic tests across 20 modules' 'C5-D immutable deterministic baseline must remain recorded'
require_match 'testing handover' "$root/development/handovers/TESTING-HANDOVER.md" '594/594 package-context tests across 19 modules plus 19/19 host release-pipeline tests' 'C5-D package/host split must remain recorded'
require_match 'main integration handover' "$main_handover" '617/617 deterministic tests across 20 modules' 'C6/C7 total deterministic baseline must be recorded'
require_match 'testing handover' "$root/development/handovers/TESTING-HANDOVER.md" '598/598 package-context tests across 19 modules' 'C6/C7 package-context baseline must be recorded'

# C6 documentation/secondary-file authority contract.
require_match 'handover index' "$root/development/handovers/README.md" 'Current authority — only these five files may direct new main-chat work' 'handover index must define the five-file current authority boundary'
require_match 'handover index' "$root/development/handovers/README.md" 'Every version-numbered handover.*historical evidence only' 'versioned handovers must be explicitly historical'
require_match 'validation matrix' "$root/development/VALIDATION-MATRIX.md" 'Current clean-core execution summary' 'validation matrix must lead with current clean-core execution guidance'
require_match 'validation matrix' "$root/development/VALIDATION-MATRIX.md" 'Historical qualification matrix — evidence only' 'legacy validation material must be marked historical'
report_match 'validation matrix' "$root/development/VALIDATION-MATRIX.md" 'capture fresh 1\.9 A1 before GFX B/rollback/A2'
require_match 'testing strategy' "$root/development/TESTING-STRATEGY.md" 'Current clean-core execution plan' 'testing strategy must lead with the current clean-core plan'
require_match 'testing strategy' "$root/development/TESTING-STRATEGY.md" 'Historical 0\.13\.1-1\.9 qualification boundary' 'legacy 1.9 qualification boundary must be historical'
require_match 'Ollama documentation' "$root/docs/OLLAMA.md" 'OLLAMA_VULKAN=1' 'Ollama docs must state Vulkan enablement'
require_match 'Ollama documentation' "$root/docs/OLLAMA.md" 'OLLAMA_IGPU_ENABLE=1' 'Ollama docs must state iGPU enablement'
require_match 'Ollama documentation' "$root/docs/OLLAMA.md" 'GGML_VK_VISIBLE_DEVICES=0' 'Ollama docs must state the visible Vulkan device contract'

# Build authority contract. GitHub Actions is the normal Fedora RPM build path;
# local execution exists only as backup/reproduction. This explicitly rejects
# the donor 2.2 local-only build authority.
require_match \
  'main-chat rules' \
  "$main_rules" \
  'primary RPM build path is the Fedora 44 GitHub Actions workflow' \
  'GitHub Actions must remain the primary RPM build path'
require_match \
  'main-chat rules' \
  "$main_rules" \
  'Local builds are backup/reproduction only' \
  'local builds must remain backup/reproduction only'
require_match \
  'release build handover' \
  "$root/development/handovers/RELEASE_BUILD_AND_VALIDATION_HANDOVER.md" \
  'primary RPM build path is the repository GitHub Actions workflow' \
  'release handover must identify GitHub Actions as primary'
require_match 'testing handover' "$root/development/handovers/TESTING-HANDOVER.md" 'GitHub Actions / Fedora 44.*primary release-build authority' 'testing handover must identify GitHub Actions/Fedora 44 as primary release-build authority'
require_match 'testing handover' "$root/development/handovers/TESTING-HANDOVER.md" 'Local Fedora workstation.*secondary reproduction' 'testing handover must identify local Fedora as secondary reproduction'
require_match 'testing handover' "$root/development/handovers/TESTING-HANDOVER.md" '`model install` Enter-cancel/no-mutation passes' 'device criteria must require the already-ported model-install cancel/no-mutation behavior'
require_match 'main-chat rules' "$main_rules" 'bc250-llm-server-0\.14\.1-1' 'current guidance must bind the C8 source identity'
require_match 'release build handover' "$root/development/handovers/RELEASE_BUILD_AND_VALIDATION_HANDOVER.md" 'workflow_dispatch.*release-selection\.json' 'release handover must distinguish explicit selected workflow-dispatch authority from ordinary CI'
require_match 'release build handover' "$root/development/handovers/RELEASE_BUILD_AND_VALIDATION_HANDOVER.md" 'BUILD_DIR=/some/path' 'release handover must document BUILD_DIR as the supported Make-level custom build root'
require_match \
  'release build handover' \
  "$root/development/handovers/RELEASE_BUILD_AND_VALIDATION_HANDOVER.md" \
  'Local build is backup/reproduction only' \
  'release handover must keep local build as backup/reproduction only'
require_match \
  'release build handover' \
  "$root/development/handovers/RELEASE_BUILD_AND_VALIDATION_HANDOVER.md" \
  'selected run becomes the artifact authority' \
  'release handover must distinguish CI runs from the selected artifact-authority run'
require_match \
  'release build handover' \
  "$root/development/handovers/RELEASE_BUILD_AND_VALIDATION_HANDOVER.md" \
  'Source0 is built from the Git tracked-file set only' \
  'release handover must require tracked-only Source0 in Git worktrees'
require_match \
  'release build handover' \
  "$root/development/handovers/RELEASE_BUILD_AND_VALIDATION_HANDOVER.md" \
  'HEAD.*GITHUB_SHA' \
  'release handover must require GitHub checkout SHA identity'
require_match \
  'release build handover' \
  "$root/development/handovers/RELEASE_BUILD_AND_VALIDATION_HANDOVER.md" \
  'release-evidence\.json' \
  'release handover must require machine-readable release evidence'

report_match \
  'main-chat rules' \
  "$main_rules" \
  'primary RPM build path.*build-local\.sh|authoritative.*build-local\.sh|sole authority.*local build'
report_match \
  'release build handover' \
  "$root/development/handovers/RELEASE_BUILD_AND_VALIDATION_HANDOVER.md" \
  'primary RPM build path.*build-local\.sh|authoritative.*build-local\.sh|sole authority.*local build'

if [[ $fail -ne 0 ]]; then
  exit 1
fi

echo 'Current clean-core guidance check: PASS'
