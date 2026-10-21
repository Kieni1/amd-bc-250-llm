# Exact-RPM testing sidechat handover — 0.14.1-1.5

## Purpose

This file is the start point for exact-artifact testing of the next release. It remains deliberately detailed so the testing chat does not rediscover package history, reopen closed architecture decisions, or confuse source/build/device evidence.

The objective is:

> Determine whether the exact selected Fedora 44 GitHub RPM for `bc250-llm-server-0.14.1-1.5` preserves the device-proven 1.4 stock-core appliance behavior, correctly implements the reviewed 1.5 fixes/additions, and completes the reboot-persistence / ordinary-user boundary that remained pending after the 1.4 Block 3 milestone.

The exact 1.4 device campaign is a high-value regression baseline. It is **not** acceptance of different 1.5 bytes.

If a real blocker appears, stop broadening scope and capture the smallest authoritative failure needed to diagnose it. Harness uncertainty is REVIEW/HARNESS evidence, not permission to label the package broken.

## Authority and evidence boundary

Current authority order:

```text
explicit current user instruction
> exact current source / commit
> selected GitHub Fedora 44 build evidence for those bytes
> exact installed-device evidence for the exact selected RPM
> current handovers
> historical/archive evidence
```

Keep evidence states separate:

```text
SOURCE-CANDIDATE
SOURCE-VALIDATED
BUILD-VALIDATED
DEVICE-VALIDATED
ACCEPTED
```

Expected state when this sidechat starts:

```text
source:  0.14.1-1.5 source candidate validated by the integration chat
build:   exact selected 1.5 GitHub authority run must be recorded
1.4 device baseline: Blocks 1-3 device-proven on its exact RPM hash
1.5 device: pending; no 1.4 PASS transfers automatically
```

Before device mutation, record the selected 1.5 workflow run, source commit, RPM/SRPM hashes and release evidence. Never infer them from filenames.

## Current package identity

```text
Name:          bc250-llm-server
Version:       0.14.1
RPM Release:   1.5
Target:        Fedora 44
Expected NVR:  bc250-llm-server-0.14.1-1.5
```

Current runtime pins remain:

```text
Ollama:        0.40.6
Open WebUI:    0.12.3
Tika:          4.1.0-full
Governor:      0.4.13
```

Graphics/runtime architecture remains stock Fedora AMDGPU/Mesa. There is no package-owned GFX1013 patched-kernel/private-RADV path to qualify.

## Device/testing working assumptions

These were established during the successful 1.4 campaign and remain the normal testing contract unless the user changes them:

- device baseline is a fresh, updated Fedora installation with `llm_admin` and SSH already configured; do not repeat OS/user/SSH provisioning;
- work as `llm_admin` from `/home/llm_admin` unless a root-only action explicitly needs `sudo`;
- Internet access is intentionally available during install and pre-v1 qualification;
- this board's 40-CU unlock is already proven stable; verify 40/40 live routing and persistence, but do not reopen broad 40-CU viability qualification without new evidence;
- prefer long coherent test blocks except at real reboot, destructive-state, rollback, credential or first-authoritative-failure boundaries;
- UX wording is acceptance surface: prompts, warnings, errors, status/health/verify summaries, next actions and human/machine consistency matter;
- device-delivery archives contain only device files; main-chat handover notes remain separate;
- source-back every blocking assertion and compare semantic state rather than incidental ordering/serialization.

## 1.4 exact-device regression baseline

The exact 1.4 RPM was:

```text
bc250-llm-server-0:0.14.1-1.4.fc44.x86_64
SHA-256 87e02e310023e6c9af22e30a92ad38ee8e69ebe9ed11f41019fd926663ae9525
```

Blocks 1–3 established, on those exact bytes:

- guided install and required primary reboot convergence;
- reviewed TTM arguments active;
- 40/40 CU routing, exact saved/live profile and boot restore enabled;
- `rpm -V` clean and no failed systemd units;
- `status` HEALTHY, `health` PASS, `verify` 61/0/0/0 after convergence;
- Ollama 0.40.6 main/task/embedding topology and package-owned local-GGUF registration persistence across supported restart;
- `/api/show` semantic stability across restart;
- visible main generation with adequate default-thinking budget and explicit `think=false` control;
- normal-mode agent lane intentionally inactive;
- Open WebUI 0.12.3 desired-state verification, local-first policy and idempotent re-apply;
- managed RAG lifecycle add/modify/replace/delete/prune/provenance behavior;
- package-owned Open WebUI RAG qualification 3/3;
- canonical DE↔FR translation qualification 12/12, including correct integrity-withholding behavior for a modality-strengthening result;
- production use-case benchmark 6/6;
- marker-correlated Open WebUI → Ollama Advanced request with `options.num_predict=6144`;
- final runtime identity matches for Open WebUI/Tika and no OOM event in Block 3.

See `20_DEVICE_QUALIFICATION_1_4.md` for the consolidated evidence and remaining boundary.

## Confirmed 1.4 findings implemented in 1.5

### Pre-convergence status semantics

1.4 could describe an intentional migration/publication hold as `package runtime identity mismatch/unavailable`. 1.5 keeps the strict identity check but adds an explicit setup/publication state so intentional convergence can report:

```text
SETUP INCOMPLETE — package runtime convergence pending
```

while a real observed mismatch remains a mismatch and unrelated identity unavailability remains an availability warning. The JSON status contract is correspondingly advanced and must agree with human output.

### Guided-installer Ollama version parsing

1.4 could render:

```text
Ollama observed: instance
0.40.6
```

when a transient multi-line `ollama --version` response contained a connection/status line. 1.5 extracts one normalized semantic version token (or an explicit unknown state); arbitrary trailing words must never become a version.

### Harness lessons that are *not* product fixes

Do not regress these testing lessons:

1. A 48-token visible-answer smoke on a thinking-capable model exhausted its entire output budget in hidden reasoning. Classify that as harness-budget/incomplete evidence; use an adequate budget or explicit `think=false` when visible output is the contract.
2. Ollama `/api/show` may reorder non-empty lines inside the serialized `parameters` string across restart. Compare the semantic multiset/values, preserving duplicates; do not use incidental line order as a product-state oracle.

## Optional 1.5 challenger additions

1.5 adds optional catalog entries without changing recommended/production defaults:

```text
exp-lfm25-8b-a1b-unsloth-q6-k-xl
agentic-lfm25-24b-a2b-unsloth-q3-k-xl
exp-gemma4-12b-hauhaucs-uncensored-q4-k-m
exp-minicpm-v47-1b-openbmb-q4-k-m
```

The first device pass should check catalog/registration integrity and bounded usability only. Preserve these boundaries:

- LFM 8B and Gemma remain experimental;
- LFM 24B is explicit exclusive agent-lane material, not normal topology;
- MiniCPM-V is an experimental multimodal helper, not the production Tika document parser;
- no challenger becomes recommended merely because it installs or generates once;
- do not broaden release acceptance into a model tournament.

## 1.5 release-build observability

The accepted SRPM-first authority chain is unchanged:

```text
freeze exact Source0/spec
→ rpmbuild -bs
→ isolated authoritative SRPM rebuild (one Rust/governor compilation)
→ RPM %check
→ publish those exact rebuilt RPMs
→ payload validation
→ blocking rpmlint
→ closed manifests/evidence/selection
```

1.5 adds only reporting/measurement around this chain: the rebuild summary identifies the source SRPM and actual rebuilt RPM filenames, and machine-greppable `BC250_TIMING stage=... seconds=... rc=...` lines cover major release stages. `%check` emits its duration from inside the same authoritative rebuild.

Do not treat timing instrumentation as permission to weaken/restructure the release gate.

