# BC-250 validation matrix — current package baseline and 0.20.0-3 SOURCE candidate

Current release identity: `bc250-llm-server-0.20.0-3` — selected and finalized SOURCE candidate; authoritative BUILD and exact-RPM DEVICE acceptance are pending.

Exact `0.14.1-1.13` remains the DEVICE-accepted predecessor baseline. Evidence never transfers across changed bytes: 1.13 BUILD/DEVICE acceptance does not qualify the 0.20.0 line. One historical 1.13 boundary remains honestly `NOT_TESTED`: pre-upgrade exclusion of an operator-modified runtime Modelfile from package provenance.
The authoritative `0.20.0-1` build was not DEVICE-accepted: first normal convergence stopped on Office - Generalist because Ollama 0.40.13 rejected the AtomicChat `AD-Q6_K` registry tag as a sharded GGUF. `0.20.0-2` repaired that acquisition path and DEVICE testing confirmed Generalist acquisition/registration, repeated convergence/idempotence, normal Open WebUI publication/topology, two complete Agent qualification/restoration cycles, final health/verify (`62 ok / 0 warn / 0 fail / 0 skipped`), no failed systemd units and valid JSON/JSONL evidence. The long run also established a highly reproducible Qwen Advanced reliability tail: 258 Advanced requests yielded 104 PASS / 154 REVIEW with 153 known repeated-reasoning/tail observations (~59%), while Structured was 172/172 PASS. Translation integrity failures remained fail-closed; `18:00` → `18h00` is an oracle/policy review rather than a delivery defect. A focused Qwen 72-vs-72 Advanced DEVICE A/B preserved 72/72 semantic correctness on both sampler arms but did not produce a clear overall reliability win for 1.0/0.95, so 0.20.0-3 retains the current 0.7/0.8 control. 0.20.0-3 fixes the Tika rootful-Podman operator boundary and clock-equivalence oracle, incorporates the deliberate frozen-component refresh, and is now the finalized SOURCE candidate awaiting BUILD/DEVICE evidence.

| Area | Current state | Next evidence |
|---|---|---|
| Release identity | `0.14.1-1.13` remains the accepted predecessor; `0.20.0-3` is the selected finalized SOURCE candidate | authoritative Fedora 44 GitHub BUILD from these exact bytes, then focused exact-RPM DEVICE acceptance |
| Clean-core architecture | active GFX/private-RADV/package-owned patched-kernel surface absent | maintain absence during bounded package work |
| 1.12 DEVICE baseline | dependency-depth A–E complete: Open WebUI 0.12.5, Ollama 0.40.13, Tika 4.2.0, malformed-input containment, RAG endurance/restarts, full authenticated revalidation and final health accepted | do not reopen broad 1.12 testing unless a changed 1.13 surface invalidates it |
| 1.13 ingestion hardening | DEVICE PASS: valid/recoverable ingestion preserved; binary-corrupt and image-only no-text inputs fail without placeholder indexing; duplicate rejection is explicit | reopen only if ingestion/shim/dependency behavior changes |
| 1.13 upgrade provenance | DEVICE PASS for observed upgrade/convergence and package-update/local-drift summary; pre-upgrade operator-modified Modelfile exclusion remains honestly NOT_TESTED | retain the limitation; cover it on a future natural upgrade when practical rather than reinstalling 1.12 |
| Optional-model UX | installer says review/reconcile/install, reuses validated data and separates package-update from local-drift counts | exercise upgrade with installed optional models whose packaged Modelfile changed |
| Duplicate-content policy | duplicate Knowledge content is expected rejection, not infrastructure failure; reusable harness recognizes the exact policy outcome | duplicate upload remains explicit, original document remains usable, failed-upload cleanup/orphan state checked where evidence is available |
| Harness corrections | Tika Markdown escapes normalized narrowly; XLSX marker/oracle unambiguous; no-text placeholder is not successful content | retain these semantics in future dependency-depth reuse |
| GitHub authority | the selected 1.13 `workflow_dispatch` build is the accepted artifact authority; push/PR runs remain CI evidence only | require a new explicit selected `workflow_dispatch` build for the subsequent release; never transfer 1.13 BUILD evidence to changed workbench bytes |
| Product-quality work | Steps 3-9 measurement contracts are established; DE/FR remain primary. 0.20.0-2 DEVICE already proved Generalist convergence and Agent restoration; 0.20.0-3 SOURCE repairs the Tika campaign privilege interface and translation clock grading | after the finalized SOURCE bytes are built, repeat only affected changed-surface DEVICE blocks plus final health/topology, then continue reboot, clean-baseline upgrade and external corpus/Tika/gold/retrieval execution |
| Model-quality follow-up | Qwen Advanced remains on the current 0.7/0.8 sampler after a focused 72-vs-72 A/B found mixed reliability evidence; repeated-reasoning/latency remains REVIEW. Translate-Gemma remains fail-closed and the clock-rendering oracle false positive is corrected in 0.20.0-3 SOURCE | preserve the three Advanced cases for future model/settings comparisons; on exact 0.20.0-3 DEVICE recheck only changed translation/Tika surfaces plus normal final state |
| Campaign Tika DEVICE path | 0.20.0-2 operator invocation looked in the rootless Podman namespace while Open WebUI/Tika are rootful Quadlets; privileged adjacent execution proved the package runtime path itself works | 0.20.0-3 keeps the campaign operator-owned and bridges only Podman access into the rootful package namespace; the final built candidate must pass the bounded one-document operator extraction chain on DEVICE |
| Translation clock preservation | runtime fail-closed guard remains identifiers/currency/percentages/modality; benchmark quality grading now treats clock values semantically | repeat the known `18:00` → `18h00` case and modality cases with machine evidence; semantic clock equivalence must pass without weakening standalone numeric checks |

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

| 0.20.0 model-campaign refresh | official/community LFM3, Nemotron, Index-Translate, Spark, Defiant, LFM3-VL and NeoHorse definitions are package-managed; nine exhausted experiments are retired; Office - Generalist is explicit new desired state | SOURCE catalog/profile/Modelfile/Open WebUI/benchmark contract tests; 0.20.0-2 already proved Generalist acquisition/convergence and Agent restoration, while remaining role/model-quality, translation/OCR and campaign evidence stays scoped to the final changed candidate |
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
| Qwen Advanced policy A/B | COMPLETE: 72 Advanced observations/arm; both 72/72 semantically correct; aggregate tails 62.5% → 51.39%, but constraint stayed 100%, insufficient regressed slightly, and candidate p95 latency/reasoning worsened | retain current 0.7/0.8 production sampler; keep repeated-reasoning/latency as REVIEW and preserve the comparison prompts |
