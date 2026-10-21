# Release 0.14.1-1.5 — scope, rationale and acceptance contract

## Release purpose

Release `0.14.1-1.5` is a controlled quality/product-foundation increment built on the successful 1.4 SRPM-first build architecture and the exact-RPM Blocks 1–3 device baseline.

It deliberately does **not** change the core runtime pins, GPU architecture or production/recommended model set.

## Included source changes

### 1. Pre-convergence status-state correction

The 1.4 device campaign proved that an intentional Open WebUI/Tika migration/publication hold could be presented as `package runtime identity mismatch/unavailable`, even though the package was correctly waiting for reboot/convergence.

1.5 adds explicit package setup/publication state and separates:

```text
real observed identity mismatch
identity unavailable outside setup convergence
intentional setup/convergence pending
fully healthy converged state
```

Expected human state at the intentional boundary:

```text
SETUP INCOMPLETE — package runtime convergence pending
```

The identity check remains strict. A real mismatch must still be reported. Machine-readable status advances with an explicit setup state so human/JSON output can agree.

### 2. Guided-installer Ollama version parser correction

The 1.4 device campaign reproduced a multi-line `ollama --version` case in which the installer showed `instance` as though it were a version. 1.5 extracts a normalized semantic version token from the output and otherwise reports an explicit unknown state. Regression coverage reproduces the multi-line failure class.

### 3. Optional model challenger catalog expansion

Reviewed optional challengers are added without changing production/recommended defaults:

```text
exp-lfm25-8b-a1b-unsloth-q6-k-xl
agentic-lfm25-24b-a2b-unsloth-q3-k-xl
exp-gemma4-12b-hauhaucs-uncensored-q4-k-m
exp-minicpm-v47-1b-openbmb-q4-k-m
```

The existing HauhauCS Gemma challenger is hardened in place rather than duplicated.

Boundaries:

- local manager-owned challenger GGUFs use package catalog metadata/checksums;
- LFM 24B remains exclusive agent-lane material;
- MiniCPM-V is experimental Ollama-managed multimodal material and does not replace Tika;
- no challenger enters `RECOMMENDED_MODELS`;
- a challenger quality/hardware-fit failure is not automatically a core release failure unless package/catalog safety or supported-state contracts are broken.

### 4. Release-build reporting/timing observability

The 1.4 SRPM-first authority architecture remains unchanged. 1.5 folds in the previously queued low-risk observability work:

- rebuild summary states that rebuilt binaries came from the authoritative SRPM and prints actual binary RPM filenames;
- release stages emit machine-greppable `BC250_TIMING` duration/RC records;
- RPM `%check` reports its duration from inside the same authoritative rebuild.

This is measurement, not a new cache/build architecture. There is still one authoritative Rust/governor compilation.

### 5. Handover/current-state reconciliation

Because this is an actual RPM release rather than an intermediate testing checkpoint, the repository handovers/current guidance are synchronized now. Intermediate testing notes were intentionally not propagated through every document while development was in flight.

## Explicitly unchanged

```text
Version:         0.14.1
Ollama:          0.40.6
Open WebUI:      0.12.3
Tika:            4.1.0-full
Governor:        0.4.13
Fedora target:   44
stock AMDGPU/Mesa architecture
SRPM-first release authority
production/recommended model selection
RAG transaction/local-first policy
Advanced max_tokens=6144 policy
```

Do not combine a new runtime upgrade with this release unless the source scope is deliberately reopened and revalidated.

## Source acceptance

Before handing 1.5 to GitHub authority require:

- exact 1.5 identity consistent across authoritative sources/current guidance;
- focused tests for status/parser/catalog/release timing changes;
- release-pipeline/preflight PASS;
- package-critical `%check` PASS;
- current-guidance/scope/clean-core PASS;
- Ruff and ShellCheck PASS in the authoritative Fedora environment;
- Source0/spec freeze reproducible and valid;
- no stale active 1.4 identity presented as current 1.5 state.

The broad module-isolated deterministic suite remains additional release evidence and should be green before handoff.

## GitHub BUILD acceptance

Selected Fedora 44 `workflow_dispatch` authority run must prove:

- frozen Source0/spec identity;
- one authoritative SRPM rebuild;
- `%check` PASS;
- published binary RPMs are the exact rebuild outputs;
- payload validation PASS;
- configured blocking rpmlint PASS;
- release manifests/evidence/selection are complete;
- exact binary/SRPM SHA-256 retained;
- timing records are captured but do not affect gate semantics.

Do not replace a failed selected build with an unrecorded local artifact.

## Exact-device acceptance

Only the exact selected 1.5 RPM can earn DEVICE-VALIDATED status.

Prioritize:

1. changed status/convergence semantics;
2. changed installer Ollama-version output;
3. exact runtime/topology/core smoke;
4. 40/40 saved/live routing and required TTM state;
5. bounded representative RAG/Open WebUI regression;
6. optional challenger catalog/registration boundaries and only selected low-cost challenger observations;
7. real reboot persistence;
8. ordinary-user Open WebUI boundary left pending after 1.4 Block 3.

See `18_TESTING_SIDECHAT_HANDOVER.md` for the execution detail and `20_DEVICE_QUALIFICATION_1_4.md` for the non-transferable baseline.

## Evidence-state rule

```text
source tests green            = SOURCE-VALIDATED only
selected GitHub artifact good = BUILD-VALIDATED only
exact selected RPM on device  = DEVICE-VALIDATED when required boundary passes
accepted release              = explicit ACCEPTED after evidence reconciliation
```

Never transfer acceptance across changed bytes or merely similar filenames.

## Post-1.5 roadmap

If 1.5 reaches acceptance, return to product value rather than immediately reopening infrastructure:

```text
RAG/document quality
German–French office translation
ordinary-user local assistant UX
measured build optimization only if 1.5 timings identify a real bottleneck
optional model challengers only when evidence supports promotion or removal
```

Keep GFX/private-RADV/custom-kernel work closed unless a new product requirement supplies compelling evidence to reopen it.
