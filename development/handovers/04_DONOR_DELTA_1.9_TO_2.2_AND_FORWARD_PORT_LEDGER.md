# C4 donor delta and forward-port ledger — frozen clean core vs 2.2 reference

## C4 verdict

**C4: PASS — classification complete; no donor code has been forward-ported.**

Authority used for this inventory:

```text
Frozen reconstruction base:
  amd-bc-250-llm(20261019-080542).zip
  SHA-256 79b1a9e60e15764b49d67982d9dd689a338766dc50f21dac2cdb4c1139cd32d6
  bc250-llm-server-0.13.1-1.9

Accepted clean-core implementation predecessor:
  amd-bc-250-llm-clean-core-C3-R1.zip
  C0 PASS / C1 PASS / C2 PASS / C3 PASS

Active integration checkpoint after this classification is frozen:
  amd-bc-250-llm-clean-core-C4.zip
  C4 PASS; classification/guidance only, no donor runtime code ported

Canonical donor/reference used for this C4 classification:
  2.2-archived.zip
  SHA-256 4807fa47397b44b603bb9231e3bb8a2c4aa0b14a5c919a04d04af87f4c42bbc6
  bc250-llm-server-0.13.1-2.2

Independent review cross-check provenance:
  amd-bc-250-llm-0.13.1-2.2.zip
  SHA-256 8570cd9b0eec17f36dde4951f4e5e4f99344a7c38caa6b61783a204793905a81
  reported content-equivalent for the exact 84-path donor delta; not bundled in this checkpoint
```

The exact 1.9 -> 2.2 donor delta contains **84 changed paths**: **66 modified common paths + 18 donor-only paths**. Every one is classified in the path appendix below. C3-R1-specific clean-core handovers/gates are not donor changes and are therefore not candidates to port.

Classification vocabulary:

```text
KEEP    behavior is useful and independent enough to port deliberately
REWORK  useful concept exists, but 2.2 implementation is coupled to GFX, stale schema, local-only build authority, or later runtime assumptions
DROP    do not port into clean core
HOLD    separate product/runtime/benchmark decision; not part of C5 core porting
```

## Build authority decision — binding for C5 and later

The primary RPM build path returns to **GitHub Actions**:

```text
.github/workflows/build-rpm.yml
Fedora 44 container
make release-gate
binary RPM + SRPM artifacts
```

Local build is **backup/reproduction only**, using the same clean-core release gate through `scripts/ci-local.sh` or direct `make release-gate` in a matching Fedora 44 environment.

The 2.2 decision to make `./build-local.sh --full` the sole authoritative release path is **DROP**. The exact donor `build-local.sh` is also GFX-heavy and is not a C5 port target. Useful generic release-hardening ideas from 1.14-1.17 are classified separately below and must be adapted to the GitHub-primary topology.

## Behavior decision ledger

