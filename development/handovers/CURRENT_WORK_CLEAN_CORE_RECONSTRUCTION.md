# BC-250 current work handover — clean-core reconstruction from 0.13.1-1.9

## 1. Baseline

```text
source archive: amd-bc-250-llm(10).zip
SHA-256:       79b1a9e60e15764b49d67982d9dd689a338766dc50f21dac2cdb4c1139cd32d6
source NVR:    bc250-llm-server-0.13.1-1.9
Fedora:        44
```

The repository main line is reported to be at this same source state. GFX development is preserved on its own branch.

## 2. Why this baseline is being used

1.9 is the last known-good full build the operator wants to use for the future core.

It already contains some GFX1013 implementation, but the code is earlier and less entangled than the later 1.10–2.2 line. Rather than continue from the highly coupled 2.2 tree, clean the 1.9 core first and then forward-port only worthwhile generic improvements.

## 3. Current integration checkpoint

The immediate accepted source predecessor is **C7 — PASS**. C8 has assigned the new source/package identity **bc250-llm-server-0.14.1-1** and is **SOURCE-READY / GitHub build pending**. C7's immediate accepted source predecessor is **C6**; **C5-D** is the immutable behavioral predecessor, **C5-C** the release-hardening predecessor, **C4** the classification predecessor, and **C3-R1** the clean-core structural predecessor. The active next action is the **C8 authoritative Fedora 44 GitHub Actions build** from this exact 0.14.1-1 source. C7 was validation/bookkeeping only and introduced no runtime behavior.

The first C3 proposition was independently reviewed and rejected for two product defects plus secondary-file/gate issues. C3-R1 keeps the structural C1/C2 removal and corrects those blockers.

Current state:

```text
C0 PASS
C1 PASS
C2 PASS
C3 PASS — C3-R1 source/deterministic checkpoint
C4 PASS — donor classification complete
C5-A PASS — low-risk correctness/supportability port complete
C5-B PASS — model/installer UX port complete
C5-C PASS — release/build hardening complete
C5-D PASS — benchmark semantics complete
C6 PASS — secondary files/documentation QC complete
C7 PASS — integrated source gate complete
C8 SOURCE-READY — 0.14.1-1 identity assigned; authoritative GitHub build pending
```

The preserved first-proposition review is `C3_PROPOSITION_REVIEW_AND_REQUIRED_REWORK.md`. The immutable accepted C5-D predecessor has 613/613 passing deterministic tests across 20 modules (594/594 package-context across 19 modules + 19/19 host release-pipeline). C7 remains the frozen 617/617 source predecessor. The current C8 source gate passes 619/619 across 20 modules (598/598 package-context + 21/21 host release-pipeline). Fedora build/device evidence is still pending.

## 4. C0 — freeze and identity

Before changes:

- preserve the original ZIP unchanged;
- preserve its SHA-256;
- verify `VERSION`, spec release, runtime pins and workbench state;
- record current Git commit/tag independently if available;
- do not infer commit identity from ZIP contents unless proven.

C0 status: baseline archive identity is known.

## 5. C1 — GFX ownership inventory — PASS

Create an explicit inventory rather than deleting by broad grep.

Expected GFX-owned classes include:

- `gfx1013/` sources/patches/manifests;
- `cmd/system/gfx1013.sh`;
- `cmd/benchmark/gfx1013-ab.py` and GFX campaign plumbing;
- CLI command dispatch/completion/help;
- package spec file lists/directories/scriptlets/dependencies;
- install/uninstall references;
- GFX qualification evidence inventory/cleanup;
- monitoring/status/doctor/version JSON fields;
- GFX docs/current README/TLDR sections;
- GFX tests and test fixtures;
- development scope/validation matrix/workbench references;
- any private RADV environment/drop-ins;
- any patched-kernel/BLS lifecycle helpers used only by GFX.

For each entry mark:

```text
REMOVE
KEEP-GENERIC
REWORK
HISTORICAL-ONLY
```

## 6. C2 — remove GFX structurally — PASS

