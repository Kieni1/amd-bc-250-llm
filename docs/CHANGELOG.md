# Changelog

## 0.11.3-1.4 - 2026-09-19

- Add two bounded Qwen3.8 27B ISTA GSQ/RCO experiments without changing production roles: IQ3_XXS is the deployability/RAG-oriented candidate at 16K with Qwen3.8 non-thinking sampling, while the existing IQ3_S entry becomes the quality-first main-model experiment at a safer 8K with Qwen3.8 thinking-mode sampling. Both are text-only and remain opt-in experiments.
- Add disabled download-only `qwen3.8-27b-ymq-xs-ti-mtp` as a same-class Qwen3.8 MTP challenger to the existing HauhauCS IQ2_M control. Keep context/draft settings matched at 8192/2 so the first device comparison isolates model/quant differences; MTP remains explicit opt-in and hardware-unqualified.

- Record historical exact-0.11.3-0.4 MTP Phase-1 evidence: Qwen3.5 9B, Qwen3.6 27B and HauhauCS Qwen3.8 27B pass same-target baseline-vs-MTP qualification with deterministic parity; the Qwen3.6 35B-A3B stock 8K/full-GPU baseline does not safely fit and should not be rerun unchanged.
- Move the failed Qwen3.6 35B-A3B MTP candidate out of the active catalog into a source-only MTP graveyard. Historical evidence is retained, but routine list/fetch/run/compare no longer exposes a candidate with no current safe retest path.
- Remove the brittle installer unit simulation that expected a mocked package install to create real `/usr/bin` assets; retain a host-independent static boundary check for backup-export SSH preparation instead.
- Keep packaged MTP draft defaults unchanged while corrected Phase-2 optimization continues. The first depth sweep repeated defaults and is noise-floor evidence only; the corrected canary proves the override path works, and `bc250-compare-mtp` now records/verifies requested versus effective draft depth before accepting MTP evidence.

- Record the completed BC-250 RAG finalist campaign. `bc250-office-documents` / Gemma E4B remains the production document/RAG default on the current 16 GiB profile: both finalists passed short authenticated Open WebUI RAG, but Gemma completed 42/42 continuous-residency turns with about 2.7 GiB MemAvailable remaining while Qwen 9B reached the campaign's 512 MiB safety floor after only a few resident subruns. Qwen remains the separate higher-quality general-office option; this is a sustained-memory-margin decision, not a semantic-quality rejection.
- Make RAG residency restoration preserve the starting model **set** while allowing each Ollama service's configured/default keep-alive policy to apply; stop forcing a synthetic 30-minute lifetime when reloading pre-existing models.
- Rename the resident-session summary field from the inaccurate `cumulative_swap_growth_mib` to `swap_peak_delta_mib`, matching its actual definition: peak observed swap minus starting swap.
- Reconcile current development memory with completed deterministic source validation and clarify that port 11434 is an interactive main/product-role lane. GPT-OSS remains the deep-reasoning and worst-case-memory production reference, not a permanently warm universal main model.
- Keep whole-appliance resource thresholds, Open WebUI desired state, model bytes, runtime topology and MTP behavior unchanged. The final RAG hardware evidence was collected on exact installed 0.11.3-0.4 and is not relabelled as 1.4 qualification.

## 0.11.3-1.3 - 2026-09-19

- Make direct `rag-quality` state-preserving: snapshot the starting model residency on the main and embedding Ollama lanes, isolate the benchmark as before, then restore and verify the starting residency set on every exit path. Restoration failure is infrastructure failure rather than a warning.
- Extend the existing telemetry contract instead of adding another sampler: RAG qualification now records per-request MemAvailable start/min/end/drift and swap start/peak/end, and canonical RAG summaries expose the chronological resident-session view including swap peak delta.
- Reload restoration is model-type neutral: the shared Ollama client first tries the normal generation load path and falls back to `/api/embed` for embedding-only registrations.
- Keep the current RAG quality thresholds, 128 MiB hard floor / 512 MiB informational headroom policy, model choices, Open WebUI configuration and long-residency experiment scope unchanged.
- Release 1.3 remains pre-release source work until external RPM build and exact-source BC-250 qualification are completed.

## 0.11.3-1.2 - 2026-09-19

- Fix the model-manager install/convergence output helper so nested header rendering binds the current label/provider explicitly, resolving Ruff B023 without suppressions or behavioral compatibility code.
- Keep `models/modelctl.py` executable in the source artifact (`0755`); the existing RPM install manifest continues to install it as executable mode `0755`.
- Carry forward the 0.11.3-1.1 RAG/Open WebUI/MTP hardening and the unpublished 0.11.3-0.5 installer/maintenance changes unchanged. No model, runtime topology, benchmark policy, or qualification threshold changes are introduced by 1.2.
- Release 1.2 remains pre-release source work until external RPM build and exact-source BC-250 qualification are completed.

## 0.11.3-1.1 - 2026-09-19

- Carry the unpublished 0.11.3-0.5 installer/maintenance and revalidation-diagnostic refinements forward into the next RPM release line; production models, service topology, MTP model/runtime settings and hard resource thresholds remain unchanged.
- Fix deterministic RAG acceptance false negatives by using boundary-aware matching for phrases/dates/numbers/IDs/currency instead of naïve substring checks. Add explicit `required_any_groups` and case-scoped `numeric_values` fixture contracts rather than fuzzy or LLM-based grading.
- Add deterministic RAG language evidence with `match`, `other` and `not-measurable` states. Language-neutral numeric/identifier answers can remain valid without being falsely claimed as a positive language match.
- Keep direct RAG scoring dimensions independent: target retrieval, all-required-source retrieval, fact/abstention, language and citation are recorded separately, with compatibility answer/citation fields retained for existing evidence consumers.
- Add exact expected-case completeness checks to canonical summaries used by `rag-quality`; missing, duplicate or unexpected case IDs are structural failures and remain separate from semantic quality and infrastructure status.
- Make `owui-rag` resolve the real Open WebUI model surface before creating temporary benchmark state: exact active preset IDs are accepted directly, raw Ollama base IDs auto-resolve only when one active preset matches, and ambiguous/unknown selections fail with actionable preset IDs. Only the sanitized active preset-to-base mapping is retained in benchmark metadata.
- Treat Open WebUI HTTP response, not merely service activation, as readiness for the product-path RAG benchmark; allow a bounded five-minute startup window for slow restarts.
- Harden MTP comparison cleanup so process-group signals require proof that the launched llama-server PID is both the session leader and process-group leader; otherwise signal only the direct child.
- Release 1.1 remains pre-release source work until final deterministic/package/archive closure, external RPM build and exact-source BC-250 qualification are complete.

## 0.11.3-0.5 - 2026-09-19

- Improve the guided installer maintenance UX: ask once whether any optional maintenance/Pi setup is wanted, default to no, then keep local BC-250 maintenance and Raspberry Pi integration as independent choices. Existing local policy can be left unchanged explicitly.
- Verify selected optional setup instead of merely printing status: protected maintenance configuration, enabled timer activity, dry-run pruning safety, restricted Pi account/sudo/SSH state and read-only export prerequisites are checked after configuration.
- Replace the long flat installer command tail with compact Validation/benchmark, Models/runtime lanes and Further setup blocks, followed by the installed documentation root and the important `/etc`, `/var/lib`, revalidation-results and installer-log paths.
- Keep revalidation PASS/FAIL policy unchanged while making two non-failing conditions visible under `Diagnostics`: tight resource headroom below 512 MiB MemAvailable (hard failure remains 128 MiB) and accepted use cases that reach their generation output budget.
- Release 0.5 is still an in-progress source iteration; packaging/archive closure and external/device qualification are intentionally pending.

## 0.11.3-0.4 - 2026-09-18

- Harden the experimental MTP lane before its first BC-250 hardware campaign: `bc250-run-mtp` now verifies protected manager state/SHA, refuses an occupied port or stale llama-server, enforces a launch-memory floor, validates runtime flags/access, and launches the external server as the `ollama` service user rather than root.
- Replace unrelated Ollama-vs-MTP timing with a controlled same-target comparison: `bc250-compare-mtp ID` runs the same GGUF sequentially through the same llama.cpp build/settings with MTP disabled and enabled, then records throughput, draft acceptance, memory/swap, runtime/model identity, server logs and kernel/GPU-fault evidence.
- Expand the disabled download-only MTP catalog to a bounded first-campaign set: Qwen3.5 9B, retained Qwen3.6 27B control, HauhauCS Qwen3.8 27B IQ2_M, and Qwen3.6 35B-A3B. MTP remains outside generic convergence and has no Ollama Modelfiles.
- Refine the install-time model pass after a real 0.11.3-0.4 installer smoke: honor catalog suppression, summarize fully current required models, keep current picker rows compact, skip the intentionally inactive agent registration probe, bound other local Ollama registration probes, and keep MTP out of the generic picker/combined `apply all` path entirely. GGUF provenance/SHA behavior is unchanged.
- Keep MTP qualification fail-closed on completion integrity, server survival, kernel-journal capture, severe GPU/kernel faults and draft-acceptance evidence; move the reviewed external llama.cpp starting baseline to `b10964` / v0.4.1 now that Qwen3.8 is in the funnel. No production model, Open WebUI role, normal Ollama topology, quality threshold, CU/governor policy or revalidation acceptance rule changes.

## 0.11.3-0.3 - 2026-09-18

- Restore the install-time model picker to state-rich output by consuming compact shared model-state inspection instead of turning `bc250-model list` back into a runtime/protected-state operation.
- Improve `bc250-model status` UX: `Upstream: not checked` now points to `--online`, while `--verbose` shows catalog source repository, revision and verified local SHA-256 when available.
- Tighten the package-owned Open WebUI tag-generation prompt after repeated real-device `tags-de` double-JSON failures: broad and specific tags must share one `tags` array and the task must emit exactly one raw JSON object with no prose/Markdown. The strict evaluator and 128-token budget are unchanged.
- Make non-severe GPT-OSS/Jina context diagnostics concise and policy-explicit (`previous -> current prompt tokens`, PASS/not-severe) without changing the severe-truncation threshold or qualification outcome.
- Record installed `bc250-llm-server-0.11.3-0.2.fc44.x86_64` revalidation v4.2 as historical device evidence: installer verification 54/0/0, infrastructure/restoration/full coverage PASS, task 5/6 on `tags-de`, and the bounded GPT-OSS/Jina context diagnostic surfaced as intended.
- Keep production model identities, normal service topology, CU/governor policy, Open WebUI role assignments and benchmark thresholds unchanged.

## 0.11.3-0.2 - 2026-09-18

- Repair the `bc250-fetch-mtp` public route after the model-manager grammar rewrite: it now explicitly dispatches to `apply mtp --include-disabled`, so packaged disabled MTP candidates can be downloaded for bounded testing without editing the catalog or making them part of generic convergence.
- Preserve stable global model indexes for the separate MTP TOML catalog, matching the documented selection contract between category and combined views.
- Enforce `--revision` / `--sha256` as true one-model overrides before an `all` selection is split into per-category operations.
- Improve MTP operator flow and evidence guidance: exact fetch/status/run commands, missing-source recovery guidance, explicit download-only removal semantics, and current real-device qualification requirements are documented. MTP remains experimental, disabled by default and unqualified on BC-250 until the external llama.cpp campaign runs.
- Reconcile secondary lifecycle surfaces: package asset discovery now uses unprivileged `bc250-model list`, current handovers agree on Release 0.2, and README/TLDR/model/specialist guidance exposes the explicit disabled-MTP preparation route.
- Keep the deterministic source gate host-independent by removing the jq-backed edge-diagnostic integration case from unit coverage; the RPM still requires `jq`, and that shell/runtime path is qualified on the installed BC-250 instead.
- Keep production model roles, Open WebUI policy, Ollama topology, revalidation v4.2 semantics, governor/CU policy and quality thresholds unchanged.

