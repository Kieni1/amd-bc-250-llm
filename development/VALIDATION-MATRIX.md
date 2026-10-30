# BC-250 validation matrix — current package baseline and next-release workbench

Current release identity: `bc250-llm-server-0.14.1-1.12`.

Release identity 1.12 is assigned to the current SOURCE dependency-refresh candidate. Prior exact-RPM evidence remains historical baseline evidence; no 1.12 RPM exists until the authoritative Fedora 44 build completes. This matrix tracks only the evidence needed to move the workbench forward. Detailed historical qualification remains in Git history and compact handover archives; it does not transfer PASS status to changed bytes.

| Area | Current state | Next evidence |
|---|---|---|
| Release identity | `0.14.1-1.12` assigned to current SOURCE candidate; prior exact-RPM evidence remains historical only | run blocking lint, freeze exact 1.12 Source0/spec, then authoritative Fedora 44 build |
| Clean-core architecture | active GFX/private-RADV/package-owned patched-kernel surface absent | maintain absence during product work and bounded cleanup |
| 1.12 SOURCE checks | dependency/settings integration complete; all 24 repository modules pass in split runs (717/717 after the persisted-prefix apply regression), package-critical 156/156, release preflight 27/27, shell/Python/JSON syntax clean, Source0 smoke clean | Ruff/ShellCheck remain required in the release environment before exact Source0/spec freeze/build |
| 1.10 model architecture | exact 1.10 RPM model-management/lifecycle DEVICE campaign PASS; metadata-first contract, schema-4 tracking, provider-aware lifecycle and Open WebUI model architecture remains accepted | do not reopen accepted architecture without affected evidence; retest only changed next-release surfaces |
| RPM `%check` | current workbench package-critical set PASS locally: 156/156 | must pass unprivileged in the next authoritative Fedora 44 SRPM rebuild |
| Release preflight | current workbench release-pipeline preflight PASS: 27/27 plus current-guidance/clean-core/scope checks | rerun after next release identity/freeze |
| Static lint | required Ruff/ShellCheck gate is not executable in the current workbench environment because those tools are unavailable | blocking next-release gate must pass where Ruff/ShellCheck are installed |
| Source0/spec freeze | not started; 1.12 identity is now assigned | freeze only after blocking lint and final release-owned checks pass |
| RPM payload / rpmlint | no 1.12 RPM exists yet | validate exact 1.12 built payload and configured blocking rpmlint in authoritative Fedora 44 build |
| GitHub authority | explicit selected `workflow_dispatch` remains artifact authority; main pushes and PRs provide CI evidence, superseded push/PR runs cancel while dispatch authority runs do not | capture next-release `release-evidence.json` + `release-selection.json` from selected build |
| Runtime/UI baseline | prior exact RPMs provide historical model/runtime evidence; 1.12 changes Ollama/Open WebUI/Tika bytes | verify four lanes/Vulkan, role switching, persisted Jina prefixes, Tika extraction and one managed-document/RAG flow after build |
| Managed Documents correctness | accepted prior boundary remains unchanged by current workbench edits | do not rerun large document campaign unless affected code/evidence changes |
| Exact-RPM core functionality / changed-surface acceptance | prior lifecycle/atomicity evidence remains historical; 1.12 source is not yet built | after 1.12 build, run bounded runtime/UI/document delta acceptance plus normal topology/verify restoration |
| Product-roadmap baseline | stock-first local office-AI direction unchanged; 1.12 is a bounded dependency/settings refresh | return to measurable document/retrieval and German–French workflow quality after 1.12 acceptance |

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
