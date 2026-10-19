# BC-250 main-chat working rules and instructions — clean-core reconstruction

## 1. Start from current authority

The frozen 1.9 ZIP is the reconstruction base. The 2.2 line is donor/reference evidence. Do not let older momentum redefine current scope.

## 2. One canonical working tree

At any moment there is exactly one current clean-core source tree.

Tests, patches, generated archives, documentation and handovers must all derive from that tree.

Do not patch one ZIP while validating another.

## 3. Freeze before editing

For every externally supplied baseline or donor artifact:

- record filename/commit/tag;
- calculate SHA-256 where practical;
- extract once into a working tree;
- do not mutate the frozen original;
- state which artifact is authority for each claim.

## 4. Work in explicit phases

Current phases:

```text
BASELINE
REMOVE-GFX
CORE-REGRESSION
DONOR-PORT
QC
SOURCE-FREEZE
FEDORA-BUILD
DEVICE-ACCEPTANCE
```

Do not mix GFX removal and a large donor feature port in the same unreviewable change.

## 5. Current clean-core checkpoint rule

Accepted immutable C5-D freeze:

```text
amd-bc-250-llm-clean-core-C5-D.zip
SHA-256: 25be3783716451c84f54209ae16a38c5de1ef1675c4b579fd02cfff08865c710
canonical manifest: e43ab0244de09bc4fc1981db36d956860e6d01715566fe91a9597c869b59e651
source files: 362
613/613 deterministic tests across 20 modules
```

Immediate accepted source predecessor: **C7 — PASS** (integrated source gate complete). Current C8 source identity: **bc250-llm-server-0.14.1-1 — SOURCE-READY; authoritative GitHub build pending**.

C7 source predecessor: **C6**. Immutable behavioral predecessor: **C5-D**. Release-hardening predecessor: **C5-C**. Classification predecessor: **C4**. Clean-core structural predecessor: **C3-R1**. C5-D adds only the ledger's benchmark-semantics correction; HOLD/DROP work remains unimplemented.

```text
C0: PASS
C1: PASS
C2: PASS
C3: PASS
C4: PASS
C5-A: PASS
C5-B: PASS
C5-C: PASS
C5-D: PASS
C6: PASS
C7: PASS
C8: SOURCE-READY (0.14.1-1; GitHub build pending)
```

The original C3 proposition is rejected historical review evidence only. Do not resume correction work from it, and do not redo the structural GFX removal. C3-R1 closes the reviewed blockers: the public `version` command is execution-tested, `kmod` is restored for stock verification, current guidance is reconciled, and the refined structural gates are part of preflight.

C4 is complete in `04_DONOR_DELTA_1.9_TO_2.2_AND_FORWARD_PORT_LEDGER.md`: every exact 1.9 -> 2.2 changed path is classified as KEEP / REWORK / DROP / HOLD. C5-A is complete with the low-risk correctness/supportability cluster. C5-B is complete with the classified model/installer UX cluster: interactive combined-catalog `model install` with hard no-mutation cancellation; grouped installer completion; desired/observed Ollama reconciliation; one RPM next action; TTY/`NO_COLOR` handling; and a `health` compatibility surface reworked onto the current doctor v3 contract. C5-C is complete with the GitHub-primary release/build-hardening cluster: frozen Source0/spec inputs, Git-tracked-only Source0 authority in worktrees, clean-source identity recheck with `HEAD == GITHUB_SHA` on authoritative Actions runs, deterministic build/cache exclusions, a core-only release contract, unprivileged Fedora builds, package-context test layering, split checksum manifests, transformed payload proof, and machine-readable release evidence. C5-D is complete with the benchmark-semantics correction: visible response identity is separate from hidden thinking, thinking-only/empty visible output is not hashable determinism evidence, and no-visible-answer generation measurements are `INCOMPLETE` without weakening thresholds.

Current C8 source deterministic baseline: **619/619** across 20 modules (598/598 package-context across 19 modules + 21/21 host release-pipeline). C7 remains the frozen 617/617 source predecessor; the accepted C5-D freeze remains 613/613 and is not redefined.

Active next action: **C8 — authoritative Fedora 44 GitHub Actions build.** The new unused identity **0.14.1-1** is assigned across source authority. Ordinary push/PR runs are CI evidence; only an explicitly selected workflow-dispatch run becomes release artifact authority and emits the C9 selection record. Do not import HOLD/DROP work, runtime upgrades, context-ceiling conclusions, or device work. Keep source/build/device evidence separate and do not inherit 2.2 qualification.

## 6. KEEP / DROP / REWORK is mandatory

Every meaningful later-line change considered for forward-port must be classified before implementation.

A useful idea implemented inside GFX code is `REWORK`, not `KEEP by cherry-pick`.

## 7. Exact regression before fix

When a defect is known, reproduce it or encode its exact state before changing code where practical.

For removal work, preserve before/after evidence for important package surfaces and public commands.

## 8. Test behavior, not only strings

For stateful commands assert:

```text
starting state
command/action
return code
resulting state
human output
machine output if applicable
mutation/no-mutation
```

## 9. Test the next failure before handoff

