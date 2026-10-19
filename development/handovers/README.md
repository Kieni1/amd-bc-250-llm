# Development handovers

These handovers are Git/source-only coordination documents. They are not installed by
the binary RPM and are not package API contracts.

## Read scope before handovers

`development/DEVELOPMENT-SCOPE.json` is the first file for routine development. It identifies current
active, boundary-active, frozen and archive-only domains. Historical release handovers and model-run
evidence remain in the tree, but archive-only material should not be loaded into a normal current batch.
Use `python3 development/scope.py check` to prove frozen/archive trees are unchanged and `scope.py map`
to select the smallest relevant handover/test surface.

Maintain three durable roles:

- `DEVELOPMENT-WORKFLOW.md` — stable rules for how development/review chats work;
- `MAIN-INTEGRATION-HANDOVER.md` — long durable technical state and integration memory;
- `OPERATIONS-HANDOVER.md` — current real-device/support state and next bounded hardware
  qualification.

Use `SPECIALIST-TESTING-HANDOVER.md` as a template when opening a temporary quality
specialist chat. Do not keep seven parallel specialist bibles permanently synchronized.
A specialist should read the newest source plus the relevant current docs and return a
bounded handoff to main integration.

Authority when information disagrees:

1. user's current instruction;
2. newest supplied source/package;
3. real-device evidence from the exact installed revision;
4. current test evidence;
5. these handovers;
6. older chats/logs/patches.

The main handover intentionally remains detailed about current hardware/software contracts,
resource constraints, model roles, current evidence boundaries and proven negative results.
Superseded release-by-release narration belongs in the changelog, `development/DECISIONS.md`,
and `development/model-runs/` rather than being copied indefinitely into every prompt.

Dated specialist handovers are evidence/method snapshots, not automatically current
workflow policy. When their procedural advice conflicts with `DEVELOPMENT-WORKFLOW.md`,
`development/DECISIONS.md`, current operator docs or newer source behavior, preserve the
historical handover but follow the newer authority. In particular, current experiment
scripts may print an evidence archive SHA-256 without creating `.sha256` sidecar files.

Dated specialist evidence handovers may also be retained here as source-only `.txt`
references when they capture a large campaign that should not be collapsed into the
operator documentation. The 2026-09-17 task/translation specialist snapshots were
retired after their durable evidence was integrated into model-run and decision records.

## Current main-integration continuity

- `CURRENT_WORK_NEXT_BUILD_HANDOVER_0.13.1-2.2.md` — current 2.2 corrective boundary: represent the safe patched-current/verified-stock-next transition consistently as a stock reboot requirement across status/reset/prepare/install without reopening proven GFX architecture.
- `CURRENT_WORK_NEXT_BUILD_HANDOVER_0.13.1-1.18.md` — historical 1.18 build/device evidence through successful prepare and the first deterministic stage-boot/dracut hierarchy failure; superseded by 2.0 for current source behavior.
- `../DEVELOPMENT-SCOPE.json` + `../scope.py` — first-stop current development scope and frozen-domain guard.
- `MAIN-INTEGRATION-HANDOVER.md` — durable project state/history.
- `MAIN_CHAT_WORKING_RULES_AND_INSTRUCTIONS.md` — current procedural authority and implemented contracts.
- `CURRENT_WORK_NEXT_BUILD_HANDOVER_0.13.1-1.17.md` — historical 1.17 release/device evidence, including the clean full-build baseline and first exact-device GFX prepare findings; superseded for current source behavior by the 1.18 handover.
- `TESTING-HANDOVER-0.13.1-1.17.md` — detailed 1.17 test authority retained as historical evidence; fresh 1.18 build/device qualification is required.
- `CURRENT_WORK_NEXT_BUILD_HANDOVER_0.13.1-1.16.md` — historical accepted 1.16 build-pipeline handover retained verbatim; do not treat it as current 1.18 authority.
- `RELEASE-TESTING-HANDOVER-0.13.1-1.3.md` — historical exact-package delta sequence; do not treat it as current 1.18 build authority.
- The 0.13.1-1.3 and 0.12.2-0.8 handovers remain historical evidence.