## 0.11.3-0.1 - 2026-09-18

- Redesign `bc250-model` around explicit catalog/state/lifecycle operations: `list`, `status`, `path`, `apply`, `refresh`, `unregister`, `remove`, and `purge-retired`; keep legacy forms as actionable migration errors rather than aliases.
- Make one shared model-state inspector authoritative for source/provenance validity, runtime Modelfile drift, registration state and optional moving-revision update checks; `apply` consumes the same state that `status` exposes.
- Separate reconciliation from deliberate source refetch: `apply` reuses verified GGUFs and repairs registration/Modelfile drift, while `refresh` explicitly fetches source bytes again. `unregister` keeps manager-owned GGUF/state; `remove` deletes it only after registration removal succeeds.
- Migrate active installer/model wrappers/current quality harnesses and current-facing documentation to the new command contract. Preserve historical campaign/changelog command syntax as historical evidence.
- Advance `bc250-revalidate` to harness v4.2 for the 0.11.3 package target: surface non-severe context truncation as an informational diagnostic, keep the dedicated GPT-OSS/Jina stage as the deep GPT-OSS resource check instead of repeating GPT-OSS in the generic edge sweep, and replace successful intermediate full snapshots with lightweight checkpoints while retaining full preflight/agent/final/failure evidence.
- Keep runtime topology, model definitions, Open WebUI role policy, quality thresholds and the 0.11.2-0.6 coding-agent/task behavior unchanged in this model-manager rewrite.

## 0.11.2-0.6 - 2026-09-18

- Preserve genuine task quality failures without cascading parse failures into misleading language/relevance causes; canonical benchmark summaries and `bc250-revalidate status` now identify failed case IDs and point at their canonical `results.jsonl` evidence.
- Tighten agent static qualification: literal reasoning markers are a format failure, while NUL-safe `xargs -0 -r -n1 basename` is accepted as valid basename extraction and omission of `-r` remains an empty-directory robustness failure.
- Move `bc250-code` from raw `/api/generate` response extraction to `/api/chat` with `think:true`; write only `message.content`, require terminal completion, refuse `done_reason=length`, reject reasoning-marker contamination, preserve exact final-content bytes, and retain atomic file replacement. `CODING_AGENT_NUM_PREDICT` is an explicit positive-integer override; the default remains 3072 pending real-device route/budget qualification.
- Add `agentic-qwen35-4b-khazarai-q6-k` and `agentic-gemma4-e4b-sol-fable-q4-k-m` as opt-in compact challengers. Ornith remains the coding/agent baseline; no candidate is promoted or retired by this release.
- Record the installed `0.11.2-0.5.fc44` full revalidation: infrastructure/restoration/full coverage passed, Open WebUI translation passed, agent passed 3/3, and task remained a real 5/6 quality result because `tags-de` emitted two JSON objects.
- Keep coding-helper source validation host-independent: remove the redundant fake-runtime subprocess case that accidentally required runner `jq`; retain direct contract assertions and packaged shell-syntax validation. Runtime `bc250-code` still requires `jq` as declared by the RPM.

## 0.11.2-0.5 - 2026-09-18

- Fix the installed `bc250-revalidate` `owui-translation` stage: benchmark fixtures now resolve through the package share tree (`/usr/share/bc250-llm-server/benchmark`) instead of deriving a source-only `/usr/examples/...` path from the installed libexec location.
- Move package-resource selection into `benchmark_common.py` and reuse it for category fixtures, Open WebUI translation fixtures and the package-owned Open WebUI desired state. Explicit `BC250_BENCH_FIXTURES` / `BC250_SHARE` overrides stay authoritative, while source-tree runs prefer their own checkout instead of an older installed RPM.
- Add focused regression coverage for source/install/override resource resolution and for the Open WebUI translation command consuming the shared resolver.
- Carry forward the GitHub validation fixes from the 0.4 follow-up: installer tests provide a hermetic `jq` test double instead of depending on the CI image, and `tests/test_openwebui.py` has Ruff-compliant import ordering.
- Keep all model, runtime, topology, quality thresholds and revalidation harness policy unchanged; this is a packaging/qualification reliability release.

## 0.11.2-0.4 - 2026-09-18

- Make active package-owned Open WebUI roles operationally complete by ensuring all of their base models during `bc250-install`; optional selection now means experiments/rollback/agent/other extras rather than models required by active UI roles.
- Advance `bc250-revalidate` to harness v4.1: pin direct Translate-Gemma qualification to the promoted 2048-token budget, add an authenticated canonical `owui-translation` screen through the actual DE→FR / FR→DE role IDs, and show canonical quality-failure causes in the completed dashboard.
- Fix the French task-title semantic fixture to recognize `réglementaire`/`reglementaire`, matching the useful live `Traduction réglementaire` result instead of reporting a false relevance failure.
- Add `bc250-openwebui-setup status --verbose` for human-readable verified role/task/RAG/Function state and make `bc250-verify` require every active Open WebUI role base model to be registered on the main lane.
- Record the real installed `0.11.2-0.3` revalidation baseline and authenticated production translation smoke; keep the production model, Stage-2E prompt/filter, Ollama/KV/CU/governor and power policy unchanged.

## 0.11.2-0.3 - 2026-09-18

- Keep the maintainer-approved Translate-Gemma production switch and reconcile decisions/testing docs so LFM is consistently rollback/reference rather than the current production translator.
- Make `quality-checks/history/` source-only in the RPM; retain historical campaigns for archaeology while the supported current task/translation screens carry forward the relevant safety lifecycle.
- Make Open WebUI translation evidence final-RC recording authoritative after restoration, credential cleanup and archive creation, matching the direct-screen evidence-integrity rule.
- Keep the exact Stage-2E prompt/wrappers, `max_tokens=2048`, omitted thinking policy, task model, runtime topology, CU/governor policy and production model identities otherwise unchanged.

## 0.11.2-0.2 - 2026-09-18

- Make `task-lfm25-1.2b-instruct-liquidai-q6-k` the sole active task-lane model and retire the weak Gemma 3 1B fallback/control to the source graveyard.
- Promote Stage-2E-selected Translate-Gemma to `prod-translate-gemma4-sub-e4b-17s-q4-k-xl`; make the explicit DE→FR / FR→DE Open WebUI roles production roles, retain LFM 8B only as `exp-lfm25-8b-a1b-liquidai-q6-k`, and retire superseded Hunyuan/Ministral/experimental-Translate identities.
- Restore `ollama-embedding.service` coverage in task survival/recovery checks and restore authoritative translation evidence final-RC handling after privacy/archive finalization.
- Refresh `COMMANDS.md` executable fences/privilege coverage, current model/quality docs, validation strategy and durable handovers; remove duplicated dated specialist handovers after preserving their durable evidence.
- Keep runtime/Ollama/KV/CU/governor topology unchanged; the new production translation identity still requires installed-device product-path verification on the BC-250.

## 0.11.2-0.1 - 2026-09-18

- Start the 0.11.2 line from the unpublished Stage-2E translation integration while keeping its exact system prompt, direction wrappers, 2048-token budget and production-promotion boundary unchanged.
- Resolve Ruff findings by removing one unused translation variable/import, using `TypeError` for invalid message container/content types, and making the focused wrapper-test string construction explicit.
- Advance package/revalidation current-version metadata to 0.11.2 while retaining prior 0.11.1 task/translation and operations results as historical evidence.

## 0.11.1-0.11 - 2026-09-17

- Integrate the Stage-2E selected Translate-Gemma configuration as two package-owned candidate Open WebUI roles with the exact explicit-direction v1 system prompt, direction-specific user wrappers, `max_tokens=2048`, and no forced thinking policy; keep the existing LFM translation role production/default pending one bounded final product-path requalification.
- Add one reviewed non-global Open WebUI Filter Function to apply only the tested DE→FR / FR→DE wrapper, reconcile it through supported Functions APIs, and extend desired-state status checks to detect function/preset drift without synchronizing away unrelated operator Functions.
- Fix translation numeric-value parsing so one-decimal locale equivalents such as `8.1` and `8,1` compare as the same value, while retaining Stage-2E's known protected-format and trailing-line caveats rather than weakening acceptance semantics.
- Harden task-model qualification around a one-round cheap screen, a dedicated warm-main tiny survival gate and a post-OOM appliance recovery check. Keep LFM2.5 1.2B Q6_K as the production task model; record Qwen3 4B as quality-promising but unsafe for the concurrent task role after both exact-source and bounded 4K staging caused global OOM/main-model loss.
- Bring German/French translation qualification in line with the current campaign: add `bc250-benchmark translation --think auto|true|false`, record richer reasoning/runtime provenance, require an empty main lane for generic foreground direct screens, and retain the eight-case canonical suite as a screening gate rather than promoting any challenger before harder-corpus/product-path work.
- Retain dated task/translation campaign evidence in `MODELS.md` and Git-only development records rather than modifying runtime Modelfiles for measurement notes. Update operator/development guidance, print evidence archive SHA-256 without creating `.sha256` sidecars, normalize archive ownership, and keep production model/prompt/topology defaults unchanged.
- Fix the new post-OOM task recovery gate so it reloads/warm-checks GPT-OSS by default and distinguishes historical experiment faults from new faults during recovery; redact only the harness's expected local HOME prefix before direct-translation privacy scanning so normal benchmark path output does not suppress valid evidence archives.

## 0.11.1-0.10 - 2026-09-14

- Make `bc250-compare-mtp` return nonzero when either backend fails completion integrity, including a missing terminal state, a pathological repeated reserved/unused-token run, or no usable completion content/reasoning.
- Align MTP reserved-token corruption detection with the generation benchmark so isolated reserved tokens do not count as a pathological run. Missing draft-acceptance counters remain valid inference but are explicitly insufficient for MTP qualification.
- Replace the MTP comparison source-string regression with a focused fake-backend behavior test covering valid completion, reasoning-only completion, absent acceptance telemetry, missing terminal markers, repeated reserved-token corruption and empty output.

## 0.11.1-0.9 - 2026-09-14

- Strengthen main-model generation evidence with backend-aware completion integrity: Ollama responses must reach their terminal state and obvious repeated reserved/unused-token corruption is treated as a runtime failure. Generation metadata now records the effective local Ollama service command/environment and KV cache type where available, plus current CU status and best-effort GPU-kernel journal evidence.
- Add optional `--deep-context` 4K/16K target runs and `--sustained-seconds` thermal/clock stability runs without forcing 32K or changing CU/governor policy. The existing compact `usecase` benchmark remains the tiny semantic sanity gate before expensive candidate qualification.
- Make direct llama.cpp/MTP evidence reproducible: the runner prints exact runtime version/build and launch flags, `UBATCH=384` remains an explicit opt-in gfx1013 stability control, and the comparison reports draft acceptance counts/rate with backend-specific completion integrity.
- Record the main-model qualification policy in Git-only development memory. Production remains GPT-OSS on Ollama 0.34.0 with existing KV, governor and CU defaults; no new main model is promoted.

