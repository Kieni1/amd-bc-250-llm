# BC-250 validation matrix — current release line

Current release identity: `bc250-llm-server-0.14.1-1.10`.

This matrix tracks only the evidence needed to move the current line forward. Detailed historical qualification remains in Git history and compact handover archives; it does not transfer PASS status to changed bytes.

| Area | Current state | Next evidence |
|---|---|---|
| Release identity | `0.14.1-1.10` assigned consistently | freeze this exact NVR for build/device evidence |
| Clean-core architecture | active GFX/private-RADV/package-owned patched-kernel surface absent | maintain absence during product work and any bounded cleanup |
| Changed 1.10 source checks | metadata/model-manager/benchmark/Open WebUI/tracking-state regressions plus release-facing validation PASS locally | run the full authoritative release gate before selecting a build |
| 1.10 model architecture | Batches 1-3 plus coherence review complete; shared validation, schema-4 tracking migration, metadata consumers, provider-aware removal and Open WebUI 0.12.4 are integrated | authoritative lint/build/package gates, then exact-RPM focused device/model delta smoke |
| Full source suite | all 24 modules / 712 tests have module-isolated PASS on the final source tree; broad suite remains advisory rather than the release oracle | keep package-critical/release gates authoritative |
| RPM `%check` | pending authoritative 1.10 build | must pass unprivileged in the Fedora 44 SRPM rebuild |
| Source0/spec freeze | tracked-source migration contract implemented | freeze exact 1.10 inputs in selected build |
| RPM payload | package contract implemented | must pass on built RPM |
| rpmlint | blocking configured package gate | any unfiltered finding blocks artifact evidence; fix the package or document a genuine appliance-specific false positive |
| Authoritative SRPM rebuild | hard release gate | frozen SRPM must rebuild once in an isolated topdir; those exact rebuilt binaries become the artifacts |
| GitHub authority | explicit selected `workflow_dispatch` run | capture `release-evidence.json` + `release-selection.json` |
| Runtime/UI baseline | accepted 1.9: Ollama `0.40.8` + Open WebUI `0.12.3`; candidate 1.10: Ollama `0.40.8` + Open WebUI `0.12.4` | focused 1.10 UI/model integration smoke; do not reopen proven tuning/topology without evidence |
| Managed Documents correctness | accepted in 1.9; 1.10 does not change document lifecycle bytes | do not rerun the large document campaign unless changed code/evidence requires it; use only normal release smoke |
| Exact-RPM core functionality | accepted 1.9 is the unchanged-boundary baseline | run normal 1.10 upgrade/health/verify/topology plus focused changed-surface model/OWUI/state-migration smoke |
| Product-roadmap baseline | 1.9 unifies MTP discovery/explicit preparation and closes 1.8 Managed Documents acceptance defects without changing runtime tuning | after acceptance, return to measurable document/retrieval and German–French workflow quality |

## Current stop conditions

### Blocking current-release coherence

Stop release creation for:

- inconsistent Version/Release/source identity;
- dirty/unbound authoritative Git source;
- current operator/release guidance contract drift;
- development-scope consistency failure;
- Ruff or ShellCheck failure;
- Source0/spec integrity failure;
- package-critical `%check` failure;
- configured rpmlint failure;
- RPM payload mismatch;
- authoritative frozen-SRPM rebuild failure, or failure to publish its exact rebuilt binaries, in the release environment;
- missing/ambiguous artifact identity.

### Advisory/historical material

Do not stop artifact production solely for:

- archive-only wording or historical evidence prose;
- unchanged historical development-scope hashes;
- unrelated noncritical behavioral findings from the broad advisory suite;
- historical campaign expectations.

Current operator/release guidance is not "documentation-only" when it defines release or safety behavior; contradictions there are blocking coherence defects.


### Next-release model metadata/benchmark contract

- Generation latency selection must follow resolved `think` behavior plus package qualification/capability metadata; packaged LFM models receive no family-name exception.
- `exp-lfm25-8b-a1b-unsloth-q6-k-xl` with `nonthinking-first-pass` uses the normal latency budget when `think` is omitted or explicitly false.
- Every Agent profile declares `agent_validation=static-output-contract`; non-Agent profiles declare `not-applicable`.
- `tools=true` is capability metadata only. The existing Agent benchmark does not qualify native Ollama `tool_calls` execution.
