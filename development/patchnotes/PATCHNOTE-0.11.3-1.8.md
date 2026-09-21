# 0.11.3-1.8

Expected NVR: `bc250-llm-server-0.11.3-1.8`

Support/maintenance safety and operator-UX refinement.

## Safety fixes

- Correct safe-power TCP endpoint parsing so active local SSH/UI/Ollama sessions really defer power actions.
- Request `poweroff`/`suspend` non-blocking after all guards pass so the decision service exits cleanly.
- Give the restricted Pi forced-command path one narrow exception for its own authenticated SSH control connection; the tuple must exist exactly once, configured safe-power/WOL policy is preserved, and any other protected connection still defers.
- Fix `bc250-40cu status` and `verify` returning rc=1 when persistent boot activation is intentionally disabled while live routing is healthy.

## Model/operator UX

- Correct obsolete `bc250-model install --all` guidance to `sudo bc250-model apply all all`; mutation `--all` now explains the explicit category/selection grammar.
- Reject visible non-`.Modelfile` regular files in the operator overlay instead of silently ignoring a renamed definition.
- Keep new operator metadata on canonical category `experiments`; historical `experimental` remains readable.
- Display MTP as standalone `FETCHED, VERIFIED` / `NOT FETCHED` inventory with no duplicate heading and no installer selection path.
- Report protected storage as protected rather than zero/absent, probe Ollama version through an active lane, and describe the normal inactive agent lane without alarming conflict wording.
- Show disabled-versus-configured maintenance policies explicitly and use useful B/KiB/MiB pruning sizes.

## Model default refinement

- Reduce `exp-qwen38-27b-ista-gsq-rco-iq3-xxs` from 16K to 8K context after sustained 16K RAG operation reached the low-memory safety boundary. This is the same verified GGUF/model identity, so applying the new definition does not require a source re-download.

## Evidence boundary

Installed 0.11.3-1.7 passed full revalidation before this support campaign. Support tests then proved backup creation/integrity, pruning dry-run and normal↔agent/degraded recovery, while also exposing the safe-power and 40-CU-return-code defects fixed here. Real S5/WOL, Pi forced-command shutdown, backup restore and destructive pruning remain follow-up device tests for installed 1.8.


## Source validation

- Repository preflight: PASS.
- Deterministic non-packaging tests: **391/391 PASS**.
- Release/changelog consistency test directly affected by the Release bump: **1/1 PASS**.
- Python compileall: PASS.
- `bash -n`: **64/64** shell/bootstrap files PASS.
- Ruff and ShellCheck were unavailable in this environment.
- RPM/SRPM bundling/build tests were intentionally skipped; GitHub remains the package-build gate.
- Exact installed 1.8 BC-250 support/power qualification is still required.