## 0.11.1-0.8 - 2026-09-13

- Revalidate an existing stored Open WebUI pruning API key before allowing interactive maintenance setup to retain it; invalid stored values now prompt for a replacement rather than bypassing the same character policy applied to newly entered keys.
- Make optional read-only Raspberry Pi backup export independently ensure that Fedora `openssh-server`/`sshd.service` is available, sharing the same small installer helper with restricted Pi maintenance access so skipping the earlier SSH branch cannot abort export setup.
- Correct current-source validation/development references for the 0.8 RPM. Production topology, model defaults, firewall exposure, retention and power-policy defaults remain unchanged.

## 0.11.1-0.7 - 2026-09-13

- Fix `bc250-maintenance contract` after the installed-documentation hierarchy change by resolving the contract from `docs/MAINTENANCE-CONTRACT.md` under the package doc directory.
- Improve the interactive maintenance/Pi installer flow: clearly separate local BC-250 maintenance from optional Raspberry Pi access/export, use an explicit numbered power-action choice, show the detected WOL interface and address before accepting it, and explain that the setup is safe to rerun.
- Re-prompt locally for invalid yes/no answers, pruning limits, warm-up values, power time/action and network-interface input instead of terminating the entire maintenance setup after earlier sections have already been applied. An IP address entered where a Linux interface name is required now gets a targeted explanation.
- Keep production topology, model defaults, maintenance policy defaults, retention, firewall exposure and quality thresholds unchanged.

## 0.11.1-0.6 - 2026-09-13

- Strengthen the optional backup-export regression coverage by executing each backup producer through its directory-preparation path in a hermetic test and asserting the resulting `0750` installed-group mode plus the `0700` no-package-group fallback, instead of protecting the fix with exact source-code strings.
- Reduce documentation regression checks to durable package-facing invariants rather than accumulating prose assertions: public command names, runnable privileged/read-only examples, revalidation lifecycle, the known retired-vs-active Qwen distinction, source/installed relative links, and exact active-experiment catalog equality remain protected.
- Add concise Git-only review/release guidance so future implementation chats report what changed, what was deliberately deferred, what validation actually ran and any residual risk, and prefer behavior-level regression tests when practical.

## 0.11.1-0.5 - 2026-09-13

- Fix the optional backup-export permission regression: config/users backup producers now preserve the package-owned `0750 root:bc250-backup-export` directory contract when the reserved group exists, while retaining a private `0700` fallback for source-tree/direct execution without that package group. Published artifacts remain `0640` only after the export account is explicitly enabled; rollback backups remain private.
- Reconcile current-facing documentation with the package: core verification is shown before optional maintenance/Pi setup, the retired `exp-qwen38-4b-distill-empero-q6-k` task candidate is no longer described as active, Open WebUI backup wording reflects scheduled verified config/users backups, and the full `bc250-revalidate` lifecycle is documented.
- Preserve repository-relative documentation paths under `/usr/share/doc/bc250-llm-server/` so one link layout works in Git and on the appliance; add staged-installed-document link regression coverage and keep Git-only `development/` bookkeeping out of the binary RPM payload.
- Consolidate `docs/RPM-LAYOUT.md` into `docs/FILESTRUCTURE.md` and `docs/REPACKAGING.md` into `packaging/README.md`; reduce source-subtree quality/experiment READMEs to maintainer guidance while retaining detailed operator/model rationale in their canonical documents.
- Add a small development-memory convention with durable decision records and model-run templates, including explicit retest conditions, so rejected experiments are not repeated merely because current-facing docs are shortened.

## 0.11.1-0.4 - 2026-09-12

- Define maintenance contract version 1 for an external Raspberry Pi companion: office readiness is HTTP :80, Wake-on-LAN is the morning-start mechanism, and `sudo bc250-maintenance request-shutdown` is the stable remote-safe-power interface. The BC-250, not the Pi, remains responsible for deciding whether active SSH/UI/Ollama/maintenance work permits shutdown.
- Add `bc250-maintenance companion status|enable` to prepare a dedicated forced-command power-control account and ensure only the existing office HTTP service plus restricted SSH :22 are available; internal Open WebUI/Ollama ports remain outside the companion contract.
- Add optional `backup-export status|enable` using Fedora `/usr/bin/rrsync` (`rsync-rrsync`) with separate config/users key scopes. Reserve a dormant export group for stable directory permissions and publish new artifacts `0640` only after the export account is explicitly enabled; rollback backups and maintenance secrets remain private.
- Add the maintenance/Pi step to full interactive `bc250-install`, including explicit prompts for WOL/power policy, restricted Pi access and optional `rsync-rrsync`. Non-interactive and `--models-only` installs do not silently enable remote maintenance or backup export.
- Keep backup secondary to office availability/power savings: no Open WebUI API key is required by the Pi, no push-to-Pi credential is introduced, and no new application port is exposed.

## 0.11.1-0.3 - 2026-09-12

- Polish model cleanup without changing deletion semantics: explicitly named targets no longer dump the full category, interactive cleanup shows registration/runtime/source/state actions before confirmation, and `--keep-gguf` previews retained source/state data while `--list` remains discovery-only. Remove the duplicate all-model catalog print.
- Scope manual maintenance output to the current systemd invocation instead of a historical journal tail and remove an internal backup-users table-name line from normal output.
- Preflight the protected Open WebUI API key before manual upload pruning, report the active age/ceiling/dry-run policy without exposing credentials, and avoid expected systemd failure noise when the key is missing or still the placeholder.
- Refresh operator documentation and command examples for the current cleanup/maintenance behavior, including `sudo` where examples use root-owned token files or privileged appliance operations. No lifecycle semantics, retention policy, quality thresholds, service topology, or storage-dedupe behavior changes in this release.

## 0.11.1-0.2 - 2026-09-12

- Move the runtime baseline from Ollama 0.33.3 to 0.34.0 using the commit-pinned official installer (`d8ab4b4f0ca24b51d3a46b3bf4f462e58ce66b1f`) and the existing verified installer SHA-256. Ollama 0.34.0 keeps the same llama.cpp revision as 0.33.3, so this is a greenfield runtime refresh rather than evidence that existing AMD/Vulkan UMA risks are fixed; real BC-250 model-load and coexistence validation remains required.
- Add four packaged main-model experiments: Qwen3.6 35B-A3B UD-IQ3_S, Qwen3.8 27B ISTA GSQ-RCO IQ3_S, Qwen3.8 27B Unsloth UD-IQ3_S, and Gemma 4 26B-A4B i1-IQ3_S. Each Modelfile records the next lower quant to try if the larger candidate cannot load safely.
- Package `quality-checks/main/10-main-model-candidate-matrix.sh` for sequential GPT-OSS-versus-candidate comparison with normal-lane residency cleanup, resource/journal evidence, compare/edge profiles, and source-GGUF retention by default.
- Fix the model-state regression exposed by upgrade/drift evaluation: schema-3 state is now treated as current, harmless sidecar rewrites preserve the `dedupe` map, and re-registration output explains whether source, Modelfile, refresh, or registration state caused reconciliation. Add `--quiet` for scripted install/cleanup and describe inactive agent registrations as deferred rather than broken.
- Keep the field-tested 16 MiB XFS dedupe range but issue all ranges for one source/blob pair through one `xfs_io` process instead of one process per chunk. Storage status/dedupe now separate live manifest-referenced source/blob pairs from transient unreferenced source-hash blobs; the latter are left to Ollama startup pruning rather than being deduped. Source GGUF retention remains the default so re-registration can avoid redownloads.
- Carry forward the prior support-ops retirement/storage patch set (retired catalog cleanup, schema-3 identity, protected-root accounting, canonical dedupe labels, fast source checksum validation) and the two Ruff-oriented translation/catalog fixes.
- Keep the upstream Ollama installer ownership model unchanged: the helper still removes the upstream-generated unit and verifies the RPM-owned unit afterward. Upstream ROCm payload behavior is not changed in this release because it has not yet been qualified as safely suppressible.

## 0.11.1-0.1 - 2026-09-12

- Promote LFM2.5 1.2B Q6_K to the dedicated Open WebUI task lane after 15/18 direct quality, 15/18 live Open WebUI quality with package-owned task prompts, and 9/9 clean true-overlap trials beside warm GPT-OSS; retain Gemma 3 1B as an optional fallback/control.
- Make the package-owned title/tag/retrieval-query prompt templates explicit in Open WebUI desired state and make the direct task benchmark consume that same policy, closing the observed 15/18-direct versus 6/18-live prompt-contract gap.
- Retire the completed/exhausted compact task candidates and unsafe Qwen3.8 4B task candidate to the source-only graveyard with evidence notes; remove obsolete candidate wrappers and keep the generic future-candidate screen aligned to the package task default.
- Preserve task keep_alive=0, warm-main residency, evaluator thresholds and quality rc=3 semantics; no evaluator is weakened to hide the known French-title relevance miss.

## 0.11.0-1.15 - 2026-09-12

- Fix the Translate-Gemma Open WebUI screening showstopper by temporarily extending only an existing restricted main-provider allow-list, preserving unrestricted providers, honoring `prefix_id`, capturing HTTP failures, and restoring both preset and provider policy with effective-model verification. Full provider configuration remains root-only under `/run`; evidence contains redacted snapshots and is scanned for both the admin token and provider credentials.
- Accept the observed valid French formal-office wording `confirmer avoir reçu` while retaining all language, source-leakage, reference, date and numeric-preservation gates. Translation direct/OWUI screens now record stronger runtime/model provenance and machine-readable run manifests; a broader corpus remains required before promotion.
- Add a first-class package retirement catalog and `bc250-model cleanup-retired`, keeping source graveyard Modelfiles out of normal discovery while safely distinguishing retired package registrations from arbitrary unmanaged models.
- Correct storage accounting for protected roots, add canonical model/lane names to dedupe/prune output, record model identity in schema-3 sidecars, and skip only previously recorded unchanged dedupe pairs. Legacy/unrecorded pairs are reported without claiming physical reclaimability.
- Preserve current production defaults, warm-main/task/embedding residency policy, exclusive agent topology, 16 MiB XFS dedupe ranges, harness-4.0 semantics and quality thresholds.

## 0.11.0-1.14 - 2026-09-11

- Harden translation candidate evidence before more real-device comparison: direct screening now uses a 1024-token default, model-appropriate Hunyuan/Translate-Gemma prompt contracts, numeric-value preservation, and correct `rc=3` propagation; authenticated Open WebUI screening adds request/resource telemetry, selected stable-field preset-delta checks, restoration verification, and credential scanning.
- Make compact task candidate screens compare baseline and challenger on the same dedicated task Ollama runtime, record the effective title/tag/query budgets and `keep_alive=0` contract, preserve `rc=3`, reject unknown pre-existing temporary task registrations, and clean the task-lane candidate on exit.
- Harden support operations: automatic upload pruning preserves files with unknown timestamps or sizes, agent-mode transitions verify the promised exclusive service topology, and `bc250-model cleanup` accepts the same explicit `--host`/`--destination` overrides as installation.
- Move three clearly exhausted comparison definitions (Granite 4.2 8B, Ling 3.0 Tiny, and Defiant-Fable Qwen3.5 9B) into the source-only graveyard and synchronize the active experiment/catalog documentation. Production models, residency policy, harness-4.0 semantics, and quality thresholds are unchanged.