| ID | Donor behavior / finding | 2.2 source | Class | C5 rule |
|---|---|---|---|---|
| B01 | GitHub demoted to source-only validation / local-only RPM authority | `.github/workflows/build-rpm.yml`, 1.13+ handovers | **DROP** | Preserve current GitHub Fedora RPM build as primary. |
| B02 | Exact `build-local.sh --full` release driver | `build-local.sh` | **DROP** | Do not import; local backup already exists through the clean-core release gate. |
| B03 | Freeze Source0 + spec before authoritative build and validate extracted frozen source | `Makefile`, 1.15-1.16 | **KEEP** | Reimplement on the GitHub-primary path; exact bytes entering `rpmbuild` must be the bytes validated. |
| B04 | Core machine-readable release contract for NVR/Fedora/runtime/build stages | `release-contract.json`, `scripts/release-contract.py` | **REWORK** | Design a GFX-free contract and make the GitHub stage graph authoritative. Do not copy GFX fields. |
| B05 | Re-check clean Git/source identity at freeze time | 1.16 build pipeline | **KEEP** | Useful for release qualification; engineering dirty-tree modes must never produce release authority. |
| B06 | Deterministic source archive: custom build-root exclusion, no generated empty dirs, cache/build path isolation | `make-source-tarball.sh`, `prepare-sources.py`, `validate.py` | **KEEP** | Port without donor GFX cache assumptions. |
| B07 | Build/package work as an unprivileged builder after dependency/tool installation | 1.11, `ci-local.sh` | **KEEP** | Apply to GitHub where practical; retain local backup parity. |
| B08 | Split closed binary/source SHA-256 manifests | 1.11/Makefile | **KEEP** | GitHub artifacts should be independently verifiable. |
| B09 | Fail-fast host release checks before expensive build plus package-context `%check` separation | 1.15-1.16 | **REWORK** | Preserve no-duplicate-test intent without inventing GFX stages; GitHub remains authority. |
| B10 | Concise deterministic-module PASS/count logging, full output only on failure | `validate.sh` | **KEEP** | Useful CI ergonomics; must retain actual return codes/timeouts and current clean-core gates. |
| B11 | Transformed binary-RPM payload verification beyond filename list | Makefile 1.13+ | **REWORK** | Keep generic runtime/package-owned metadata checks; remove all GFX payload checks. |
| B12 | Disable unrelated `fedora-cisco-openh264` only during build-tool install | GitHub/local CI 1.11 | **KEEP** | Port if still needed by Fedora 44 CI; it must not alter runtime repositories. |
| B13 | Local `.build` workspaces, sccache telemetry, background mode, timestamped stage timing | 1.14-1.17 | **HOLD** | Backup-build convenience only; not required for the primary GitHub release path. |
| B14 | Structured release diagnostics/result JSON | `release-diagnostics.sh`, `build-local.sh` | **REWORK** | Keep only if it adds useful GitHub artifact evidence without duplicating existing logs/hashes. |
| U01 | TTY-aware status/health/installer colors; `NO_COLOR`; plain non-TTY/JSON | `doctor.py`, `install.sh`, spec | **KEEP** | Centralize or share patterns where sensible; color remains supplemental. |
| U02 | `Web interface` instead of normal-output `front door` jargon | installer/verify/docs | **KEEP** | Diagnostic listener/proxy terminology may remain technical. |
| U03 | Neutral package-transition wording for upgrade/downgrade/reinstall | spec/output | **KEEP** | Do not call every transaction an upgrade. |
| U04 | One authoritative post-transaction next action | 2.0-2.2 packaging/installer | **KEEP** | Reimplement generically; GFX handoff suppression itself is DROP. |
| U05 | Installed package NEVRA in human status | `status.sh` 1.10 | **KEEP** | Keep machine schema stable unless deliberately versioned. |
| U06 | `bc250 health` user-facing alias while retaining `doctor` compatibility | dispatcher/doctor/completion | **REWORK** | Alias is useful; preserve the current clean-core v3 doctor semantics and return-code contract. Do not import 2.2 GFX readiness/schema v2. |
| U07 | Combined-catalog interactive model-install workflow (planned C5 behavior) | `models/modelctl.py`, 2.0-2.1 | **KEEP** | `apply` remains advanced/scripted reconciliation. |
| U08 | Model-install prompt/grammar and cancel/no-mutation UX | model installer/tests | **KEEP** | Enter cancels, no mutation, and final text should be `Cancelled — no changes made.`; use `Experimental models:`. |
| U09 | Installer completion grouped into status/validation, setup/repair, models, optional improvements | `install.sh` 2.0-2.1 | **REWORK** | Keep grouping and direct model-install orientation; delete every GFX line. |
| U10 | Installer shows desired/observed Ollama version and verifies post-reconciliation equality | `install.sh` | **KEEP** | Independent of whether runtime remains 0.34.4 or later changes. |
| R01 | Ollama 0.40.4 runtime pin | `runtime.env`, spec/docs | **HOLD** | Separate runtime/API/model/device acceptance; C5 must not change the pin. |
| R02 | Verify effective BC-250 Vulkan/iGPU/device-selection environment | `verify-server.sh` | **KEEP** | Services already configure these values; verification should prove the effective contract. |
| R03 | External context-allocation-ceiling conclusions from `akandr/bc250-rocm` | 1.15 docs | **HOLD** | Benchmark methodology only; no production context/swap/governor change in C5. |
| Q01 | Open WebUI token-path probing tolerates `PermissionError`/`OSError` | `openwebui-setup.py` | **KEEP** | Treat inaccessible optional path as unavailable. |
| Q02 | Maintenance and restore-user scripts are safely sourceable for direct tests | `maintenance.sh`, `restore-users.sh` | **KEEP** | Preserve normal CLI behavior and root enforcement. |
| Q03 | `ollama-profile.sh` nounset-safe declaration split | `ollama-profile.sh` | **KEEP** | Low-risk shell correctness fix. |
| Q04 | Fixture-local `HF_HOME` to avoid host cache leakage | `tests/test_state.py` | **KEEP** | Test isolation only. |
| Q05 | Thinking-capable model output can live in `thinking` while visible `response` is empty | 2.2 benchmark investigation / current donor ledger | **REWORK** | Fix measurement semantics explicitly; do not weaken thresholds or hash empty visible output as meaningful determinism. |
| D01 | GFX1013 lifecycle/state/boot/private RADV/kernel/Mesa/build/benchmark/docs/tests | all GFX paths | **DROP** | Standalone GFX repository owns the experiment. |
| D02 | GFX-bound package-gate/qualification identity and 2.2 schema rollback | qualification files/tests | **DROP** | C3-R1 clean-core package-gate v3 and GFX-free identity remain authoritative. |
| D03 | 2.2 current handovers/workbench/release identity | changelog/handovers/state | **DROP** | Preserve only as historical donor evidence. |
| D04 | GFX-specific SRPM/source-package/kernel/Mesa provenance machinery | 1.10-1.18 build helpers | **DROP** | No patched kernel/private Mesa build belongs in the core release gate. |