Remove GFX from public and internal core behavior.

Important requirements:

- no `bc250 gfx1013 ...` public command;
- no private RADV path under the core package;
- no patched amdgpu build/prepare/stage/enable/disable/reset lifecycle;
- no GFX package transaction rollback logic;
- no GFX state directory ownership;
- no GFX-only build requirements;
- no GFX-specific JSON/health state;
- no GFX current documentation;
- no GFX device-qualification dependency for releasing the core.

Do not remove stock AMDGPU diagnostics/live-CU functionality just because it mentions AMD/Vulkan.

## 7. C2 absence audit

After removal search current code/docs/tests/spec for at least:

```text
gfx1013
GFX1013
private RADV
/opt/bc250-gfx1013
VK_DRIVER_FILES
PATCHED_BOOT_UNVERIFIED
STOCK_REBOOT_REQUIRED
stage-boot
patched amdgpu
```

Allowed survivors require explicit classification, typically only historical changelog/archived decision records.

The absence audit is a gate, not the only test.

## 8. C3 — clean-core regression baseline — PASS (C3-R1)

C3-R1 proves the clean-core source baseline before donor import. The corrected checkpoint:

- executes `bc250 version` in normal, JSON and short modes with installed and missing RPM identity cases;
- retains `kmod` because generic stock verification uses `lsmod`;
- keeps stock AMDGPU/Mesa/Vulkan/live-CU behavior;
- reconciles current testing, handovers and product docs;
- runs structural GFX-absence and stale-current-guidance gates as normal preflight;
- uses the agreed frozen predecessor filename, while recording the timestamped upload as a byte-identical alias;
- passes all 578 deterministic tests across 19 modules.

This is source validation only. Build and device confidence remain future gates.

## 9. C4 — donor ledger — PASS

C4 is complete. The exact 1.9 -> 2.2 donor delta is classified in `04_DONOR_DELTA_1.9_TO_2.2_AND_FORWARD_PORT_LEDGER.md`: 84 changed paths (66 modified + 18 donor-only), all assigned KEEP / REWORK / DROP / HOLD. No donor code was forward-ported during classification.

The build-policy decision is explicit: GitHub Actions remains the primary Fedora RPM build path; local build is backup/reproduction only.

Do not start C5 by cherry-picking commits. Port one coherent behavior cluster at a time from the written ledger.

## 10. C5 — forward-port groups

Use the exact sequence frozen in the C4 donor ledger. Do not reorder the groups or pull model/installer UX ahead of the smaller correctness fixes.

1. **C5-A — PASS — low-risk correctness/supportability:** Open WebUI inaccessible-path handling; maintenance/restore sourceability; shell nounset fix; test-isolation fix; generic `Web interface`/transition wording; package NEVRA; Vulkan environment verification.
2. **C5-B — PASS — model/installer UX:** combined-catalog model-install workflow, hard cancel/no-mutation behavior, installer grouping, desired/observed Ollama reconciliation, one-next-action, TTY/`NO_COLOR`, and `health` compatibility alias reworked onto current doctor v3 semantics.
3. **C5-C — PASS — release/build hardening:** frozen Source0/spec, Git-tracked-only Source0 authority in worktrees, clean-source identity recheck including `HEAD == GITHUB_SHA` on Actions, deterministic archive/build-cache exclusions, core-only release contract, split checksum manifests, unprivileged Fedora build, fail-fast host/package test layering, transformed payload proof, and machine-readable release evidence — all adapted to GitHub-primary RPM authority.
4. **C5-D — PASS — benchmark semantics:** the exact current thinking/visible-response path was regression-encoded first; generation now separates visible-response identity from hidden thinking, never hashes an empty visible response as deterministic output evidence, and records no-visible-answer measurements as `INCOMPLETE` without weakening performance/quality thresholds.

Ollama 0.40.4, external context-ceiling conclusions, and local-build convenience work remain HOLD and are not prerequisites for C5-A/B/C/D.