## 0.11.0-1.13 - 2026-09-10

- Add checksum-pinned experimental compact task candidates: LFM2.5 1.2B, MiniCPM5 2B, Qwen3 1.7B and Qwen3.8 2B Distill. The production task default remains Gemma 3 1B until a candidate proves both quality and safe coexistence with warm GPT-OSS.
- Add Hunyuan-MT 7B Q4_K_M and Translate-Gemma 4 Sub E4B Q4_K_XL as translation experiments. LFM2.5 8B-A1B remains production while model comparison continues.
- Install the Batch 1-3D evidence scripts and new standalone task/translation candidate screens under `/usr/share/bc250-llm-server/quality-checks/`. These are deliberately separate from harness-4.0 qualification.
- Add only minimal package coverage for the new quality assets; real model downloads, GPU/runtime quality and Open WebUI mutation checks remain operator-run on the BC-250.

## 0.11.0-1.12 - 2026-09-09

- Preserve the proven 20-minute main-model residency and keep Gemma 3 1B as the lightweight Open WebUI task default after Qwen3.8 4B overlap with GPT-OSS caused a real task-service OOM.
- Promote Ornith 1.5 9B for exclusive agent mode at temperature 0 with 3072-token Bash/Python budgets.
- Keep Jina v5 small as the warm embedding default and retain explicit German/French translation direction in the production LFM model.
- Preserve harness-4.0 architecture and quality return-code semantics while carrying forward the corrected RAG, translation, task, agent and dashboard evaluators.

## 0.11.0-1.11 - 2026-09-08

- Correct post-qualification evaluator false negatives for public-cloud RAG prohibition wording, redundant question identifiers, locale/order-safe currency invariants, formal French prohibition wording, and the DE-to-FR formal-office honorific/invariant-content fixture.
- Enforce language compliance for the German tag task case while retaining separate language and relevance failure reporting.
- Make completed revalidation dashboards use final-state infrastructure/worker wording, clear stale rows when a shorter final frame replaces a running frame, and preserve failed-run diagnostics.
- Report unavailable Ollama registration probes explicitly instead of the ambiguous `setup unknown` label (notably for the normally inactive agent lane).
- Keep the successful 0.11.0-1.10 and 0.11.0-1.11 real-device qualification bundles historical and unchanged; these evaluator/UX corrections apply only to new runs.

## 0.11.0-1.10 - 2026-09-07

- Fix harness-v4 `run_step` execution for declared internal Bash functions so GNU `timeout` runs them inside an exported child Bash rather than treating function names as nonexistent executables.
- Close the real Phase-3 `rc=127` path affecting production sanity, GPT-OSS sanity, Jina residency, and recent device-error checks while preserving the sanitized benchmark wrapper.
- Add deterministic regression coverage for both successful and nonzero internal-function return-code propagation through `run_step`.

## 0.11.0-1.9 - 2026-09-07

- Fix harness-v4 `run_step` so package-qualification commands are sanitized first and GNU `timeout` executes the real benchmark command rather than trying to execute the `qualification_benchmark` Bash function.
- Preserve the original failed phase/stage and failing-step console path across failure finalization; dashboard/status now report the useful failure location, error-context guidance is sudo-safe, and foreground failure output includes the console tail.
- Make executable-source validation Git-safe by requiring the executable bit rather than an exact source `0755` mode; the install manifest continues to enforce installed `0755`.

## 0.11.0-1.8 - 2026-09-07

- Finalize canonical benchmark evidence on SIGINT/harness-timeout interruption across category, generation, runtime and Open WebUI benchmark entry points.
- Require complete resource evidence on every successful Phase-3 measurement; missing context, residency, `MemAvailable`, temperature, or short-decode throughput now makes qualification evidence incomplete.
- Restore `openwebui-benchmark.py` source mode to `0755`, clean the current RAG memory-edge wording, and add focused deterministic regressions for interruption and telemetry completeness.

## 0.11.0-1.7 - 2026-09-07

- Preserve canonical benchmark evidence on initialized-run infrastructure failures across category, generation, runtime and Open WebUI benchmark entry points.
- Correct Phase-3 context qualification to enforce the minimum observed allocated context across successful measurements, and treat missing required thermal telemetry as qualification failure.
- Show run state and coverage in revalidation completion/status output, and make installer revalidation guidance match the authenticated harness-v4 interface.
- Document the conservative gross-edge policy rationale, use static-contract terminology for agent evaluation, and remove stale current-facing 0.10.0 wording.

## 0.11.0-1.6 - 2026-09-06

- Complete Round 2C-2 evidence output: canonical summaries now contain category aggregates, and generation reports warm answer latency, prefill, swap start/peak/end/delta, temperature p95/max and context/output diagnostics.
- Standardize benchmark metadata around package identity, kernel, benchmark version, runtime endpoints/versions, model names/digests, fixture hashes and effective options.
- Split the mixed workflow implementation into `runtime-benchmark.py` for Ollama/coexistence and `openwebui-benchmark.py` for Open WebUI RAG/tuning/restoration.
- Remove stale revalidation compatibility/reboot-era helpers and polish active-run/final wording without changing harness-v4 restoration ownership.
- Treat `bc250-benchmark rag-quality --think true|false` as the canonical thinking-policy comparison; routine revalidation continues to test only the packaged policy.

## 0.11.0-1.5 - 2026-09-06

- Revalidation now qualifies immutable package-owned model roles; operator/stale `prod-*` registrations cannot widen the run.
- Canonical benchmark records distinguish `measurement` from `qualification`; quality summaries derive only from qualification cases.
- Phase 3 now enforces conservative gross-regression gates for decode, residency, context, memory, temperature, device errors, and GPT-OSS/Jina coexistence.
- Full revalidation requires a protected Open WebUI token file validated before run-state creation; `--skip-owui` is an explicit incomplete-coverage mode.
- Final reports aggregate canonical benchmark failure causes, and preflight/final `bc250-verify` checks are hard health gates.
- Open WebUI mutation benchmarks verify configuration readback and temporary knowledge/file cleanup; cleanup/restoration failure is infrastructure failure.
- RAG answer-model residency loss is classified as an infrastructure/coexistence failure rather than a quality failure.

## 0.11.0-1.4 - 2026-09-06

- Complete the Round-2 benchmark-result migration for generation, OCR, RAG, coexistence and Open WebUI tuning workflows using one canonical per-run result directory.
- Remove legacy `bc250-benchmark` aliases and the implicit commandless generation mode; explicit canonical subcommands are now required.
- Remove the private revalidation tuning helper. `num-batch`, concurrency and Open WebUI tuning are explicit benchmark workflows, while harness v4 continues to qualify only packaged defaults.
- Make `results.jsonl`, `summary.json`, `summary.txt`, `meta.json` and copied fixtures the canonical evidence set; CSV remains a category export where useful.
- Improve BC-250 UMA generation summaries with resident size, minimum `MemAvailable`, swap start/peak/end/delta and diagnostic thermal/context warnings.

## 0.11.0-1.3 - 2026-09-06

- Advance `bc250-revalidate` to harness v4.0 and make routine revalidation qualification-only: six phases cover preflight, production roles, resource edge, exclusive agent mode, packaged Open WebUI RAG, and final restoration/reporting.
- Remove routine configuration-decision sweeps and hardware A/B controls from revalidation. `num_batch`, embedding-batch, chunk-min, `RAG_SYSTEM_CONTEXT`, thinking-policy, keepalive, kernel/governor, and experimental-model comparisons belong to explicit benchmark/diagnostic workflows.
- Route benchmark/helper execution through one explicit quality-vs-infrastructure status path: quality `rc=3` remains nonfatal, while other helper/benchmark failures propagate to the worker and restoration.
- Replace the stage-transition heartbeat with a TSV event stream, stage-start timestamp, worker state and last real event age; final status separately reports run state, infrastructure, quality and restoration.
- Qualify the complete live SPI/WGP routing-table health in preflight without requiring a hard-coded numeric CU total.

## 0.11.0-1.2 - 2026-09-06

- Finish the Round-1 agent static-contract correction without executing generated code: nested function/class bodies no longer satisfy Python requirements, `parse_ports` requires recognizable deduplication, and range-bound evidence must be associated with branches that raise `ValueError`.
- Tighten the Bash Modelfile-list contract so `exit 2` must belong to a recognized missing-argument branch and glob implementations must be safe when no `*.Modelfile` exists (`nullglob` or an explicit existence guard).
- Treat per-query embedding Top-3 status as an observational metric rather than a qualification check; the aggregate fixture policy remains the only Jina qualification gate.
- Add adversarial deterministic regressions for duplicate-preserving Python, dead nested AST evidence, unrelated range errors, detached Bash exits, and unsafe empty-directory globbing.

## 0.11.0-1.1 - 2026-09-06

- Fix the production-usecase common-record serialization crash and align reused output paths so CSV, JSONL and generated summaries always describe one invocation.
- Make schema-managed summary generation fail visibly on malformed canonical records instead of silently dropping them.
- Tighten agent static qualification without executing generated code: Python requirements are scoped to the requested function and include range-boundary evidence; the Bash Modelfile fixture checks argument guarding, direct-directory selection, basename extraction, sorting and filtering.
- Move embedding qualification from a hidden per-query Top-3 rule to explicit aggregate Jina policy thresholds in the fixture; experimental embedding comparisons remain measurement-only.
- Classify translation source-language leakage separately from target-language failure, strengthen graveyard-isolation regression coverage, and clarify the active-control-vs-retired-graveyard policy.
- Clarify that the common result envelope rollout is staged: embeddings/task/agent/translation/usecase are migrated first; OCR/RAG/generation keep their established record shapes until the next round.

## 0.11.0-1.0 - 2026-09-06

- Start the pre-1.0 benchmark/revalidation cleanup around the three-command boundary: `bc250-verify` checks current health, `bc250-benchmark` discovers candidates, and `bc250-revalidate` qualifies packaged defaults.
- Add a small common benchmark result envelope (`outcome`, `failure_kinds`, `diagnostics`, `checks`, `metrics`) and adjacent JSON/text summaries without removing the established CSV and JSONL interfaces.
- Fix demonstrated evaluator defects: task relevance now gates parsed task content, translation requires meaningful target-language output with consistent normalization, production use-case acceptance no longer rejects valid intermediate weekday reasoning, and agent results separate raw format, syntax and requirements.
- Canonicalize OCR markup for text-fidelity scoring while keeping table/reading-order structure separate; add embedding hard-case and target-margin diagnostics.
- Record swap start/peak/end plus peak delta so sequential BC-250 UMA runs do not misattribute previously allocated swap to later models.
- Remove disqualified comparison definitions from normal model discovery while retaining their Modelfiles in a source-only graveyard.

## 0.10.0-1.3 - 2026-09-06

- Make repeated installs quieter and more idempotent: reuse one transient Hugging Face authentication decision across normal and agent model groups, suppress the second full model catalog after selection, disable unsupported Xet advisories, avoid no-op Ollama re-enable/restart churn, and restart private Podman services only when configuration changed or the live path is unhealthy.
- Correct 40-CU status semantics: live SPI/WGP routing is the availability signal, while kernel/RADV numeric CU counters are labeled diagnostic; `bc250-40cu status` and `bc250-status` now surface the live routed-CU summary instead of implying that the kernel counter is the active total.
- Align status wording with the verifier for expected BC-250 cpufreq/cpuidle behavior and normal inactive agent mode, and make an unavailable `needs-restarting` helper an explicit unchecked state rather than a pseudo-result.
- Add compact `bc250-verify --summary` output for installer use and remove the duplicated memory/CU/parity report from routine installation; detailed `bc250-verify` and `llm-run-diagnose` remain explicit troubleshooting commands.
- Accept `--owui-token-file` as an alias for `--token-file` in `bc250-openwebui-setup` so credential-file naming is consistent across installer, verifier, revalidation and Open WebUI helpers.

