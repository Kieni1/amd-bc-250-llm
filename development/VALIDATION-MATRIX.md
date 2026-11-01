# BC-250 validation matrix — current package baseline and next-release workbench

Current release identity: `bc250-llm-server-0.20.0-2` (source candidate; not yet BUILD/DEVICE-accepted).

Exact `0.14.1-1.13` remains the DEVICE-accepted predecessor baseline. `0.20.0-2` is the next source candidate and retains the accepted Ollama/Open WebUI/Tika runtime pins while changing campaign/model definitions, Open WebUI desired state and selected quality policies. Evidence never transfers across changed bytes: 1.13 BUILD/DEVICE acceptance does not qualify 0.20.0-2. One historical 1.13 boundary remains honestly `NOT_TESTED`: pre-upgrade exclusion of an operator-modified runtime Modelfile from package provenance.
The authoritative `0.20.0-1` build was not DEVICE-accepted: first normal convergence stopped on the new Office - Generalist candidate because Ollama 0.40.13 rejected the AtomicChat `AD-Q6_K` registry tag as a sharded GGUF. `0.20.0-2` keeps the same model/role policy but switches that source to BC-250-managed direct Hugging Face acquisition of the exact nested GGUF before local Ollama registration.

| Area | Current state | Next evidence |
|---|---|---|
| Release identity | `0.20.0-2` is the numbered source candidate; `0.14.1-1.13` remains the accepted predecessor | final research handover consumed; freeze/build exact 0.20.0-2 and collect new BUILD/DEVICE evidence |
| Clean-core architecture | active GFX/private-RADV/package-owned patched-kernel surface absent | maintain absence during bounded package work |
| 1.12 DEVICE baseline | dependency-depth A–E complete: Open WebUI 0.12.5, Ollama 0.40.13, Tika 4.2.0, malformed-input containment, RAG endurance/restarts, full authenticated revalidation and final health accepted | do not reopen broad 1.12 testing unless a changed 1.13 surface invalidates it |
| 1.13 ingestion hardening | DEVICE PASS: valid/recoverable ingestion preserved; binary-corrupt and image-only no-text inputs fail without placeholder indexing; duplicate rejection is explicit | reopen only if ingestion/shim/dependency behavior changes |
| 1.13 upgrade provenance | DEVICE PASS for observed upgrade/convergence and package-update/local-drift summary; pre-upgrade operator-modified Modelfile exclusion remains honestly NOT_TESTED | retain the limitation; cover it on a future natural upgrade when practical rather than reinstalling 1.12 |
| Optional-model UX | installer says review/reconcile/install, reuses validated data and separates package-update from local-drift counts | exercise upgrade with installed optional models whose packaged Modelfile changed |
| Duplicate-content policy | duplicate Knowledge content is expected rejection, not infrastructure failure; reusable harness recognizes the exact policy outcome | duplicate upload remains explicit, original document remains usable, failed-upload cleanup/orphan state checked where evidence is available |
| Harness corrections | Tika Markdown escapes normalized narrowly; XLSX marker/oracle unambiguous; no-text placeholder is not successful content | retain these semantics in future dependency-depth reuse |
| GitHub authority | the selected 1.13 `workflow_dispatch` build is the accepted artifact authority; push/PR runs remain CI evidence only | require a new explicit selected `workflow_dispatch` build for the subsequent release; never transfer 1.13 BUILD evidence to changed workbench bytes |
| Product-quality work | Steps 3-9 measurement contracts are established; DE/FR remain primary. Existing accepted roles/RAG remain controls, with Office - Generalist and the refreshed candidate set in 0.20.0-2 | build/install exact 0.20.0-2, qualify Generalist/new registrations and changed Qwen/Agent policies, then execute the external corpus/Tika/gold/retrieval campaign and freeze retrieval before further promotion |
| Model-quality follow-up | Qwen `think=true` retained; runaway reasoning reproduced; `presence_penalty=1.5` passed 14/14 twice and is integrated. Ornith remains Agent default; Qwen3.5 4B Agent challenger rejected; contract-first Bash wording passed the canonical Bash/Python/JSON closure 3/3. Translate-Gemma remains with the fail-closed guard; all three known semantic failure families now have product-containment evidence | focused DEVICE qualification of these source changes on exact 0.20.0-2 bytes |

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
- Historical `exp-lfm25-8b-a1b-unsloth-q6-k-xl` `nonthinking-first-pass` evidence remains provenance only; that model is retired from the active 0.20.0 campaign. Current auto-think tests use active profile metadata, including explicit non-thinking Qwen3.5 4B and the new Generalist policy.
- Every Agent profile declares `agent_validation=static-output-contract`; non-Agent profiles declare `not-applicable`.
- `tools=true` is capability metadata only. The existing Agent benchmark does not qualify native Ollama `tool_calls` execution.

