# Development handovers

These handovers are Git/source-only coordination documents. They are not installed by
the binary RPM and are not package API contracts.

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