## 0.10.0-1.2 - 2026-09-05

- Refine the guided installer UX: lazy Hugging Face authentication only when model bytes are actually needed, a defaultable protected Open WebUI administrator API-key-file choice without re-entering the detected path, clearer persistent-vs-live 40-CU wording, live-manager service detection, and a concise successful-completion command summary.
- Advance `bc250-revalidate` to v3.9 with a compact foreground dashboard showing elapsed time, numbered application phase, stage, heartbeat age and recent benchmark outcomes while the systemd worker remains authoritative; make `status` human-readable by default with `--raw` for scripts, distinguish the installed harness from the harness that produced the recorded run, and keep routine agent qualification pinned to the package-default Qwen model so catalog additions cannot silently widen or change the run.
- Make revalidation startup quieter by suppressing the transient systemd enable message and replacing duplicate filesystem tables with one storage-headroom line.
- Add `bc250-verify --owui-token-file FILE`, report model registration by normal lane, and classify absent standard CPU cpufreq interfaces as informational when the package SMU governor is healthy instead of producing two non-actionable warnings.
- Add `agentic-gemma4-12b-fable5-tau2-q4-k-m`, `exp-gpt-oss20b-unsloth-ud-q4-k-xl`, and `exp-qwen38-4b-empero-q6-k` as opt-in comparison Modelfiles. Experimental catalog growth remains non-blocking for routine package/revalidation runs and production roles are unchanged.

## 0.10.0-1.1 - 2026-09-05

- Recreate the Tika and Open WebUI Quadlets after installer firewall/Quadlet reconciliation and skip firewalld reloads when the HTTP policy is already current, preventing stale Podman DNS/host-gateway state after updates.
- Add `bc250-install --owui-token-file FILE`; Open WebUI setup now offers token-file choice 3, suggests an existing protected `/root/owui-test.key`, and reuses the transient authenticated token for final desired-state verification without persisting it.
- Split `bc250-verify` container-path diagnostics into private Tika DNS, Tika HTTP, `host.containers.internal` DNS and per-lane Ollama connectivity checks.
- Advance `bc250-revalidate` to v3.8 with an early Open WebUI private-network preflight before model benchmarks, clearer helper failure output, and a live foreground phase/stage indicator; `--detach` retains immediate-return behavior.
- Keep the static `llm-run-diagnose --no-load` report model-neutral instead of selecting an arbitrary installed experiment.
- Reduce update noise by avoiding redundant kernel-devel reconciliation when 40-CU is already prepared and suppressing the redundant full model catalog during baseline task/embedding reconciliation before the single optional selection.

## 0.10.0-1.0 - 2026-09-05

- Stabilize `bc250-revalidate` v3.7 so child benchmark/sampler failures cannot invoke global recovery, successful workers do not delete/reload their own active systemd unit, and bundles retain the harness journal plus shell error context.
- Use the package-facing `bc250-office-documents` Open WebUI workspace model for authenticated chunk/system-context experiments; record helper outcomes and skip tuning when package-owned OWUI state is drifted.
- Increase the direct `rag-quality` answer budget to 1024 tokens by default, classify retrieval/answer/citation/thinking-budget exhaustion separately, and add a diagnostic default-vs-`think=false` A/B without changing the production preset.
- Keep noninteractive generic generation benchmarks production-scoped unless experimental models are explicitly named or `BENCH_INCLUDE_EXPERIMENTS=1` is set.
- Keep experiment documentation validation one-way: documented experiment IDs must exist, but adding another structurally valid `exp-*` Modelfile no longer fails package validation merely because the prose inventory has not yet been expanded.
- Add the Qwen3.8 9B, Qwythos 9B and TIR Qwen3.5 9B non-thinking experimental definitions while leaving production defaults unchanged.
- Keep completed revalidation work state inspectable until `cleanup` or the next `start`; `status` now reports the bundle for the current run.
- Make authenticated OWUI helper errors fail as infrastructure only after their exit/outcome data are written, while quality status `3` remains nonfatal.
- Improve agent acceptance diagnostics and align the Bash fixture with its stated spaces-in-path requirement rather than an unstated arbitrary-newline requirement.

## 0.10.0-0.7.testing - 2026-09-04

- Preflight custom Ollama service overrides before invoking the pinned upstream installer; reject upstream-looking units with operator additions.
- Remove installer-history/package-baseline/network-before-state bookkeeping under the pre-1.0 greenfield contract.
- Add `ensure` semantics to memory and swap helpers and delegate those decisions from `bc250-install`.
- Move persisted Open WebUI providers/task/embedding/RAG settings into one package-owned `desired-state.json` consumed by the supported API helper.
- Simplify normal/agent mode switching around the four static package units and add `bc250-reset` as the preferred full-appliance reset command.
- Correct remaining command privilege/RAG benchmark wording and simplify XFS dedupe restoration so failures propagate without a blind exception catch.
- Refresh source pins without changing the release: Ollama 0.33.3, Apache Tika 4.0.0-full with the Open WebUI Tika-4 API contract, and the current CU live-manager revision; Open WebUI and the governor remain current.

## 0.10.0-0.6.testing - 2026-09-04

- Package all four Ollama lane units, including the main service; the pinned upstream installer supplies the binary but no longer owns service policy.
- Keep Open WebUI non-boot-enabled until the resumed installer has established normal topology and registered the baseline task/Jina models.
- Define normal mode as main + task + embedding and make unified model operations switch temporarily into agent mode when needed.
- Add a lightweight fresh-install lifecycle acceptance test for the primary reboot boundary and model-before-Open-WebUI activation order.

## 0.10.0-0.5.testing - 2026-09-03

- Correct `bc250-revalidate` so benchmark acceptance status `3` remains nonfatal while unexpected benchmark failures propagate to worker recovery; re-establish normal Ollama after the `num_batch` sweep.
- Report the full live CU routing dashboard and classify routed/problem cells without requiring a universal `40/40` count.
- Require successful service quiescing for XFS dedupe and surface restoration failures instead of ignoring them.
- Make `bc250-install` the single owner of Fedora update policy, expand its setup-plan summary, restore source-tree model-setup executability, and clarify the 4K embedding cap comments.

## 0.10.0-0.4.testing - 2026-09-03

Finish the installer/storage pass without widening the runtime architecture. The
repository-root `install` is now a small bootstrap: update Fedora, install the
selected RPM, then hand off to the RPM-owned `bc250-install`. RPM `%post` is
limited to package integration and the persistent Open WebUI signing secret;
service, firewall and SELinux provisioning happens only in the explicit guided
installer.

`bc250-install` shows the current setup plan, avoids no-op root-LV growth and
package/model work where practical, combines Fedora/kernel and TTM preparation
before one primary reboot, and asks for models once using global indexes, names,
ranges, `recommended`, `production` or `all`. A second reboot is requested only
when persistent 40-CU mode is already configured and the prepared replacement
AMDGPU module is not yet running.

Model registration now skips only when the validated source, rendered Modelfile
and correct Ollama-instance registration are all current. Large downloads report
filesystem headroom. New `bc250-storage` tooling reports GGUF/Ollama duplication,
performs explicitly confirmed XFS `FIDEDUPERANGE` sharing on verified pairs,
optionally prunes fully verified offline GGUF source copies, and removes 40-CU
cache trees only for kernels no longer installed. The real XFS experiment
recovered about 46 GiB while retaining both logical GGUF and Ollama paths, so
reflink dedupe is now a supported explicit operation rather than a feasibility
question.

Add `bc250-revalidate` as the packaged, opt-in whole-appliance revalidation
harness. It uses package-native state paths, keeps phase reports inside the final
bundle, recovers the main Ollama service between destructive long-prefill
candidates when needed, and removes transient worker/unit state after a final
tarball is safely written. This remains a pre-1.0 diagnostic tool rather than a
mandatory package validation gate.

## 0.10.0-0.3.testing - 2026-09-03

Tighten the runtime before the installer/storage pass. Bound both dedicated
embedding Modelfiles to the service's 4096-token context so an existing 32K
model definition no longer defeats the small embedding lane. Keep Jina as the
default pending the required same-board retrieval and GPT-OSS coexistence rerun.

Persist Open WebUI's signing secret in package state so container recreation does
not invalidate existing sessions/API credentials. Fix agent boot-state verification
to inspect `UnitFileState`, accepting `static` as the intended non-boot-enabled
state. The already-integrated explicit agent restoration-status handling remains
unchanged.

Make benchmark process status match benchmark meaning: task and agent acceptance
failures now return the existing quality-fail status `3`; translation comparison
normalizes harmless Unicode dash and locale-number formatting, and supports an
explicit source/target direction A/B without changing the production LFM role.

## 0.10.0-0.2.testing - 2026-09-02

Close the remaining installer review gap without changing the appliance runtime
architecture. The guided installer now records whether the **original** stdin was
interactive before `script(1)` creates its transcript pseudo-terminal, propagates
that state into the child process, and uses it for model, Hugging Face and Open
WebUI prompts. A pipe or `/dev/null` therefore stays non-interactive even when the
transcript child itself owns a PTY. Unattended selections continue to come from
the existing `BC250_*_SELECTION` variables; unset categories skip cleanly.

Retain the reviewed agent restoration diagnostics, conservative firewalld/SELinux
ownership handling, Open WebUI response-shape validation and Ruff cleanup from the
0.10.0 release review. The official Ollama install script remains fetched from the
immutable v0.33.2 release commit rather than the moving `ollama.com/install.sh`
entry point, and its expected SHA-256 is now pinned and verified before root
execution. The verified upstream script still downloads versioned Ollama binary
archives over HTTPS without repository-pinned per-asset checksums; document that
remaining boundary instead of overstating it as full end-to-end artifact
verification.

Fedora 44 now publishes kernel `7.1.12-200.fc44`. The 7.1.12 stable delta itself
is a networking/GSO fragment-reassembly panic fix. The intervening 7.1.11 stable
update also contains AMDGPU devcoredump fixes that allocate ring buffers per ring
and avoid a recursive reservation-lock/self-deadlock while formatting a dump after
a hung job. Those changes improve failure diagnostics/recovery paths but do not
provide evidence for changing the measured TTM-only memory profile, 1850-MHz
governor ceiling, Mesa policy or Ollama settings. The 40-CU workflow remains
dynamic and must be prepared against the exact running kernel after an update.

## 0.10.0-0.1.testing - 2026-09-01

Harden the release after validation review. Report failures while restoring
normal Ollama lanes after an agent setup or mode-switch error, preserve unknown
legacy firewalld/SELinux ownership during purge, and let non-TTY model-only runs
use selection variables or skip cleanly. Validate Open WebUI response shapes,
pin its root-executed Ollama installer helper to the signed v0.33.2 release
commit, and clear the release's Ruff findings.

