# 0.11.3-2.3

Expected NVR: `bc250-llm-server-0.11.3-2.3`

Operations and operator-UX refinement.

## Implemented

- Make malformed `/etc/bc250-llm-server/models.d/` errors identify offending operator-owned files, preserve them untouched, and give the exact recovery/rerun path.
- Present local maintenance and Raspberry Pi/companion setup as separate optional installer decisions; local maintenance no longer appears gated by Pi setup and both top-level choices remain optional/default-No.
- Keep safe-power guards unchanged while making local protected-port defer messages specific without printing peer addresses.
- Improve agent-mode enter/leave output and add `bc250-agent-mode normal` as an idempotent alias for the existing normal-topology convergence path.
- Add concise topology-aware `Overall` / `Runtime mode` lines near the top of `bc250-status`; report unavailable reboot diagnosis as unknown rather than as an appliance fault.
- Make verifier degradation reporting distinguish root lane failures from dependent unavailable checks, and report skipped authenticated Open WebUI verification explicitly.
- Make degraded status print the supported `sudo bc250-agent-mode normal` recovery path, include skipped checks in verifier headline totals, and point agent-mode exit guidance at the same normal-convergence command.
- Reconcile `/var/lib/bc250-llm-server/swap` runtime creation with the existing packaged/tmpfiles `0750 root:root` contract.
- Clarify maintenance timer history (`last_scheduled`) and make DRY_RUN prune output explicitly separate actual zero deletions/freed bytes from planned/simulated values.
- Make selective identity restore compare canonical pre/post foreign-key violation sets: strict SQLite integrity remains required, pre-existing unrelated violations are tolerated, and any newly introduced violation still fails closed and triggers automatic rollback.
- Summarize identity restore validation with strict integrity state, baseline/new FK counts and explicit rollback success without dumping the unrelated baseline rows.
- Keep canonical generation GPU-journal evidence while moving it out of model aggregates into explicit runtime diagnostics; scripted generation runs already avoid the optional board-note prompt when stdin is not a TTY.

## Deliberately unchanged

- MTP, RAG and translation workflows/models.
- Raspberry Pi/companion architecture or defaults.
- Healthy-live-40-CU semantics and persistent-mode policy.
- Safe-power return semantics and protected-endpoint policy.
- Backup architecture, private-data handling and current-invocation journal filtering.

## Evidence boundary

This is the closed source release. Deterministic source validation and syntax/compile checks are the
release-local gates. RPM/SRPM build, installed `rpm -V`, real SSH survival/power behavior, real
40/40 routing and exact-2.3 device acceptance remain external follow-up work and must not be inferred
from source validation.

## Incremental operations evidence incorporated

Operator-supplied exact-2.2 Batch 04–06 evidence additionally records verified config/users backup creation and retention, successful configuration restore, successful automatic identity rollback, production use-case 4/4, task 6/6 and bounded generation-edge infrastructure 17/17. The raw evidence archive was not independently inspected in the main integration environment, so these remain operator-supplied summarized device observations rather than independently revalidated evidence.

The same Batch 05 evidence exposed the baseline-FK identity-restore validation defect corrected above. Batch 06's apparent new-GPU-failure self-check was a harness false positive; the bounded kernel search itself contained no matching new GPU failure signature.

## Source validation

- repository/RPM preflight: **PASS**;
- complete deterministic Python test suite, executed in split modules after the monolithic runner
  exceeded the execution window without reporting a failure: **438/438 PASS**;
- `bash -n`: **64/64** shell/bootstrap files PASS;
- Python compileall: **PASS**;
- Ruff and ShellCheck: unavailable in this environment, therefore not claimed;
- RPM/SRPM build, package installation and exact-2.3 device qualification: intentionally not run;
  they remain separate external gates.