## C5 implementation order

No donor code was ported during C4. The next milestone is C5, one coherent cluster at a time:

1. **C5-A — low-risk correctness/supportability:** Open WebUI inaccessible-path handling; maintenance/restore sourceability; shell nounset fix; test-isolation fix; generic `Web interface`/transition wording; package NEVRA; Vulkan environment verification.
2. **C5-B — model/installer UX:** `model install`, cancel/no-mutation wording, installer grouping, desired/observed Ollama reconciliation, one-next-action, TTY/`NO_COLOR`, optional `health` alias reworked onto current v3 semantics.
3. **C5-C — release/build hardening:** frozen Source0/spec, deterministic archive exclusions, core-only release contract, checksum manifests, unprivileged build, fail-fast/package test layering, payload proof — **all adapted to GitHub-primary RPM authority**.
4. **C5-D — benchmark semantics:** thinking/visible-response determinism correction only after the exact current benchmark path is inspected and a failing regression is encoded.

`R01`, `R03` and local-build convenience work remain HOLD and are not prerequisites for C5-A/B/C/D.

## Direct-port prohibitions

Do not cherry-pick or bulk-copy these donor surfaces:

- `build-local.sh`;
- donor `.github/workflows/build-rpm.yml` (it intentionally stops building RPMs);
- donor `release-contract.json` without redesign;
- donor `Makefile` release graph;
- donor monitoring/qualification schemas;
- any `gfx1013/`, GFX helper, GFX benchmark, GFX build dependency/provisioner or GFX test;
- donor current handovers, workbench status, release identity or 2.2 qualification claims.

## Path-level coverage appendix

This appendix classifies the direct portability of every exact 1.9 -> 2.2 changed path. A `REWORK` path can contain individual KEEP ideas described above; it is not safe to copy as a unit.