Make the runtime separation explicit around the BC-250's shared-memory limits.
Normal appliance mode uses main Ollama on 11434, task Ollama on 11435 and a
dedicated embedding Ollama on 11437 with a 10-minute keepalive. Coding/agent
work on 11436 is intentionally exclusive: entering agent mode stops the normal
lanes, and leaving it restores them. This avoids treating four independent
Ollama processes as if the 16-GB UMA pool could safely host four large models.
GPT-OSS 20B remains the expected memory-edge production case and should be
re-benchmarked with the dedicated embedding lane after deployment.

Upgrade the digest-pinned Open WebUI baseline to v0.11.3. Add
`bc250-openwebui-setup init|apply|status`, which uses supported Open WebUI admin
APIs to persist the package-owned main/task provider configuration, task model,
dedicated embedding endpoint, reviewed RAG baseline and additive model presets.
Fresh interactive installs can create or sign in the administrator and apply the
baseline without storing credentials. Non-interactive installs never block; an
operator can provide `OWUI_API_KEY` temporarily or run setup later. Package model
imports are additive so unrelated operator models, users, prompts and knowledge
remain operator-owned.

Enable the local/offline Open WebUI application baseline while retaining
firewalld/nginx as the actual security boundary. Verification understands normal
versus exclusive-agent mode, checks the embedding model on 11437 and can perform
an authenticated desired-state comparison only when `OWUI_API_KEY` is supplied.
The package deliberately leaves `RAG_SYSTEM_CONTEXT=false` for a later real-corpus
A/B test. Fedora Mesa 26.2+, the external GFX1013 compute-queue stack, ROCm,
2000-MHz operation and model pruning stay documented as future evaluation items
rather than being mixed into this release. No pre-v1 Open WebUI database backup
automation is added.

## 0.9.7-0.11.testing - 2026-08-31

Use the 2026-08-31 reboot-by-reboot Fedora 44 / kernel 7.1.10 revalidation to
simplify the fresh-machine memory profile to `ttm.pages_limit=4194304` and
`ttm.page_pool_size=4194304`. Removing the deprecated explicit `amdgpu.gttsize`
and the full `amdgpu.ppfeaturemask` override did not reduce measured model
throughput, stability or usable GTT on the tested 40-CU board. The installer now
converges older four-argument profiles to this TTM-only baseline; status, verify,
diagnostics and removal keep enough legacy awareness to migrate or clean older
installs safely. Ollama version verification is API-first so a root/systemd
environment without `$HOME` no longer produces a false CLI panic.

Keep the normal governor policy at 350-1850 MHz with busy-flag demand tracking.
The same revalidation found fixed 1750 MHz roughly five percent slower on the
prefill samples, while fixed 1850 stayed close to busy-flag performance. Upstream
`cyan-skillfish-performance-mode --on` selected 2000 MHz despite the configured
1850-MHz normal maximum; the package therefore documents that mode as an explicit
operator override, recommends `--fixed-frequency 1850` for normal fixed-max
comparisons, and verification reports an active clock above the configured range.

Add opt-in, fixture-driven benchmark lanes for DE<->FR office translation and a
small embedding->retrieval->Gemma-E4B grounded-answer acceptance chain. Extend OCR
scoring with recoverable row/field structure and two deterministic harder scans,
report task-model language requirements separately from structural compatibility,
and add an optional cold/warm repeated-prefix generation pair for Ollama 0.33.x
cache measurement. These model/hardware benchmarks are not part of `make validate`.
Open WebUI keeps conservative `RAG_SYSTEM_CONTEXT=false`,
`CHUNK_MIN_SIZE_TARGET=0`, `RAG_EMBEDDING_BATCH_SIZE=1` and asynchronous embedding
disabled until real appliance measurements justify changing them.

Rename the top-level operator guide to `MODELS.md` and record current benchmark
conclusions there, including comparison candidates whose promotion case is now
exhausted without deleting their Modelfiles. Fix the stale OCR-count prose, update
installer/command/RAG/governor/memory documentation, retain the reviewed 40-CU
fork pending a provenance-delta audit, and document a real sustained thermal-soak
procedure separately from the short regression thermal wave.

## 0.9.7-0.10.testing - 2026-08-31

Upgrade the digest-pinned Open WebUI image to v0.11.2, including its reasoning
streaming/tool-state/security fixes. Declare the main/task/agent Ollama backends,
show only production chat models on the enabled main connection, disable direct
browser connections/frontmatter pip installs, and enforce bounded office upload
size/count/extensions. Ollama services created or normalized by the install/setup
helpers set `OLLAMA_NO_CLOUD=1`; older optional task/agent services are left untouched
until their setup helper is rerun.

Make the BC-250 fresh-machine profile explicitly set `amdgpu.gttsize=14750`,
`ttm.pages_limit=4194304`, `ttm.page_pool_size=4194304`, and
`amdgpu.ppfeaturemask=0xffffffff`. Verification now flags `amd_iommu=on`, lingering
`nomodeset`, and community-documented bad kernel ranges. The 16-GiB TTM setting is
kept because it is the project-tested profile, while external BC-250 guidance is
documented alongside it.

Add `bc250-model cleanup --keep-gguf` so Ollama registration/unreferenced blob data
can be removed while the local GGUF/state is retained for reuse. Remove
the redundant production/experiment/embedding `bc250-fetch-*` aliases (MTP keeps
its distinct fetch workflow), retire the `apply-safe` memory alias, centralize
runtime pins in `config/runtime.env`, and stop testing an arbitrary total model
count. The operator-selected Modelfile catalog itself remains unchanged.

Post-audit corrections make the production roles executable rather than merely
documented: restore LFM2.5 as a dedicated implicit DE↔FR translator; add
`bc250-maintenance model-baseline` to store request-level `think=false` for the
production Qwen3.5 base model in Open WebUI without replacing Ollama's native
renderer/parser; and explicitly disable follow-up, autocomplete, web-search-query
and retrieval-query task generation while keeping titles/tags enabled. Paginate
Open WebUI knowledge lookup across all search pages, add a five-case production
role acceptance lane plus a main-instance RAG model-switch latency lane, and fix
the 128-MiB application / 256-MiB nginx upload documentation and stale experiment
catalog prose.

Final installer/model-manager hardening makes the guided `install` script
self-contained when copied beside the RPM, skips the RPM transaction when the
exact package NEVRA is already installed, and lets the RPM post script detect the
official `/usr/local/bin/ollama`. Model administration now exposes only canonical
categories plus `all`; `sudo bc250-model cleanup all --keep-gguf` applies the
retained-source cleanup across every catalog, while `sudo bc250-model list`
reports protected retained GGUFs accurately. Static `--no-load` diagnostics no
longer warn about the deliberately absent resident model, and unpinned Mesa
version differences are reported as reference information rather than package
configuration warnings.

Use the final 2026-08-31 benchmark rerun to tighten interpretation without
changing deployed defaults: GLM-OCR remains the office OCR fidelity leader; the
harder embedding fixture leaves Jina/Qwen tied at 11/13 Recall@1 with the same
two near-duplicate misses; LFM2.5 2.6B is retained as a task challenger after
returning empty tag/query output; and the agent validator now checks small
static semantic requirements instead of calling merely compilable code correct.
Clarify that remote OCR sources remain Ollama-managed main+projector bundles in
0.33.2 rather than misleadingly placing only the main GGUF in the package source
tree.

## 0.9.7-0.9.testing - 2026-08-31

Make **Ollama 0.33.2** the package-standard runtime while keeping the BC-250 on
the same explicit Vulkan/one-model service architecture. The Linux-relevant
0.33.x change is improved cancelled/resumed prefill-cache correctness in 0.33.0;
0.33.1/0.33.2 are mostly MLX/desktop/proxy follow-ups for this appliance. Preserve
top-level `think`, request-time `system`, embedding and unload API behavior.

Make generation prefill and context-capacity points unload the runner first so
the stronger 0.33.x shared-prefix cache cannot distort raw prompt-ingestion
comparisons; bump generation benchmark metadata to 7.4. Keep production sampling
and reasoning policies unchanged. Refresh install/verify/diagnostic text, add a
documented 0.32.15 rollback path and optional Vulkan `cap_perfmon` guidance.

Retain all 28 operator-selected Modelfiles. Update Granite 4.2 experiment comments
to keep their explicit 32K context bound because upstream 0.33.x reports document
128K auto/full-context OOM risk on <=16 GB shared-memory systems; refresh Ling and
Jina runtime notes without changing their model parameters.

## 0.9.7-0.8.testing - 2026-08-31

Use the first full 0.9.7-0.7 production/category run to tighten benchmark
interpretation rather than changing production model profiles. Keep LFM2.5 on
the reasoning-capable latency budget even during explicit `think=false` tests,
reduce natural-stop warning noise, and bump generation metadata to 7.3.

Match Open WebUI 0.11.1 task JSON extraction while retaining a separate strict
raw-JSON signal and an informational language hint. Give agent fixtures enough
shared budget for native reasoning, reject empty final code, and capture thinking,
answer presence, `eval_count` and `done_reason`. Make the embedding fixture harder
with multilingual near-duplicate/conflicting office facts.

Retain the operator's broader experimental comparison pool for the next full
rerun and add compact Modelfiles for Qwen3.8 4B Distill Q6_K, Granite 4.2 3B/8B,
Ling 3.0 Tiny, LFM2.5 2.6B Q6_K as a task challenger, and Qwen2.5-Coder 7B
Q5_K_M (single-file Unsloth GGUF) as a coding baseline. GLM-OCR and OvisOCR2
remain the packaged OCR comparison pair.

## 0.9.7-0.7.testing - 2026-08-30

Correct generation-latency interpretation for reasoning-capable models after the
first full JSONL review. Keep the existing 96/64-token latency cap for explicit
non-thinking profiles, but use 512/384 for policies where reasoning can consume
the shared Ollama `num_predict` budget. Preserve `NUM_PREDICT_LATENCY` as a global
override and add an optional `NUM_PREDICT_LATENCY_THINKING` split override.

Remove the semantic `[reqid ...]` cache-busting text in favor of harmless leading
blank-line prompt variants. Record whether a streamed final answer actually
started plus answer/thinking character counts, warn when a latency request reaches
`done_reason=length` without final content, and persist context-truncation warnings
and near-limit notes in JSONL. Clarify that streamed `/api/chat` records are the
preferred qualitative source for families whose raw `/api/generate` output may
contain native reasoning markers. Generation benchmark metadata is now 7.2.

## 0.9.7-0.6.testing - 2026-08-30

Upgrade the digest-pinned Open WebUI baseline from v0.11.0 to v0.11.1 for its
security/access-control, RAG/knowledge, streaming and native Ollama reasoning-history
fixes while retaining the existing three-Ollama/Tika architecture. Keep Tika on
major version 3 and explicitly leave knowledge-file retention disabled.

Expose the new `TASK_MODEL_PARAMS` control at `{}` rather than introducing an
unmeasured task-sampling profile. Refresh the task benchmark compatibility labels,
RAG/upgrade documentation and smoke-test guidance without changing the compact task
prompts or enabling ORJSON/new agentic Open WebUI features.

## 0.9.7-0.5.testing - 2026-08-30

Harden manager-owned GGUF reuse with schema-2 state metadata: unchanged size,
mtime and ctime use the fast path; changed/legacy state is SHA-256 verified before
reuse. Model cleanup now retains local source files when an Ollama registration
cannot be removed.