C5-A and C5-B deliberately did **not** pull release-pipeline hardening forward; C5-C implements only the classified release/build-hardening cluster, and C5-D implements only the classified thinking/visible-response benchmark semantic correction. Runtime version changes, context-ceiling conclusions, local-build convenience work, and all other HOLD/DROP work remain unported. The immutable C5-D source checkpoint remains validated at 613 deterministic tests across 20 modules; C6 documentation/QC and C7 integrated source validation are complete at 617/617. C8 has assigned 0.14.1-1 and passes 619/619 source tests. Build/device evidence remains pending. Next work is the authoritative C8 Fedora 44 GitHub Actions build. GitHub Actions remains the primary Fedora RPM authority and local build remains backup/reproduction only.

## 11. C6 — secondary files — PASS

C6 reconciled the current secondary/documentation surfaces against completed C5 behavior. It changed no runtime feature, runtime pin, context limit, RPM Release, device state, or CLI semantics.

Completed C6 checks include:

- recorded the immutable C5-D freeze identity (`25be…` archive, `e43a…` canonical manifest, 362 files, 613/613 total baseline);
- rewrote the current validation summary so old 1.9/GFX A1/B/A2 instructions are historical-only, not executable clean-core guidance;
- reframed the accumulated 1.9 qualification narrative and old lane campaign text in `TESTING-STRATEGY.md` as historical/reference material;
- made the five current handover authorities explicit and demoted all other handovers to supporting reference or historical evidence;
- synchronized `docs/OLLAMA.md` with `OLLAMA_VULKAN=1`, `OLLAMA_IGPU_ENABLE=1`, and `GGML_VK_VISIBLE_DEVICES=0`;
- kept GitHub Actions as primary RPM authority and local Fedora execution as backup/reproduction only;
- preserved the immutable C5-D baseline as 613/594/19 historical predecessor evidence while making the C6 source result explicit at 617/598/19;
- final C6 source validation: 617/617 across 20 modules (598/598 package-context across 19 modules + 19/19 host release-pipeline).

## 12. C7 — integrated source gate — PASS

C7 added no product feature. It reran repository preflight, clean-core absence, current-guidance, development scope, shell/Python/JSON syntax checks, all deterministic modules, tracked-file Source0 generation/extraction/equivalence, frozen-source preflight, and package-context tests from extracted Source0. Final result: 617/617 across 20 modules (598/598 package-context + 19/19 host release-pipeline). The inherited 1.9 identity has now been retired for new bytes. C8 assigns the unused clean-core identity 0.14.1-1; it is not device-accepted until the selected authoritative GitHub build and C9 hardware acceptance complete.

## 13. C8 — release identity and Fedora build

The regular release identity `bc250-llm-server-0.14.1-1` is already assigned and source-validated. For the authoritative build:

- do not change Version/Release unless a new source change requires a new candidate;
- freeze deterministic Source0 from the exact selected Git commit;
- test extracted Source0;
- run the authoritative Fedora 44 GitHub Actions workflow in `.github/workflows/build-rpm.yml`;
- use `scripts/ci-local.sh` or direct `make release-gate` only as backup/reproduction in a matching Fedora 44 environment;
- preserve exact RPM/SRPM/source hashes and the GitHub build log/artifacts.

No GFX kernel/Mesa build should be part of the clean-core build gate.

## 14. C9 — device acceptance

Device acceptance is stock-core focused:

- upgrade/install from the selected predecessor;
- installer convergence;
- reboot if normal package/system updates require it;
- stock AMDGPU and live CU routing;
- Ollama/Open WebUI/Tika readiness;
- status/doctor-or-health/verify/version;
- model install cancel/no mutation;
- representative production inference;
- RAG/translation smoke appropriate to changed surfaces;
- package integrity;
- no GFX artifacts/services/drop-ins/boot entries introduced.

## 15. Stop condition

If clean-core removal reveals that a supposedly generic helper is actually coupled to GFX, stop and classify it `REWORK`; do not preserve the coupling just to keep tests green.
