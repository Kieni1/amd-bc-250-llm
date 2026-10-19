# AMD BC-250 LLM appliance — main integration handover — clean-core reconstruction

## 1. Main-chat responsibility

The main integration chat owns the whole-product boundary:

- current source identity and canonical tree;
- the clean-core reconstruction scope;
- donor-change classification;
- package/build/device authority;
- cross-component regressions;
- whether a finding is code, packaging, test tooling, environment or evidence gap;
- when a change is ready for Fedora/device handoff;
- preservation of historical qualification without transferring it to new bytes;
- transition back toward office/RAG/product work after the core is clean.

The main chat should not recreate GFX1013 functionality in the core package merely because the old implementation is available.

## 2. Current authority hierarchy

Use authority in this order:

1. newest exact evidence from the current working tree;
2. frozen 1.9 baseline for reconstruction identity;
3. current clean-core tests and handovers;
4. 2.2 testing/reference line for donor behavior and historical findings;
5. older handovers/changelogs for context only.

If documents disagree, reconcile them explicitly. Do not silently average old and new truth.

## 3. Current baseline identity

Frozen reconstruction source:

```text
amd-bc-250-llm(10).zip
SHA-256: 79b1a9e60e15764b49d67982d9dd689a338766dc50f21dac2cdb4c1139cd32d6
bc250-llm-server-0.13.1-1.9
Fedora 44
Ollama 0.34.4
Open WebUI 0.11.4
Tika 4.1.0-full
```

The baseline is known-good enough to reconstruct from, not accepted as GFX-free. It contains GFX1013 surfaces beginning in the 1.5-era history and therefore requires deliberate removal.

## 4. Repository topology

Intended repository roles:

```text
main
  clean-core future

preserved GFX branch
  historical in-core experiment; do not merge back into main

2.2 testing/reference repository or branch
  exact qualification evidence + donor implementation/reference

bc250-gfx1013 standalone repository
  independent experiment; no dependency from core unless explicitly reconsidered later
```

Do not merge the qualified 2.2 GFX tree into main and then revert it. Build forward from the clean-core reconstruction line.

## 5. Current integration checkpoint status

C8 source identity is now assigned: `bc250-llm-server-0.14.1-1`.

```text
bc250-llm-server-0.14.1-1
Fedora 44 build authority: GitHub Actions
Build status: pending selected authoritative run
Device status: pending C9
```

C8 is the current source-ready checkpoint. C7 remains its immediate frozen source predecessor and integrated source-gate PASS.

The immutable accepted C5-D behavioral/source freeze is:

```text
archive: amd-bc-250-llm-clean-core-C5-D.zip
archive SHA-256: 25be3783716451c84f54209ae16a38c5de1ef1675c4b579fd02cfff08865c710
canonical manifest SHA-256: e43ab0244de09bc4fc1981db36d956860e6d01715566fe91a9597c869b59e651
source files: 362
deterministic source baseline: 613/613 across 20 modules
package-context baseline: 594/594 across 19 modules
host release-pipeline baseline: 19/19
```

That identity is frozen evidence and must not be redefined by later documentation/bookkeeping bytes. Current source checkpoint: **C8 — SOURCE-READY (0.14.1-1); authoritative GitHub build pending**. Immediate frozen source predecessor: **C7 — PASS**; C7's predecessor is **C6**. Immutable behavioral predecessor: **C5-D**. Release-hardening predecessor: **C5-C**. Classification predecessor: **C4**. Clean-core structural predecessor: **C3-R1**. Active next action: **C8 — authoritative Fedora 44 GitHub Actions build**.

The independently reviewed first C3 proposition remains preserved as failure evidence, but its narrow blockers were corrected in C3-R1.

Current source verdict:

```text
C0 baseline identity:      PASS
C1 ownership inventory:   PASS
C2 structural removal:    PASS
C3 regression baseline:   PASS (C3-R1 source/deterministic level)
C4 donor classification:  PASS
C5-A correctness/support: PASS
C5-B model/installer UX: PASS
C5-C release/build hardening: PASS
C5-D benchmark semantics:     PASS
C6 secondary docs/QC:        PASS
C7 integrated source gate:   PASS
C8 source gate:               PASS / SOURCE-READY (build pending)
```