Require confirmed model unload before measurements labelled cold, normalize
scheme-less Ollama hosts, and let agent benchmarks inherit deployed sampling by
default (`AGENT_TEMPERATURE` remains an explicit deterministic override).

Make RAG front matter a strict documented YAML subset, require `source_file` to
remain inside its collection's `sources/` directory, and reject active/source
symlink escapes. Protect reusable RPM source archives and the generated Cargo
vendor archive with local SHA-256 sidecars; `sources-check` now verifies them.

Remove the dead sensor logger and obsolete `install-cu-manager` /
`pull-embedding-model` compatibility commands. Rename the narrow speed-only
experiment helper to `bc250-compare-mtp`. CI now runs on pushes and pull requests
and adds Fedora Ruff/ShellCheck before the RPM build. Follow-up hardening catches
malformed Open WebUI sync response types cleanly, rejects tab-indented RAG metadata,
keeps install-manifest sources inside the source tree, and excludes Ruff/Python caches
from handoff/source archives.

## 0.9.7-0.4.testing - 2026-08-30

Fix the reviewed Jina embedding source to the upstream Q4_K_M GGUF carrying
`pooling_type` metadata, paginate the complete Open WebUI upload inventory before
pruning, and make the agent benchmark respect the isolated service residency
policy with guaranteed immediate unload.

Bind benchmark thermal/GPU/VRAM/GTT sampling to one selected AMD DRM device,
use its edge/on-die temperature for the 80/83/85 C thresholds, and bump generation
benchmark metadata to 7.1 for the changed telemetry semantics. Add embedding
dimension validation and exception-safe per-model unload cleanup.

Make OCR quality scoring penalize hallucinated output with token precision/F1 and
normalized character similarity while retaining exact required-field/order checks.
Align compact task fixtures with Open WebUI 0.11.0 message-window/tag/query
behavior, remove the legacy experiment helper's global `think:false`, and set a
fresh-install Open WebUI privacy baseline for sharing, code execution/interpreter
and memories. Clarify that `BENCH_MODE=production` remains a generic
production-configuration comparison; role-specific use-case benchmarking stays
deferred.

## 0.9.7-0.3.testing - 2026-08-30

Add a compact `bc250-benchmark agent` lane for the isolated port-11436 service.
The deterministic fixtures validate Bash/Python syntax and required structured
output without executing model-generated code. This keeps coding correctness
visible without adding a separate benchmark framework or dependency.

Harden embedding/OCR telemetry cleanup so sampler threads are stopped on request
errors. OCR now also reports required-field reading-order score. Task telemetry
and lighter category metadata remain intentionally unchanged.

Refresh benchmark, model and installation documentation, correct the source-tree
benchmark link, add `MODEL.md`, and document the pre-1.0 green-field installer
policy and intentionally flexible model revisions.

## 0.9.7-0.2.testing - 2026-08-30

Refactor `bc250-benchmark` into a thin dispatcher with stdlib-only Python suites
for generation, embeddings, OCR and the isolated Open WebUI task model. Generation
now separates a neutral cross-model mode from production Modelfile behavior, uses
model-family `think` policies compatible with Ollama 0.32.15, records response
JSONL and model digests, and treats short `done_reason=stop` separately from a
normal `length` limit.

Add request-time BC-250 telemetry for peak/p95 temperature, time at 80/83/85 C,
GPU busy/clock range, AMDGPU VRAM/GTT counters, minimum `MemAvailable`, maximum
swap use and Ollama allocation. `RUN_THERMAL=1` adds sustained decode windows.
Resource values are documented as overlapping UMA signals rather than independent
pools.

Add multilingual office fixtures and quality metrics for Jina/Qwen embeddings,
GLM/dots/Ovis/Chandra OCR and Open WebUI 0.11-style title/tag/retrieval-query
tasks. OCR prompts are model-specific and preserve source language.

Correct Qwen3.6 FableVibes to upstream `1.0 / 0.95 / 20` sampling, replace the
production Qwen3.5 stale experimental SYSTEM with the multilingual office prompt,
and add a source-grounded Open WebUI RAG template that reports insufficient
document evidence instead of silently falling back to model knowledge.

## 0.9.6-0.7.testing - 2026-08-27

Make Ollama **0.32.15** the package-standard runtime for BC-250 smoke tests; the
official installer helper now requests that version unless an operator deliberately
sets `OLLAMA_VERSION`. Verification and diagnostics warn, rather than fail, when a
different Ollama runtime is being compared.

Overhaul `bc250-benchmark` around useful BC-250/office measurements instead of a
single generation tok/s figure. The default `moderate` profile now separates cold
model-switch latency, warm latency, loaded decode throughput, document-prefill
throughput, context-capacity/truncation behavior, loaded Ollama allocation and host
memory/swap headroom. `conservative` is a shorter lower-context pass. Optional
embedding benchmarking uses `/api/embed` with a multilingual office batch; OCR
remains a real-page quality test through `bc250-ocr`. Dedicated task/agent stores
can be measured by pointing `OLLAMA_URL` at ports 11435/11436.

Make the fresh-install RAG baseline **moderate** at 1500-token chunks, 200 overlap
and Top K 8. Keep 1000/100/5 as the documented conservative alternative. Retrieval
query generation is disabled for the baseline so embedding/chunking quality is
measured before task-model query rewriting is introduced. Documentation now
distinguishes reindexing from source re-upload/re-sync.

`modelctl.py` removes redundant temporary `hf.co/...` OCR registrations after a
friendly packaged alias is created, while retaining safe status handling if cleanup
cannot occur. `bc250-rag-import --prune` can also clear the final stale remote file
when a generated Originals/Français lane has become locally empty.

## 0.9.6-0.6.testing - 2026-08-26

Add `bc250-rag-import` for the operator-owned `/srv/bc250-documents` tree. It
validates active Markdown front matter and source-PDF SHA-256 provenance, then
incrementally syncs each collection into separate Originals and Français Open
WebUI knowledge bases while keeping public/confidential boundaries distinct.
German originals remain authoritative; French translations are intended for
French queries. Remote files removed locally are retained unless `--prune` is
explicitly requested.

The package now creates `/srv/bc250-documents` as `root:root` mode `0750` and
ships a metadata-only Markdown template. No real office documents or API keys
are packaged.

## 0.9.6-0.5.testing - 2026-08-25

Add a privacy-oriented Open WebUI/Tika RAG baseline for German/French/English
office documents without adding another retrieval service or ingesting example
business data. Fresh installs now start with deterministic 1000/100 token
chunking, Top K 5, Markdown-header splitting, vector-only search, sequential
Ollama embeddings and Jina `Query:` / `Document:` prefixes.

`bc250-verify` reports the Open WebUI embedding/extraction defaults and checks
that the configured embedding model is registered with main Ollama without
running an embedding request. The installer points operators to the new RAG
guide after an embedding selection. Documentation covers Open WebUI v0.11.0's
Native-mode knowledge behavior, DE/FR cross-language evaluation, OCR-first
scans, reindexing, confidential data paths and complete stopped-instance
backups. A blank pilot evaluation TSV is packaged; no real documents are.

## 0.9.6-0.4.testing - 2026-08-25

Correct `bc250-ocr install/show` alias validation so an unknown OCR model exits
with status 2 before invoking the model manager or Ollama. Rename the GLM OCR
experiment to `exp-glm-ocr-ggml-q8-0` so its testing name reflects the actual
`ggml-org` source. Existing registrations under the old experimental name are
left untouched and may appear as unmanaged until the operator removes them.

MTP now explicitly adds `--no-cache-idle-slots` when supported alongside
`--cache-ram 0`. CPU power-state diagnostics ignore an unexpanded sysfs CPU
glob on systems where that interface is absent. Multi-command documentation
uses `bc250-check-temp --once` so the default continuous watcher does not block
following commands. Chandra keeps the currently published dotted upstream GGUF
filename `chandra-ocr-2.Q4_K_M.gguf`.

## 0.9.6-0.3.testing - 2026-08-25

Add four compact experimental office OCR definitions (GLM-OCR, dots.ocr,
OvisOCR2 and Chandra OCR 2) plus `bc250-ocr`, a thin list/install/show/test
wrapper over the shared model manager and main Ollama instance. GLM uses a 16K
context; Chandra remains a Q4_K_M compatibility probe pending real BC-250 image
testing.

Status and verification now report CPU topology, cpufreq driver/governor and
missing cpuidle states without adding CPU-unlock behavior. MTP disables the
llama.cpp RAM prompt cache when that option is available. Benchmarks warn when
`prompt_eval_count` stops growing and label SMU power as uncalibrated. Temperature
monitoring is continuous by default, while legacy diagnostics now match governor
v0.4.12 and the 1850 MHz package default.

## 0.9.6-0.2.testing - 2026-08-25

Correct model reuse so cached GGUF bytes are accepted only when repository,
revision and filename still match their recorded provenance. Modelfile-only
SYSTEM/PARAMETER edits continue to reuse the same bytes, while a changed source
identity triggers a download. Ornith Q5_K_M is pinned to the upstream commit
matching its packaged exact checksum.

Clean Fedora installation can now start its transcript with `tee` before the RPM
provides `util-linux-script`; `/usr/bin/script` is required only when a selected
model download needs visible progress. Guided MTP selection explicitly lists
and opts into its disabled download-only entries.

`bc250-status` again warns when root free space falls below `MIN_FREE_GB`. Model
listing reports known registrations on the wrong Ollama instance, firewall
verification checks every active zone plus accepting rich rules, and cache
cleanup documentation states that journal vacuuming is system-wide.

## 0.9.6-0.1.testing - 2026-08-24

This streamlining update expands the guided model stage to production, task,
agentic, embedding, experiments and MTP through one shared installer path. The
installer checks Fedora's `script` prerequisite before changing the system and
ends with the short `sudo bc250-40cu` next step while leaving CU activation
explicit and board-specific.

Model replacement now reuses an already validated GGUF when only source
metadata changes and rebuilds the Ollama registration; `--refresh` remains the
explicit way to fetch new bytes. Model discovery, validation and Ollama host
selection share fewer code paths without renaming or removing packaged models.

`bc250-status` now combines per-instance model storage, Hugging Face cache,
Podman, journal, memory pressure, zram, disk swap and swappiness visibility.
`bc250-maintenance clean-cache` is an explicitly confirmed rebuildable-cache
cleanup that retains GGUFs, Ollama models and Open WebUI data. Verification
checks the internal Ollama listener shape/firewall policy, CU status reports
stale kernel preparation, and deterministic validation cross-checks upstream
pins against the RPM spec.

## 0.9.5-0.3.testing - 2026-08-24

The optional maintenance stack now has one `bc250-maintenance` command for a
fast backup-only baseline, guided office scheduling, storage/backup status,
manual runs and clean schedule disabling. Local backups persist across missed
timer events and are serialized with idle I/O priority.

Upload pruning retains its safe dry-run default, treats zero as “disable this
rule” instead of “delete everything,” and preserves files whose age or size is
not trustworthy. Warm-up is still opt-in, now follows the current standard
office model and keeps it resident for only 15 minutes by default.

The former suspend-only helper is now an explicit `poweroff` or `suspend`
action. It covers HTTP as well as HTTPS/SSH/Ollama sessions, no longer fails
merely because Wake-on-LAN was not configured, and can require verified WOL
before acting. Documentation distinguishes same-disk recovery points from an
encrypted complete off-machine backup.

## 0.9.5-0.2.testing - 2026-08-24

