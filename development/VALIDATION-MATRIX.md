# BC-250 validation matrix — current package baseline and next-release workbench

Current release identity: `bc250-llm-server-0.14.1-1.11`.

Release identity 1.11 is assigned to the current SOURCE candidate. Exact 1.10 remains the packaged DEVICE evidence baseline; no 1.11 RPM exists until the authoritative Fedora 44 build completes. This matrix tracks only the evidence needed to move the workbench forward. Detailed historical qualification remains in Git history and compact handover archives; it does not transfer PASS status to changed bytes.

| Area | Current state | Next evidence |
|---|---|---|
| Release identity | `0.14.1-1.11` assigned to current SOURCE candidate; exact `0.14.1-1.10` remains packaged DEVICE evidence baseline | run blocking lint, freeze exact 1.11 Source0/spec, then authoritative Fedora 44 build |
| Clean-core architecture | active GFX/private-RADV/package-owned patched-kernel surface absent | maintain absence during product work and bounded cleanup |
| 1.11 SOURCE checks | governance/export/evidence/LFM benchmark refinements integrated; all 24 modules / 715 tests PASS locally in module-isolated/split runs before release bump | rerun release-owned checks on exact 1.11 identity; blocking Ruff/ShellCheck remain required before freeze/build |
| 1.10 model architecture | exact 1.10 RPM model-management/lifecycle DEVICE campaign PASS; metadata-first contract, schema-4 tracking, provider-aware lifecycle and Open WebUI 0.12.4 remain accepted architecture | do not reopen accepted architecture without affected evidence; retest only changed next-release surfaces |
| RPM `%check` | current workbench package-critical set PASS locally: 156/156 | must pass unprivileged in the next authoritative Fedora 44 SRPM rebuild |
| Release preflight | current workbench release-pipeline preflight PASS: 27/27 plus current-guidance/clean-core/scope checks | rerun after next release identity/freeze |
| Static lint | required Ruff/ShellCheck gate is not executable in the current workbench environment because those tools are unavailable | blocking next-release gate must pass where Ruff/ShellCheck are installed |
| Source0/spec freeze | not started; 1.11 identity is now assigned | freeze only after blocking lint and final release-owned checks pass |
| RPM payload / rpmlint | no 1.11 RPM exists yet | validate exact 1.11 built payload and configured blocking rpmlint in authoritative Fedora 44 build |
| GitHub authority | explicit selected `workflow_dispatch` remains artifact authority | capture next-release `release-evidence.json` + `release-selection.json` from selected build |
| Runtime/UI baseline | exact 1.10 RPM runs Ollama `0.40.8` + Open WebUI `0.12.4`; focused model-management/lifecycle DEVICE blocks PASS | support-bundle/evidence UX changes in this newer workbench require changed-surface device verification after build |
| Managed Documents correctness | accepted prior boundary remains unchanged by current workbench edits | do not rerun large document campaign unless affected code/evidence changes |
| Exact-RPM core functionality / changed-surface acceptance | exact 1.10 model lifecycle/atomicity campaign PASS; 1.11 source is not yet built | after 1.11 build, verify operator export ownership/directory non-mutation/JSON evidence plus bounded source-changed smoke |
| Product-roadmap baseline | stock-first local office-AI direction unchanged; 1.11 is evidence/UX and benchmark-contract refinement | return to measurable document/retrieval and German–French workflow quality after 1.11 acceptance |

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
- `exp-lfm25-8b-a1b-unsloth-q6-k-xl` with `nonthinking-first-pass` resolves benchmark `--think auto` to an explicit `think=false` request and uses the normal latency budget. If the provider still serializes a leading literal `<think>...</think>` block into `response`, the raw output is preserved and tagged `reasoning-present-despite-think-false`; benchmark evidence must not silently strip it.
- Every Agent profile declares `agent_validation=static-output-contract`; non-Agent profiles declare `not-applicable`.
- `tools=true` is capability metadata only. The existing Agent benchmark does not qualify native Ollama `tool_calls` execution.