## Before touching the device — bind exact 1.5 artifact identity

Record:

```text
GitHub repository
workflow name
workflow run ID
run attempt
selected source commit SHA
selected RPM filename / NEVRA / SHA-256
selected SRPM filename / SHA-256
release-evidence.json identity/hash
release-selection.json identity/hash
device identifier
Fedora release
kernel
pre-test boot ID
```

Verify hashes against selected GitHub evidence. Ambiguous identity is `INCOMPLETE EVIDENCE` and a stop before mutation.

## Phase 1 — install/upgrade and changed-surface smoke

Install/upgrade the exact selected 1.5 RPM and require:

- transaction succeeds and `rpm -V` is clean;
- migration-safety stop/hold remains coherent where applicable;
- package secret permissions remain private;
- `sudo bc250 install` converges without source-tree intervention;
- pre-convergence status, when deliberately observed at the valid reboot/convergence boundary, uses the new setup-incomplete semantics rather than falsely claiming mismatch;
- guided installer shows exactly one normalized Ollama observed version (or explicit unknown), never `instance`/arbitrary words;
- normal post-convergence `status`, `health`, `verify` remain coherent;
- no GFX/private-RADV/patched-kernel dependency appears.

A real runtime identity mismatch must still be surfaced; do not accept a fix that merely hides mismatch warnings.

## Phase 2 — core topology and 40-CU persistence

Verify rather than re-prove:

```text
11434  main Ollama
11435  task Ollama
11437  embedding Ollama
11436  agent Ollama only in explicit exclusive agent mode
3000   Open WebUI loopback
80     nginx when configured
Tika   private application/container network
```

Require the known supported 40/40 routing profile, exact saved/live match, zero problem cells and enabled boot restore. Do not reopen a general 40-CU stability campaign.

## Phase 3 — representative runtime/RAG regression

Because 1.5 does not change runtime pins or RAG architecture, use bounded regression evidence rather than replaying all of 1.4 Blocks 2–3 unless a changed-surface observation demands it.

At minimum preserve:

- main visible generation;
- task and embedding lane separation;
- package-owned registration remains unique/stable;
- Open WebUI authenticated desired state and local-first policy;
- one grounded document question with expected citation/provenance;
- one deliberately unsupported question with no fabricated document fact;
- one package-owned Advanced path proving the saved 6144 policy still arrives as `options.num_predict=6144` if low-cost to capture, otherwise retain the exact 1.4 proof as regression context and prioritize the pending reboot/ordinary-user boundary.

Do not repeat expensive qualification merely to accumulate duplicate evidence.

## Phase 4 — 1.5 challenger bounded checks

Only after core state is green:

1. confirm all four challenger catalog identities are discoverable and not recommended/default;
2. install/register only the challengers selected for this device round; do not install everything automatically;
3. for local GGUF entries, verify manager-owned path/hash behavior;
4. for the LFM 24B agent challenger, enter exclusive agent mode only through the supported path, verify the normal lanes are not concurrently presented as normal operation, then restore normal mode;
5. for MiniCPM-V, treat one bounded vision/OCR observation as experimental evidence only; do not compare it as a Tika replacement unless a separate experiment is requested;
6. record resource pressure/OOM behavior and stop rather than forcing an oversized model into success.

A challenger failure does not automatically fail the core 1.5 appliance unless it exposes a package/catalog contract defect. Classify model-quality or hardware-fit results separately.

## Phase 5 — required reboot persistence and ordinary-user boundary

This is the major acceptance surface left open after the 1.4 Block 3 milestone.

Record pre-reboot boot ID, then perform a real supported reboot and prove the boot ID changed. After reboot require:

- exact 1.5 RPM hash/NEVRA remains installed;
- required TTM kernel arguments are active;
- 40/40 live routing is restored and matches the saved profile;
- required services recover with no package-attributable failed units;
- `status`, `health`, `verify` remain sane;
- package-owned registrations remain usable;
- Open WebUI remains accessible and package policy remains applied;
- RAG state used in the smoke remains coherent.