The guided model stage is divided into four complete phases: production, task,
agentic and embedding. Each phase now lists, prompts and installs before the
next begins, while Hugging Face authentication is prepared only once. The
installer also distinguishes a same-NEVRA reinstall from a different-version
RPM transaction, verifies that the selected RPM is the one installed, avoids
repeating the 40-CU helper's activation message, and runs both verification
reports before returning a failure.

## 0.9.5-0.1.testing - 2026-08-24

Embedding models now use the same strict Modelfile discovery, Hugging Face
download, checksum and Ollama registration path as the chat categories. The
guided installer presents explicit selections for production, task, agentic
and embedding models; it no longer silently installs every discovered model in
a tooling category. Existing compatibility commands remain available.

The current operator-supplied model folder is retained and normalized to the
repository's strict metadata and storage rules. The Jina v5 small retrieval
GGUF is pinned to its verified upstream revision and corrected SHA-256. Current
recommended roles now point to Gemma 4 E2B/E4B, LFM 2.5, GPT-OSS 20B, Jina v5,
Gemma 3 1B and Ornith 1.5 while all other Modelfiles remain selectable for
testing.

## 0.9.4-testing - 2026-08-24

`bc250-verify` now reports dedicated Vulkan compute queue families and detects
the optional external GFX1013 kernel/Mesa patch stack without packaging it. A
custom `/opt/bc250-gfx1013` Mesa ICD selected without the project's patched
boot marker and matching kernel-specific `updates/amdgpu.ko` is a failure. The
documentation keeps this experimental module workflow separate from the
package's existing 40-CU replacement helper and requires a rebuild after every
kernel update.

The verifier now prints the exact Ollama version and scans recent Ollama and
kernel journal entries for `ErrorDeviceLost`, command-submission memory errors
and AMDGPU compute-ring timeouts. Ollama Vulkan updates are documented as
reviewed smoke-test candidates rather than automatic recommended baselines; a
smaller per-model `num_batch` is documented only as a diagnostic for the
reported long-prompt timeout case.

The Fedora kernel, governor and existing 40-CU upstream inputs remain unpinned
from runtime kernel versions and otherwise unchanged.

## 0.9.3-testing - 2026-08-23

This integration update pins Open WebUI v0.11.0 by its OCI index digest while
retaining the existing Ollama, private Tika, persistent-data, loopback and
privacy settings. Clean installations initialize the current schema directly.
Because v0.11.0 includes database schema changes, existing installations must
take a complete offline snapshot of `/var/lib/open-webui` before upgrading.

The Fedora kernel workflow remains tied to the kernel actually running, not to
a release number. Installation and 40-CU preparation use `uname -r` and the
matching kernel-devel tree; verification reports the AMDGPU module path and
vermagic and warns when the module must be rebuilt after a kernel update. The
governor remains pinned to v0.4.12 with `fix-freq = false`,
`method = "busy-flag"` and the fresh-install 1850 MHz maximum.

The shell validation entry point no longer depends on `/dev/fd`, allowing the
same checks to run in restricted build environments without changing the test
scope.

## 0.9.2-testing - 2026-08-21

This focused hardware-maintenance update pins Cyan Skillfish governor v0.4.12
at commit `be9537fc36f24b17570088cafa8c79365f80fee8`. Fresh installations keep
the existing conservative usage policy, now expressed as `fix-freq = false`
and `method = "busy-flag"`. Operators should enable `fix-freq` only for the
eight-core GPU-frequency reporting problem; the optional `kernel` usage method
still requires a separately patched compatible kernel.

`bc250-verify` now reports the running kernel, matching kernel-devel/build tree,
AMDGPU module path and vermagic, installed governor version and effective
`fix-freq`/usage-method settings. A kernel/module mismatch produces an explicit
warning to rebuild and reapply the 40-CU module after a Fedora kernel update.
No Fedora kernel release is hard-coded, and the existing Vulkan-oriented Ollama
configuration remains unchanged.

## 0.9.1-testing - 2026-07-23

This operational update adds `bc250-status`, a concise read-only overview of
the kernel, live CU report, governor, all three Ollama instances, web services,
memory, swap, storage and sensors. The existing verifier remains the detailed
pass/fail tool.

The swap profile now reports `vm.swappiness` and accepts an optional
`SWAPPINESS=0..200` override. It records the previous runtime value so profile
removal and full purge can restore it. If the variable is unset, existing
system policy is left alone. Sensor checks now include fan readings and
available PWM controls without installing an experimental fan-control stack.

Fresh installations use a 350–1850 MHz governor range. The 2000 MHz curve point
remains available for deliberate operator overrides, and `%config(noreplace)`
continues to preserve an existing governor configuration during upgrades.

## 0.9.0-testing - 2026-07-22

This update removes duplicated Ollama catalogs and makes each strict
`.Modelfile` the complete discoverable model definition. Packaged templates are
read from `/usr/share`; operator additions and same-name overrides are read
from `/etc/bc250-llm-server/models.d`. Production and experiment downloads
still require an explicit selection, while task and agentic setup keep their
dedicated Ollama instances on ports 11435 and 11436.

MTP retains its TOML because its llama.cpp context and draft-token fields do
not belong in an Ollama Modelfile. Revisions remain flexible and SHA-256
metadata is optional; downloaded files are still hashed and recorded locally.
The build now places source and binary RPMs together in `dist/`, declares the
Fedora `util-linux-script` dependency needed for visible Hugging Face progress,
and includes an installed-files overview.

## 0.8.1-testing - 2026-07-22

This maintenance release adds a bounded, explicit full-purge path, retains
live model-download progress and integrates default-off 40-CU preparation.

### 40-CU preparation

- The guided installer installs development files for the exact running kernel
  and prepares the replacement AMDGPU module without enabling additional CUs.
- Kernel source is cached, repeated builds are skipped, and the module embedded
  in the rebuilt initramfs is inspected before preparation succeeds.
- `status` now distinguishes the on-disk module, initramfs copy and actually
  loaded driver instead of reporting an on-disk patch as active.
- Secure Boot/signature enforcement is detected before an unsigned replacement
  is installed. Activation remains one explicit command and reboot.
- Corrected module verification so `pipefail` cannot misclassify a valid built
  module, and activation now skips the redundant preparation pass when the
  installed and initramfs copies are already verified.
- Added `install --models-only` to resume optional production, task, agentic and
  embedding setup after a reboot or interrupted system-setup run.

### Uninstall

- Added `sudo bc250-uninstall`, guarded by a destructive confirmation phrase.
- The purge removes package-owned configuration, all appliance model/UI/cache/
  backup data, isolated Ollama instances, official Ollama installed by this
  setup, containers, network, profiles and generated services.
- It removes CU live-manager persistence and restores verified stock AMDGPU
  module backups for every affected installed kernel before rebuilding module
  metadata and initramfs.
- The guided installer records packages that were absent before its own package
  transactions. Purge removes only that recorded set; it never guesses on an
  upgraded installation without a record.
- Pre-install firewalld HTTP access and the SELinux network boolean are
  recorded and restored instead of being silently reset.
- Filesystem growth and ordinary Fedora upgrades remain irreversible.

## 0.8.0-testing - 2026-07-22

This is the first cleanup step toward 1.0. It keeps the appliance features and
current model set while reducing the two most costly maintenance areas.

### Build

- The source manifest now records pinned commits, URLs and archive names only.
  Per-archive SHA-256 and required-member bookkeeping were removed.
- `make sources` reuses non-empty cached inputs and fetches only missing ones.
- `make clean` preserves the source cache. `make sources-check`,
  `make clean-sources` and `make distclean` make cache handling explicit.
- Release RPM checksums are still generated in `dist/SHA256SUMS`.
- The guided installer excludes Fedora's older Ollama package, verifies safe
  removal of an existing copy, and no longer sends `latest` as a version query
  to the official Ollama installer.
- The RPM now carries a sysusers declaration and provides its own `ollama`
  account capabilities, eliminating the dependency on Fedora's Ollama RPM.

### Models

- Consolidated model fetching, validation, state, registration and cleanup in
  one focused `modelctl.py`; the public command and TOML catalogs remain.
- Model selection accepts stable ids and Ollama display names as well as the
  existing numeric indices and ranges. Invalid selections now fail clearly.
- Minimal source/checksum state is reused for commits, tags, branches and
  `latest`; use `--refresh` when a moving revision should be fetched again.
- Hugging Face authentication is resolved only when a download is required.
  `HF_TOKEN` or `--token-file` is validated as `ollama`; an invalid or missing
  token falls back to anonymous downloads. Tokens are no longer written to
  operator shell files.
- Model-manager messages are line-buffered and Hugging Face downloads retain a
  pseudo-terminal, keeping status and live byte progress ordered in installer
  transcripts.
- Low-space installation now stops with an explicit cleanup command instead of
  offering destructive cleanup in the middle of a download workflow.
- Cleanup is explicit, asks for confirmation, removes local artifacts and
  registrations, and never edits `%config(noreplace)` catalogs.

### Preserved

- All current production, experiment, task, agentic and MTP catalog entries and
  Modelfiles.
- Strict Modelfile name/source/revision/GGUF/path validation and BC-250
  `num_gpu 99` / `num_keep 256` parameters.
- Main Ollama on 11434, task Ollama on 11435 and agent Ollama on 11436.
- Pinned governor, 40-CU unlock and CU live-manager sources.

## 0.7.1-testing - 2026-07-22

This update focuses on operational stability during model installation on a
pre-production BC-250 appliance.

### Why

- Model fetches were brittle when Hugging Face rate limits or private/gated
  access required a token: the previous prompt was one-shot and not clearly
  validated as the `ollama` service account.
- Operators could select models interactively, but nonstandard sudo/TTY setups
  could fall back poorly and make it hard to trust what would be installed.
- State-file reuse is useful, but testing moving revisions sometimes needs a
  single explicit command to force a new GGUF, hash and Ollama registration.
- Low disk space is common on local LLM appliances. The manager should offer a
  safe cleanup path before failing a large download.

### Changed

- `bc250-model install` now validates `HF_TOKEN` with `hf auth whoami` using the
  `ollama` account.
- If no valid token is available and a TTY exists, the installer offers:
  `[P]ersist`, `[T]his run only` and `[S]kip`.
- Persisted tokens are written to the invoking sudo user's `.bashrc` instead of
  silently targeting root when `SUDO_USER` is available.
- Added `--refresh` to force GGUF download, SHA-256 calculation and Ollama
  registration even when the state file matches.
- Added a low-space cleanup prompt. The default threshold is 30 GiB, or a higher
  explicit/catalog minimum if one is configured; it can be overridden with
  `--cleanup-threshold-bytes` or `BC250_CLEANUP_FREE_BYTES`.
- Added `bc250-model cleanup` for explicit cleanup of enabled production and
  experiment Ollama models.
- Cleanup removes the Ollama registration, source GGUF and adjacent
  `.bc250.json` state file, then disables the installed TOML catalog entry when
  possible.
- If automatic catalog editing is unavailable or fails, cleanup prints the exact
  `sudoedit` command and model id to disable manually.

### Preserved

- Existing command-line arguments remain supported.
- TOML catalogs remain the only model catalog format.
- State files, Modelfile rendering, strict metadata validation and ordinary
  Ollama registration behavior are preserved.
- Production and experiment downloads remain disabled by default.
- Existing `%config(noreplace)` package behavior is unchanged.