| Changed path | Class | Direct-port decision |
|---|---|---|
| `.github/workflows/build-rpm.yml` | **DROP** | 2.2 demotes GitHub to source-only validation; current policy restores GitHub Fedora RPM build as primary. |
| `.gitignore` | **REWORK** | Only generic generated-build exclusions are potentially useful; do not import the 2.2 local-build topology wholesale. |
| `CHANGELOG.md` | **DROP** | 2.2 release history remains historical donor evidence; do not rewrite current clean-core history as if those releases were ancestors. |
| `Makefile` | **REWORK** | Harvest frozen-input, manifest and fail-fast ideas; strip every GFX stage and keep GitHub as build authority. |
| `README.md` | **REWORK** | Update only for accepted clean-core behavior; do not copy 2.2 runtime/GFX/build-authority claims. |
| `TLDR.md` | **REWORK** | Update only for accepted clean-core behavior; do not copy 2.2 runtime/GFX/build-authority claims. |
| `WORKBENCH-STATE.json` | **DROP** | 2.2 state/evidence is donor history and cannot become current clean-core authority. |
| `build-local.sh` | **DROP** | Exact script is GFX-heavy and makes local Fedora the sole authority. Local build remains backup via the clean-core release gate. |
| `cmd/benchmark/gfx1013-ab.py` | **DROP** | Experiment-specific A/B campaign. |
| `cmd/benchmark/revalidate.sh` | **KEEP** | Generic wording removes a hard-coded Ollama version from thinking-metadata commentary. |
| `cmd/maintenance/maintenance.sh` | **KEEP** | Sourceable main-guard improves testability without changing normal execution. |
| `cmd/maintenance/restore-users.sh` | **KEEP** | Sourceable main/root guard makes restore behavior testable without sed-based test hacks. |
| `cmd/monitoring/doctor.py` | **REWORK** | TTY/NO_COLOR and health naming are useful; GFX readiness/schema/return-code changes are not. |
| `cmd/monitoring/status.sh` | **REWORK** | Installed package NEVRA is useful; GFX action-state overlay is not. |
| `cmd/monitoring/verify-server.sh` | **KEEP** | Verify the already-configured BC-250 Vulkan/iGPU/device-selection environment explicitly. |
| `cmd/openwebui/openwebui-setup.py` | **KEEP** | Treat inaccessible token-file paths as unavailable instead of raising OSError/PermissionError. |
| `cmd/qualification/package_gate_capture.py` | **DROP** | 2.2 re-binds qualification to GFX and regresses the clean-core v3 contract. |
| `cmd/system/gfx1013.sh` | **DROP** | Experiment lifecycle/state/build/boot owner. |
| `cmd/system/install.sh` | **REWORK** | Keep desired/observed Ollama convergence and installer orientation; remove all GFX-specific completion logic. |
| `cmd/system/ollama-profile.sh` | **KEEP** | Small nounset-safe local declaration fix. |
| `config/runtime.env` | **HOLD** | Ollama 0.40.4 is a separate runtime upgrade decision. |
| `development/DECISIONS.md` | **HOLD** | 2.2 edits are tied to the later runtime identity; revisit only with a runtime decision. |
| `development/DEVELOPMENT-SCOPE.json` | **DROP** | 2.2 scope/status is not current clean-core authority. |
| `development/TESTING-STRATEGY.md` | **REWORK** | Harvest generic release/testing lessons only; retain current clean-core strategy and GitHub-primary build policy. |
| `development/VALIDATION-MATRIX.md` | **DROP** | 2.2 matrix is release/GFX evidence, not transferable qualification. |
| `development/handovers/CURRENT_WORK_NEXT_BUILD_HANDOVER_0.13.1-1.16.md` | **DROP** | Donor release handover is historical evidence only; do not make it current clean-core authority. |
| `development/handovers/CURRENT_WORK_NEXT_BUILD_HANDOVER_0.13.1-1.17.md` | **DROP** | Donor release handover is historical evidence only; do not make it current clean-core authority. |
| `development/handovers/CURRENT_WORK_NEXT_BUILD_HANDOVER_0.13.1-1.18.md` | **DROP** | Donor release handover is historical evidence only; do not make it current clean-core authority. |
| `development/handovers/CURRENT_WORK_NEXT_BUILD_HANDOVER_0.13.1-2.0.md` | **DROP** | Donor release handover is historical evidence only; do not make it current clean-core authority. |
| `development/handovers/CURRENT_WORK_NEXT_BUILD_HANDOVER_0.13.1-2.2.md` | **DROP** | Donor release handover is historical evidence only; do not make it current clean-core authority. |
| `development/handovers/MAIN-INTEGRATION-HANDOVER.md` | **DROP** | Donor current-state handover is historical only. |
| `development/handovers/README.md` | **DROP** | Donor current pointers are historical only. |
| `development/handovers/TESTING-HANDOVER-0.13.1-1.17.md` | **DROP** | Donor release handover is historical evidence only; do not make it current clean-core authority. |
| `docs/BENCHMARKING.md` | **HOLD** | External context-ceiling methodology is interesting but belongs to a later benchmark/runtime decision. |
| `docs/GFX1013.md` | **DROP** | Experiment operator documentation. |
| `docs/HARDWARE.md` | **HOLD** | Context-ceiling additions are external benchmark evidence, not required for C5 core porting. |
| `docs/OLLAMA.md` | **REWORK** | Keep generic Vulkan contract guidance if ported; 0.40.4 identity remains HOLD. |
| `docs/OPENWEBUI.md` | **HOLD** | Only donor change is the held Ollama runtime identity. |
| `docs/OPERATIONS.md` | **REWORK** | Harvest accepted operator UX and build guidance; strip GFX/current-2.2 claims. |
| `docs/QUALIFICATION.md` | **DROP** | Donor changes are tied to GFX qualification. |
| `gfx1013/upstream/MESA-SOURCE` | **DROP** | Experiment source payload. |
| `gfx1013/upstream/PACKAGE-PROFILE-VERSION` | **DROP** | Experiment source payload. |
| `gfx1013/upstream/PATCH-SHA256SUMS` | **DROP** | Experiment source payload. |
| `gfx1013/upstream/SOURCE-SHA256SUMS` | **DROP** | Experiment source payload. |
| `gfx1013/upstream/UPSTREAM-NOTICE.md` | **DROP** | Experiment source payload. |
| `gfx1013/upstream/check-kernel-provenance.py` | **DROP** | Experiment kernel provenance helper. |
| `gfx1013/upstream/patches/mesa/0001-gfx1013-compute-queue-fix.patch` | **DROP** | Experiment Mesa patch. |
| `gfx1013/upstream/patches/mesa/series` | **DROP** | Experiment Mesa patch series. |
| `models/modelctl.py` | **KEEP** | Interactive combined-catalog model install is accepted; implement with stronger explicit cancel/no-mutation wording. |
| `models/modelfiles/exp-granite42-3b-ibm-q6-k.Modelfile` | **HOLD** | Only donor delta ties commentary to held Ollama 0.40.4. |
| `packaging/README.md` | **REWORK** | Build/release docs must reflect GitHub-primary clean-core policy rather than donor local-only/GFX pipeline. |
| `packaging/bc250` | **REWORK** | Health alias is useful; GFX route is not. |
| `packaging/bc250-llm-server.spec` | **REWORK** | Keep NO_COLOR/neutral transition/one-action ideas; discard GFX hooks/dependency and do not reuse 2.2 NVR. |
| `packaging/completions/bc250.bash` | **REWORK** | Add accepted model-install/health completion only if implemented; discard GFX completion. |
| `packaging/install-manifest.tsv` | **DROP** | 2.2 delta only adds GFX provenance payload. |
| `release-contract.json` | **REWORK** | Core-only machine-readable release contract is valuable; remove GFX fields and make GitHub stage graph authoritative. |
| `scripts/check-gfx1013-kernel-build.sh` | **DROP** | Experiment build gate. |
| `scripts/check-gfx1013-mesa.py` | **DROP** | Experiment build gate. |
| `scripts/check-upstream-patches.py` | **KEEP** | Allow explicit source-cache directory through BC250_SOURCE_DIR. |
| `scripts/ci-local.sh` | **REWORK** | Keep unprivileged-builder discipline as backup; remove GFX provisioning and do not make local CI authoritative. |
| `scripts/make-source-tarball.sh` | **KEEP** | Generic custom build-root exclusion and empty-directory pruning improve deterministic Source0. |
| `scripts/prepare-sources.py` | **KEEP** | Generic source/build directory overrides and cleanup improve reproducibility. |
| `scripts/provision-gfx1013-kernel-builddeps.sh` | **DROP** | Experiment build provisioning. |
| `scripts/provision-gfx1013-mesa-builddeps.sh` | **DROP** | Experiment build provisioning. |
| `scripts/release-contract.py` | **REWORK** | Useful generic accessor only after a core-only release contract is designed. |
| `scripts/release-diagnostics.sh` | **REWORK** | Structured diagnostics idea is useful; exact implementation assumes donor local/GFX release graph. |
| `scripts/validate.py` | **REWORK** | Keep generic dynamic exclusions/release-metadata checks; remove GFX-required inputs and identity assertions. |
| `scripts/validate.sh` | **REWORK** | Keep concise isolated module reporting/package-mode split if needed; restore clean-core guidance gates and GitHub-primary pipeline semantics. |
| `tests/test_benchmark.py` | **REWORK** | Retain generic Vulkan-env/noninteractive coverage; runtime-version assertions follow the held runtime decision. |
| `tests/test_catalog.py` | **KEEP** | Direct coverage for model-install combined-catalog and hard no-mutation cancellation. |
| `tests/test_documentation.py` | **REWORK** | Port only tests for accepted current docs/contracts; donor GFX/runtime identity checks are not authority. |
| `tests/test_gfx1013.py` | **DROP** | Experiment lifecycle tests. |
| `tests/test_gfx1013_benchmark.py` | **DROP** | Experiment benchmark tests. |
| `tests/test_gfx1013_kernel_provenance.py` | **DROP** | Experiment kernel tests. |
| `tests/test_gfx1013_mesa_check.py` | **DROP** | Experiment Mesa tests. |
| `tests/test_install.py` | **REWORK** | Keep generic installer orientation/convergence/color contracts; remove GFX transition cases. |
| `tests/test_maintenance.py` | **KEEP** | Tests the sourceable maintenance/restore helpers directly. |
| `tests/test_openwebui.py` | **KEEP** | Regression for inaccessible legacy token path. |
| `tests/test_operations.py` | **REWORK** | Keep package-identity/color/health-alias pieces only; discard GFX health/status semantics and donor schema rollback. |
| `tests/test_packaging.py` | **REWORK** | Keep deterministic Source0, GitHub authority, runtime-env and artifact checks; discard GFX/local-only assumptions. |
| `tests/test_qualification.py` | **DROP** | 2.2 delta reintroduces GFX qualification and older schema. |
| `tests/test_release_pipeline.py` | **REWORK** | Useful frozen-input/release-orchestration tests, but exact suite is coupled to build-local/GFX/local authority. |
| `tests/test_state.py` | **KEEP** | Fixture-local HF_HOME prevents host cache leakage. |
| `tests/test_upstream_patch_validation.py` | **DROP** | 2.2 delta only wires GFX Mesa source validation. |

## Coverage totals

Exact donor delta paths classified: **84 / 84**.

- **KEEP: 14 paths**
- **REWORK: 26 paths**
- **HOLD: 6 paths**
- **DROP: 38 paths**

These counts describe path-level direct portability, not the number of behavior decisions. Mixed files intentionally land in REWORK even when they contain multiple accepted generic ideas.