After the requested change passes, ask what the operator will do next and test the likely deterministic failure class before handing off.

This rule caught multiple avoidable 2.x external iterations and remains binding.

## 10. Secondary-file audit is part of implementation

A code change is incomplete until relevant secondary surfaces are reviewed:

- README/TLDR;
- topic docs;
- changelog/current workbench state;
- development scope;
- release/build contracts;
- RPM spec/manifests;
- help/completion;
- tests/fixtures;
- handovers/scripts.

Historical evidence must not be rewritten to pretend it originally emitted new behavior.

## 11. First-failure discipline

Preserve the first authoritative failure and classify it before stacking speculative fixes.

Do not turn a reviewer-script false failure into a product fix. The GFX PREPARED queue-attestation incident is the canonical reminder.

## 12. Source/build/device authority are distinct

Use:

```text
SOURCE-VALIDATED
BUILD-VALIDATED
DEVICE-VALIDATED
```

Never inherit an exact-artifact PASS across changed bytes.

## 13. Timeouts are not failures or passes

If a monolithic suite exceeds the environment window:

- report the timeout honestly;
- rerun deterministic modules in bounded batches;
- record actual module/test outcomes;
- do not label the timeout as a product regression.

This bounded-batch method proved useful during the 2.2 UX QC pass and should remain standard.

## 14. Public/private output boundary

Human-facing output should be readable and action-oriented.

Machine-readable/diagnostic output must preserve exact identifiers.

TTY color rules:

- green: successful/ready/verified;
- amber: warning/action required;
- red: failure/blocked/recovery;
- cyan: informational/off/no-change/cancelled;
- respect `NO_COLOR`;
- do not emit ANSI escapes to JSON, pipes or non-TTY captures.

Color is supplemental; text must remain sufficient without it.

## 15. One-next-action rule

When operator action is required, normal output should end with one authoritative next action wherever possible.

Do not present optional work as if it competes with a required step.

## 16. Return codes are API

Tests and docs must agree with command return codes. A friendly message cannot silently change script semantics.

## 17. No-mutation promises require proof

If output says `No changes were made`, compare relevant files/state/service/boot metadata in tests.

## 18. Package changes trigger package review

Any spec/install/uninstall change requires at least:

- packaging tests;
- source/install manifest checks;
- scriptlet review;
- syntax/static checks;
- release-pipeline/preflight checks;
- current docs/handovers update.

## 18A. RPM build authority

The primary RPM build path is the Fedora 44 GitHub Actions workflow in `.github/workflows/build-rpm.yml`, which runs the repository release gate and publishes binary/source RPM artifacts.

Local builds are backup/reproduction only. Use `scripts/ci-local.sh` or the same `make release-gate` in a matching Fedora 44 environment when GitHub is unavailable or when reproducing a CI failure. Do not reintroduce the 2.2 local-only `build-local.sh --full` authority model.

## 19. Lint is real evidence

Run Ruff/ShellCheck when available. If unavailable locally, say so and leave the authoritative Fedora lint gate pending.

Do not convert missing tooling into a green lint claim.

## 20. Greenfield freedom is intentional

The project may remove previously engineered complexity when the product tradeoff is poor.

Deep qualification is evidence, not a sunk-cost mandate.

## 21. GFX policy for the core

Current mainline policy:

> The core package is being reconstructed with no GFX1013 ownership.

Do not add compatibility shims, dormant enums or optional GFX fields “just in case” unless the operator explicitly requests a core/extension integration contract later.

The standalone GFX repository is separate.

## 22. Preserve normal AMD functionality

Do not equate `amdgpu`, Vulkan or CU-routing references with GFX1013 automatically.

Stock AMDGPU and existing live CU routing remain core features when they do not rely on the experimental replacement module/private RADV path.

## 23. Model workflow rules

Keep production defaults conservative while allowing explicit experimentation.

For `model install` forward-port the accepted safe-cancel UX:

- Enter can cancel;
- cancellation does not mutate model state;
- final output should confirm `Cancelled — no changes made.`;
- use `Experimental models:` rather than the grammatical error `Experiments models:`.

Do not automatically rename the established `Agentic` category.

## 24. Benchmark output semantics

Thinking-capable model APIs may separate `thinking` from visible `response`.

A determinism test must explicitly define what identity is being checked. Do not hash an empty `response` and call it visible-output stability when the model consumed its budget in `thinking`.

Do not weaken thresholds to make a benchmark pass; fix the measurement definition.

## 25. Documentation truth

Current docs describe current behavior. Historical docs describe historical behavior and are clearly labeled.

When removing GFX, do not leave current docs telling operators to run GFX commands that no longer exist.

## 26. Artifact delivery

For substantial checkpoints provide:

- exact source archive;
- SHA-256;
- concise handover;
- patch/diff when useful;
- explicit confidence level and remaining gates.

## 27. No background promises

Do the work in the current interaction. Do not promise future completion outside a scheduled automation.

## 28. Candidate handoff rule

A candidate is not ready because the requested line changed successfully.

It is ready when implementation, direct tests, neighboring regressions, secondary files, source identity, packaging/static gates and the likely next external failure have all been reviewed.