Then run the complementary ordinary-user Open WebUI qualification using the current supported harness, covering as applicable:

```text
ordinary-user ACL / visibility
uploaded-document RAG UX
synthetic Tika DOCX path
Advanced reasoning / structured / history paths
Deep reasoning / residency sequence
background task lane
multi-model path
cross-preset office-email UX comparison
```

Do not replay package-owned RAG 3/3, canonical translation 12/12 or the raw 6144 capture solely for duplication if their relevant 1.5 regression boundary is otherwise established.

## Stop conditions

Stop and preserve evidence at the first confirmed blocker, especially:

- exact artifact identity cannot be established;
- install/upgrade cannot converge safely;
- migration snapshot/integrity boundary fails;
- changed 1.5 status parser hides a real mismatch or reports wrong setup state;
- installer version parser still produces a non-version token;
- package-owned data would require destructive cleanup merely to continue testing;
- required registrations/topology are lost;
- local-first policy unexpectedly enables an outbound-capable surface;
- RAG clearly violates public/confidential boundaries;
- reboot fails to restore supported appliance state;
- a package/catalog defect makes an optional challenger unsafe or corrupts core state.

Do not continue unrelated testing after enough evidence exists for a real blocker.

## Result classification

Use:

```text
CONFIRMED PRODUCT/PACKAGE DEFECT
CONFIRMED BUILD/RELEASE DEFECT
CONFIRMED TEST/HARNESS DEFECT
CONFIRMED SECURITY/RECOVERY DEFECT
EXPECTED/SUPPORTED STATE
CI/ENVIRONMENT FAILURE
INCOMPLETE EVIDENCE
OBSERVATION / REVIEW
OUTSIDE SCOPE
```

Overall exact-RPM verdict:

```text
PASS        required 1.5 exact-artifact acceptance boundary passed
FAIL        confirmed package/device blocker
INCOMPLETE  required evidence could not be obtained safely
HARNESS/ENV test environment prevented a valid conclusion
```

Only exact selected 1.5 bytes can become DEVICE-VALIDATED/ACCEPTED.

## What not to reopen

Without new direct evidence, do not reopen:

- GFX1013 patched-kernel/private-RADV work;
- custom AMDGPU lifecycle/bootloader machinery;
- stock Fedora graphics decision;
- broad runtime/model topology redesign;
- broad model tournaments;
- context-ceiling changes beyond explicit policy evidence;
- backup/restore as a new core v1.0 feature;
- SRPM-first release architecture;
- `sccache` or custom builder-image work during device testing.

## Cleanup and restoration

For every stateful test:

- preserve operator-added models/data;
- keep secrets out of evidence;
- restore temporary corpus/config changes;
- verify cleanup rather than merely attempting it;
- do not delete unexpected state before capture/classification;
- restore normal mode after any agent-exclusive test.

## Required return to main integration chat

Return one evidence-rich handback containing:

```text
1. selected GitHub run / source commit
2. exact 1.5 RPM NEVRA + SHA-256
3. exact SRPM + SHA-256
4. device/Fedora/kernel identity
5. install/upgrade + changed UX/parser verdict
6. status/health/verify verdict
7. 40-CU/reboot persistence verdict
8. representative Ollama/Open WebUI/RAG regression verdict
9. challenger catalog/device observations, clearly separated from core acceptance
10. ordinary-user Open WebUI boundary verdict
11. confirmed defects
12. harness/environment limitations
13. cleanup/restoration status
14. raw evidence locations/hashes
15. overall PASS/FAIL/INCOMPLETE/HARNESS-ENV verdict
16. one recommended next action
```

Do not return only “works” or “failed.” Exact artifact identity and first authoritative failure are part of the result.
