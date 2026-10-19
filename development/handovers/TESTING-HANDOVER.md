# Testing handover — clean-core reconstruction

## 1. Ownership split

### Main chat

- deterministic source tests;
- code/docs/package reconciliation;
- clean-core absence audit;
- donor ledger;
- source candidate freeze.

### GitHub Actions / Fedora 44 — primary release-build authority

- full release gate;
- lint/rpmlint;
- RPM/SRPM/payload;
- clean SRPM rebuild;
- exact hashes;
- the specifically selected run becomes artifact authority for BC-250 acceptance.

### Local Fedora workstation — secondary reproduction

- execute the same release gate in a matching Fedora 44 environment;
- reproduce/debug GitHub failures;
- never silently replace the selected GitHub artifact.

### BC-250 device

- exact RPM upgrade/install;
- stock runtime/service convergence;
- live CU routing;
- production inference;
- RAG/translation smoke where required;
- final package integrity.

### Sidechat

- focused investigations with structured handback.

## 2. Current source state

C0-C3 are source-validated at the corrected C3-R1 checkpoint. The rejected first C3 proposition is preserved as review evidence, but its blockers are corrected: `bc250 version` has real execution coverage, `kmod` again covers generic `lsmod` verification, current secondary files are reconciled, and the refined absence/current-guidance checks are integrated into preflight.

The immutable accepted C5-D freeze passed 613/613 deterministic tests across 20 modules: 594/594 package-context tests across 19 modules plus 19/19 host release-pipeline tests. C6 secondary documentation/QC is complete and introduces no runtime behavior change. C7 integrated source validation is complete at 617/617: 598/598 package-context tests across 19 modules plus 19/19 host release-pipeline tests, with tracked-file Source0 equivalence and extracted-Source0 validation. C8 assigns `bc250-llm-server-0.14.1-1` and passes 619/619 source tests: the package-context lane remains 598/598 while the host release-pipeline lane is 21/21 for release-selection/environment/build-root contracts. The C5-C release-source regressions prove that Git-ignored workspace junk cannot enter Source0 and that authoritative GitHub runs reject `HEAD != GITHUB_SHA`; C5-D additionally proves that thinking-only/empty visible generation output has no visible-response hash/determinism eligibility and is recorded `INCOMPLETE`. The authoritative Fedora 44 GitHub build is next. No Fedora build or BC-250 device acceptance is implied by this source result. The primary RPM build path is the Fedora 44 GitHub Actions workflow; local build remains backup/reproduction only.

## 3. First future Fedora success criteria

- exact new release identity `bc250-llm-server-0.14.1-1`;
- selected GitHub Actions workflow-dispatch run ID/workflow identity, `release-evidence.json`, and `release-selection.json`;
- frozen Source0/spec hashes;
- full build success;
- lint/rpmlint success;
- package `%check` success;
- payload contains no unintended GFX artifacts;
- SRPM rebuild success;
- hashes preserved.

## 4. First future device success criteria

- package transaction succeeds from selected predecessor;
- installer converges;
- stock boot/runtime remains normal;
- no core-created GFX artifacts or private RADV override;
- core status/doctor-or-health/verify pass according to final contract;
- representative inference works;
- `model install` Enter-cancel/no-mutation passes;
- package integrity passes.

## 5. Do not repeat historical GFX qualification

The clean-core release is accepted by proving absence + normal stock operation, not by recreating the removed experiment.
