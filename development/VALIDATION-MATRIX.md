# BC-250 validation matrix — current package baseline and next-release workbench

Current release identity: `bc250-llm-server-0.14.1-1.13`.

Exact `0.14.1-1.12` is the accepted dependency/integration DEVICE baseline. Release 1.13 is a bounded package-hardening/UX candidate that deliberately retains the 1.12 Ollama/Open WebUI/Tika pins, four-lane topology, model set and RAG tuning. Evidence never transfers across changed bytes: 1.12 runtime acceptance is baseline evidence, while 1.13 must prove its changed ingestion/provenance/UX surfaces and normal final health.

| Area | Current state | Next evidence |
|---|---|---|
| Release identity | `0.14.1-1.13` assigned to current SOURCE candidate; exact 1.12 remains accepted DEVICE baseline | freeze/build the final 1.13 bytes after all intended next-release changes are merged |
| Clean-core architecture | active GFX/private-RADV/package-owned patched-kernel surface absent | maintain absence during bounded package work |
| 1.12 DEVICE baseline | dependency-depth A–E complete: Open WebUI 0.12.5, Ollama 0.40.13, Tika 4.2.0, malformed-input containment, RAG endurance/restarts, full authenticated revalidation and final health accepted | do not reopen broad 1.12 testing unless a changed 1.13 surface invalidates it |
| 1.13 ingestion hardening | package-owned Open WebUI shim rejects missing/blank/placeholder Tika content and provides explicit no-usable-text/duplicate wording | focused exact-RPM malformed/empty/image-only/recoverable extraction regression plus normal health/verify |
| 1.13 upgrade provenance | RPM `%pre` preserves knowable Open WebUI previous-version provenance and captures hashes only for runtime Modelfiles still proven current under the old package | upgrade from exact 1.12 and verify rollback naming plus `PACKAGE UPDATE PENDING` vs local `DRIFT` classification |
| Optional-model UX | installer says review/reconcile/install, reuses validated data and separates package-update from local-drift counts | exercise upgrade with installed optional models whose packaged Modelfile changed |
| Duplicate-content policy | duplicate Knowledge content is expected rejection, not infrastructure failure; reusable harness recognizes the exact policy outcome | duplicate upload remains explicit, original document remains usable, failed-upload cleanup/orphan state checked where evidence is available |
| Harness corrections | Tika Markdown escapes normalized narrowly; XLSX marker/oracle unambiguous; no-text placeholder is not successful content | retain these semantics in future dependency-depth reuse |
| GitHub authority | explicit selected `workflow_dispatch` remains artifact authority; push/PR runs provide CI evidence | capture 1.13 release evidence/selection only from the final selected build |
| Product-quality work | model/RAG quality campaign remains active separately; DE/FR are primary languages | do not mix quality/model promotion changes into 1.13 unless deliberately selected and separately evidenced |

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