| 0.20.0 model-campaign refresh | official/community LFM3, Nemotron, Index-Translate, Spark, Defiant, LFM3-VL and NeoHorse definitions are package-managed; nine exhausted experiments are retired; Office - Generalist is explicit new desired state | SOURCE catalog/profile/Modelfile/Open WebUI/benchmark contract tests; next DEVICE candidate must prove provider acquisition/registration, curated role policy, DE/FR behavior, memory/latency and model-specific translation/OCR/Agent paths |
| 0.20.0 Generalist provenance | AtomicChat uncensored Nemotron is behavior-modified community provenance, not interchangeable with official NVIDIA Bolt; Q6_K + 1.0/0.95 + `think=false`/4096 is the proposed product contract | DEVICE compare against Standard/Advanced office controls, include benign refusal/instruction fidelity, multilingual DE/FR, repetition/visible-answer reliability, memory/load and latency before acceptance |
| 0.20.0 Advanced sampler | normal Advanced/raw Qwen remains `think=true` with 0.7/0.8/top-k-20 but request-level `presence_penalty=1.5`; Advanced Structured remains think=false / presence-penalty 0.0 | focused DEVICE regression against the known backup/constraint/structured cases and packaged revalidation after install |
| 0.20.0 Agent prompt policy | Ornith retained; canonical Bash qualification prompt is contract-first; Python/JSON fixtures unchanged | final closure must prove Bash improvement plus no Python/JSON regression and topology restoration |
| Hardware performance policy | 1850 MHz remains normal ceiling; 2000 MHz gives ~9% prefill but ~1% decode gain and hit thermal cutoff under heavy prefill | no higher-clock work; keep 2000 MHz operator-test-only and report prefill/decode separately |
| Post-1.13 Open WebUI provenance confidence | structured capture distinguishes proven live/previous runtime evidence from an old-package hint; only proven equality may skip migration backup | source tests plus focused DEVICE upgrade/interrupted-upgrade regression in the next candidate |
| Post-1.13 package Modelfile transition evidence | successful model reconciliation consumes only that model's pre-upgrade entry and removes empty state | source state/apply tests plus focused DEVICE reconciliation check |
| Quality campaign control audit | campaign manifest matches exact current Modelfile parameters, role request policy and RAG desired state without mutating production | `bc250 advanced benchmark campaign audit` |
| External corpus inventory | external PDF directory is inventoried without copying corpus data; hashes/sizes/PDF-header sanity/byte-identical duplicates are recorded and annotation remains explicit | `campaign corpus-inventory` on an external directory |
| External corpus boundary | corpus manifest accepts only safe relative external files and verifies SHA-256/size; real PDFs are never package fixtures | campaign corpus validation + packaging/source review |
| Tika extraction quality | extraction scored independently from embedding/generation and raw response/text retained as evidence | `campaign tika-extract` on external corpus |
| Gold evidence binding | gold questions/support anchors are non-empty and present in the exact Tika extraction evidence for the same locked corpus; coverage is reported without an invented balance threshold | `campaign gold-validate` |
| Retrieval-only quality | ranked chunks scored for R@1/R@3/R@5, MRR, support/conflict/exact values and language pairs without generation | `campaign retrieval-score` using a named fresh-index arm |
| Retrieval comparison/freeze | only results from the exact same corpus/arm authority can be compared; no automatic winner; selected arm requires explicit rationale and input hashes are frozen | `campaign retrieval-compare` then `campaign retrieval-freeze` |
| Fixed evidence comparison | exact retrieved chunks are exported only from the frozen retrieval contract and replayed unchanged across answer models | `campaign fixed-export` then `campaign fixed-replay` |
| Translation semantic regression | direct and Open WebUI translation benchmarks reuse the package clause-local modality authority; precise recommendation/negation/prohibition mismatch reasons remain in evidence | source metamorphic tests plus next-candidate direct/Open WebUI translation DEVICE qualification |