C3-R1 specifically restored generic `runtime_identity` handling in `bc250 version`, restored the `kmod` dependency required by the stock verifier, reconciled current testing/handovers/docs, installed refined clean-core/current-guidance preflight gates, and aligned the frozen predecessor name. C5-C closes release/source authority at 611 tests across 20 modules, with the package-context lane at 592 tests across 19 modules; Git worktrees build Source0 from tracked files only, ignored/untracked workspace bytes cannot enter the archive, and authoritative GitHub runs fail closed unless checked-out `HEAD` equals `GITHUB_SHA`. C5-D raised the then-current deterministic baseline to 613 tests across 20 modules (594 package-context tests across 19 modules) and prevents thinking-only/empty visible responses from being represented as deterministic visible-output evidence.

C6 documentation/QC adds four regression tests and passes 617/617 deterministic tests across 20 modules: 598/598 package-context tests across 19 modules plus 19/19 host release-pipeline tests. C7 reruns that complete integrated source gate on the accepted source, proves tracked-file Source0 equivalence and extracted-Source0 validation, and remains 617/617. C8 assigns 0.14.1-1 and passes 619/619 deterministic source tests across 20 modules: the package-context lane remains 598/598 across 19 modules and the strengthened host release-pipeline lane is 21/21. The immutable C5-D predecessor remains 613/613; later source checkpoints do not rewrite that evidence.

This is still source evidence only: no Fedora build or BC-250 device acceptance is implied. The rejected first proposition and review are retained in `C3_PROPOSITION_REVIEW_AND_REQUIRED_REWORK.md`.

## 6. Completed clean-core removal milestone

C3-R1 closes the reviewed blockers. C1, C2 and C3 are PASS at the source/deterministic level. Do not redo the structural removal. C4 donor classification is complete; C5-A, C5-B, C5-C and C5-D have ported only their written-ledger clusters. C5-C closes the source-side release/build-hardening work with GitHub Actions as artifact authority; C5-D closes the thinking/visible-response benchmark semantic correction. C6 secondary-file/documentation QC and C7 integrated source validation are complete. C8 has assigned the new unused 0.14.1-1 identity and passed its source gate. Proceed next to the authoritative Fedora 44 GitHub Actions build; do not pull HOLD/runtime/context-ceiling work forward, and do not begin C9 until the selected build evidence is frozen.

The completed structural removal covered, as applicable:

- `gfx1013/` source payload;
- `cmd/system/gfx1013.sh`;
- GFX benchmark helper/campaign code;
- CLI dispatcher entries;
- GFX install/uninstall/package manifests;
- `%pre/%post/%preun` GFX rollback/migration logic;
- GFX state/cache directories and `%ghost` entries;
- private RADV paths and environment overrides;
- patched-module/kernel-source build requirements;
- GFX BLS/GRUB helpers if not used by any non-GFX feature;
- GFX fields in status/doctor/health/verify/version/JSON;
- GFX qualification inventory and cleanup surfaces;
- GFX docs and current help text;
- GFX unit/integration tests;
- GFX release/development-scope requirements.

Do not blindly delete generic AMDGPU, Vulkan or CU-routing functionality. The normal stock appliance still uses AMD hardware.

## 7. Core behavior that must survive the removal

At minimum preserve:

- normal stock boot and stock AMDGPU;
- live CU/WGP routing and saved profile behavior where already part of the normal appliance;
- Ollama service topology;
- Open WebUI/Tika convergence and identity checks;
- model catalog/apply/status behavior;
- RAG/document paths;
- storage/maintenance functionality;
- package integrity and verification;
- installer convergence;
- support/version/status diagnostics;
- operator state and protected persistent data.

A clean grep is not enough. The remaining appliance must still work.

## 8. Donor philosophy

Treat 2.2 as a donor/reference, not as an ancestor to merge.

Every candidate donor change must be classified:

```text
KEEP     useful and independent of GFX; port with tests
DROP     GFX-specific or not worth carrying
REWORK   useful idea but implementation is coupled to GFX/current 2.2 assumptions
HOLD     requires a separate product decision
```

Do not cherry-pick broad commits whose useful part is mixed with GFX code. Reimplement the useful behavior on the clean core.

## 9. Explicitly accepted generic donor improvements

The current forward-port default includes:

- TTY-aware human-output colors that respect `NO_COLOR` and disappear in pipes/non-TTY/machine output;
- `Web interface` wording instead of internal `front door` jargon;
- neutral package-transition language that is correct for upgrade/downgrade/reinstall;
- model-install prompt/grammar/cancel-no-mutation wording improvements;
- source/release/preflight hardening that is not GFX-specific;
- one canonical tree and frozen/extracted Source0 validation;
- exact return-code and no-mutation tests;
- package/runtime identity improvements and convergence fixes that are independent of GFX;
- documentation/secondary-file consistency gates;
- benchmark-harness correction for thinking-capable models: never treat empty `response` caused by a full `thinking` budget as meaningful visible-output determinism evidence.

The detailed ledger is in `04_DONOR_DELTA_1.9_TO_2.2_AND_FORWARD_PORT_LEDGER.md`.

## 10. Explicitly rejected automatic ports

Do not automatically import previously rejected MAYBE UX changes:

- dramatically shortening default `status`;
- converting default health output to a new problem-only contract;
- introducing a new global `REBOOT REQUIRED` severity vocabulary outside a concrete need;
- optimistic `STARTING` classification without a reliable readiness signal;
- renaming `Agentic` to `Agent` without a product-wide terminology decision;
- changing `registration unavailable` wording without knowing the real availability condition.

These remain closed unless the operator explicitly reopens them.

## 11. GFX evidence is historical, not wasted

The 2.2 GFX path was deeply qualified. It proved lifecycle safety, rollback, private RADV isolation, multi-model stability and modest performance gains. That evidence supports the decision to archive the experiment intelligently; it does not force the core to keep the architecture.

The durable product conclusion is:

> GFX1013 worked, but the ongoing engineering/build/qualification cost was unreasonable for the measured product benefit.

## 11A. Build authority

The primary RPM build path is the Fedora 44 GitHub Actions workflow in `.github/workflows/build-rpm.yml`. It runs `make release-gate` as an unprivileged builder from frozen Source0/spec inputs and publishes binary/source RPMs plus closed manifests and `release-evidence.json`. A push or PR run is CI evidence; the specific selected GitHub run becomes artifact authority for BC-250 acceptance.

`release-evidence.json` records the Git commit SHA, GitHub Actions run ID, workflow name/reference, frozen Source0 SHA-256, spec SHA-256, release-contract SHA-256, and binary/SRPM NEVRA+SHA-256. Local Fedora builds remain a backup/reproduction path through `scripts/ci-local.sh` or direct `make release-gate` in a matching Fedora 44 environment and are labeled local reproduction evidence. The donor 2.2 decision to make `./build-local.sh --full` the sole authority is explicitly rejected.

## 12. Versioning rule

Do not publish modified clean-core bytes under an already published NVR.

C8 has now assigned the explicitly requested unused identity `bc250-llm-server-0.14.1-1` across the authoritative version surfaces. Do not reuse the inherited 1.9 identity for new clean-core bytes.

The next authority transition is build evidence: ordinary push/PR GitHub runs remain CI evidence; only the explicitly selected workflow-dispatch run may produce the C9 release-selection record.

## 13. Completion condition for this lane

The reconstruction lane closes when:

1. core GFX ownership is absent;
2. baseline core behavior is regression-clean;
3. accepted generic donor improvements are reimplemented and tested;
4. docs/current handovers match the clean architecture;
5. a frozen Source0 passes the integrated source gate;
6. Fedora 44 builds the exact source successfully;
7. the exact RPM passes focused stock-core device acceptance;
8. the project can move back to office-data/RAG/translation work.
