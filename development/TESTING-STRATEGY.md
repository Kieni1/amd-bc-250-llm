# BC-250 testing strategy

This is the development plan for continuing BC-250 qualification without repeatedly
running one giant hardware campaign. The package already separates health,
measurement, and qualification; the testing process should preserve that separation.

## 0. Select development scope before selecting tests

The routine test surface is defined by `development/DEVELOPMENT-SCOPE.json`. Before a batch:

1. run `python3 development/scope.py check`;
2. map the changed paths with `python3 development/scope.py map ...`;
3. run focused tests for affected **active** components;
4. add **boundary_active** tests only when that boundary changed or an active change crosses its listed interface;
5. do not rerun **frozen** component suites when their baseline hash is unchanged;
6. do not load **archive_only** evidence unless a specific provenance question requires it.

Current frozen domains are maintenance/companion, MTP, coding-agent and OCR. RAG/Tika is product-relevant and active; uninstall is a boundary-active lifecycle surface. Frozen domains remain available but their source is held until deliberately thawed. The full deterministic/package gate still applies at a release milestone.

This scope layer is specifically intended to avoid repeatedly paying for closed investigations such as the
current Tika serialization work and for unrelated optional subsystems such as maintenance while Advanced,
translation, installer/Open WebUI and benchmark/revalidation work continues.

## 1. Three different questions

Use the right tool for the question:

| Question | Primary tool |
|---|---|
| Is the appliance healthy right now? | `bc250 verify` |
| Which model/setting behaves better? | `bc250 benchmark ...` |
| Does the package configuration qualify as a whole? | `bc250 revalidate` |

Do not use a benchmark win as proof of appliance health. Do not use a healthy verifier
as proof of model quality. Do not run whole-appliance revalidation merely to compare
one candidate.

## 2. Test ownership

- **Source/chat environment:** unit/static checks that are actually available.
- **GitHub:** RPM/package build.
- **Workstation:** Ruff and developer linting as configured by the user.
- **BC-250:** real services, GPU/resource behavior, model quality, WOL/power, Open WebUI,
  llama.cpp/MTP and integration qualification.

Never substitute an unavailable local check with an imitation and report it as real.

The deterministic source/unit gate must remain host-independent. Runtime shell integrations
that depend on packaged tools such as `jq` belong to installed-package/BC-250 qualification.
Do not build source tests that mock a package-manager install and then expect absolute host files
(e.g. `/usr/bin/...`) to appear: a fake `dnf` cannot mutate the test host safely. For those
boundaries, prefer deterministic source/ordering assertions or mock the filesystem probe itself.
source tests should exercise the underlying data/format contracts without invoking those runtime
dependencies.

Installer/model-manager source coverage must also protect the setup UX contract: catalog suppression
must actually suppress the redundant pre-apply catalog, local registration discovery must be bounded
and skip the known-inactive agent lane, combined `apply all` / `refresh all` must never acquire MTP,
and unchanged required models may collapse to concise category summaries without hiding any real
repair/download action. Do not make this fast by weakening GGUF provenance/SHA behavior.

The current 0.13.1-1.7 source builds on the 1.6 GFX1013 safety/observability source candidate while the last operator-confirmed built package checkpoint remains 0.13.1-1.5. Release 1.7 is bounded QoL/qualification work: reboot-aware same-package GFX1013 A1/B/A2 benchmarking, evidence inventory/cleanup, exact version reporting and shell completion. The 1.6 Secure Boot, exact-kernel, rollback and private-RADV runtime guards are not weakened. Runtime/model/CU defaults remain frozen at 32K, q8_0 KV, parallel=1, flash attention on, current keep-alive/Deep admission policy and current production model identities. GFX1013 remains profile v0.2.1-alpha, experimental and default-off. Configured Ruff/ShellCheck, `%check`, rpmlint, RPM payload validation and clean SRPM rebuild remain grouped under the authoritative Fedora `make release-gate`; Agent remains optional and broad model/runtime discovery stays closed.


Revalidation diagnostics are evidence visibility, not new acceptance gates. Keep the 128 MiB
MemAvailable hard floor unchanged; below 512 MiB may be surfaced as tight headroom. Likewise, an
accepted use case with `output-budget` remains a PASS but should be visible in the top-level
Diagnostics section.

## 3. Common promotion funnel

For a candidate change, stop as soon as it no longer has a promotion case.

1. **Source/static gate** — package parses/tests; model definition is sane.
2. **Cheap/direct screen** — deterministic fixture on the narrow role contract.
3. **Real integration path** — Open WebUI or package workflow where the product uses it.
4. **Resource/coexistence gate** — memory, swap, latency, topology and thermal evidence.
5. **Repeatability** — repeat only finalists or production defaults, not every loser.
6. **Decision record** — observed facts, interpretation, decision, retest conditions.

A larger model does not advance merely because it is interesting. A quality winner does
not promote if it makes the real appliance unsafe or unresponsive.

## 4. Evidence envelope for every BC-250 batch

Record:

```text
source release / source SHA when available
installed RPM NEVRA
runtime versions
exact model IDs and relevant digests
exact command(s)
effective settings / benchmark profile
result directory or evidence archive + SHA-256
verifier/topology before and after when stateful
observed facts
interpretation
decision / next gate
restoration result
```

Do not include GGUF contents, API keys, HF tokens, passwords or private backup data.

## 5. Cadence: one bounded hardware batch at a time

The next batch should depend on the previous result. In particular, do not provide a
five-stage destructive machine plan up front. Use read-only baseline evidence before
state changes. Restore state before moving to another lane.

## Closed optimization-program lessons carried into 0.13.1-1.3

- Sidechat 15: keep current residency/keepalive/swappiness/Deep pre-eviction defaults.
- Sidechat 16: keep 32K and production output ceilings; q4_0 was candidate-only.
- Sidechat 17: keep parallel=1, flash attention, automatic num_batch, full GPU offload and governor policy.
- Sidechat 18/19: promote RAG TOP_K=4, reject q4_0 after integrated Advanced instability.
- Performance evidence must record starting SwapUsed, memory PSI, MemAvailable and resident model set.
- Clean 6144-token reasoning exhaustion with no visible answer is INCOMPLETE; repetition at that ceiling is a quality failure.
- Task title/tag persistence is authoritative; missing a short-lived task residency sample is not itself failure.
- Semantic evaluators should normalize unambiguous dates/times/invoice identifiers, parse grouped citation membership, and use required numeric membership rather than relying on one surface form or the last number in an explanation.
- RAG hidden-reasoning exhaustion with empty visible output is INCOMPLETE/retry only when no independent retrieval/semantic defect exists; repetition remains a quality failure.
- Verification must distinguish a configured/initialized zram device from a `/dev/zramN` that is actually active swap, and must parse actual failed systemd unit rows.

## Current 0.13.1-1.7 qualification boundary

Exact 0.12.2-0.8 device evidence is qualified and is the immediate predecessor baseline: upgrade/convergence PASS, `bc250 verify` 53/0/0/0, 40/40 live CU with exact saved-profile boot restoration, clean Open WebUI desired state, revalidation Infrastructure/Restoration PASS, RAG direct + OWUI product PASS, ordinary-user ACL/product journeys PASS, and correct optional-Agent PARTIAL coverage. The only layout REVIEW was runtime Python bytecode written under package-owned `/usr`.

The pre-0.13.1 investigation attributed those writes to dispatcher-launched RAG/benchmark Python imports and proved `PYTHONDONTWRITEBYTECODE=1` prevents them. It also proved optional absent/cached models were semantically healthy despite `MISSING`/false `DRIFT` labels, and that graveyard source content must stay inert while an operator-manually registered historical model still follows normal Open WebUI testing-policy visibility. Those hygiene/model-state fixes shipped in the final 0.13.1-1.0 logic checkpoint and remain protected in 1.2. The 1.1 delta was the closed Sidechat 15–19 RAG/tooling/readiness/verification work described above; the 1.2 corrective delta narrows semantic substitution and hardens HTTP/swap diagnostics without changing qualified defaults; exact-device testing should therefore upgrade the exact 1.0 baseline to 1.2 and exercise only that bounded delta unless it exposes a regression.

For 1.6, the package-build gate is intentionally separate from device qualification. The operator-provided Fedora workstation sequence is authoritative for source cache, Ruff/ShellCheck, preflight, RPM `%check`, configured rpmlint, binary payload and clean SRPM rebuild. Device work should then focus on the changed safety boundary: 1.5 -> 1.6 upgrade with GFX disabled and, when applicable, prepared/enabled-state rollback; `bc250 doctor`; JSON status schemas; Secure Boot refusal; `prepare --check`; one-shot patched boot; exact BC-250 RADV identity; stale/new-stock-kernel Ollama guard; disable/reset; and final stock saved + next boot restoration. Do not turn this into another broad model tournament.

## 6. Recommended current work order

### Lane A — general operations / office availability / power

This is currently the highest product priority because the Pi/maintenance contract was
added after much of the older hardware evidence.

Exact installed 0.11.3-1.7 is now the newest whole-appliance baseline: guided install/core
verification 54/0/0, Open WebUI baseline APPLIED + VERIFIED, and v4.2
infrastructure/restoration PASS, FULL coverage and quality 8/8. Preserve that evidence as exact 1.7;
do not relabel it as current 2.2.

The following exact-1.7 support campaign passed read-only health, normal<->agent transitions,
deliberate degraded detection/recovery, verified local backups and pruning dry-run, then exposed a
P1 safe-power failure: an active interactive SSH session was not detected because the parser checked
the wrong fixed `ss` columns. It also exposed healthy live 40/40 status/verify returning rc=1 when
persistent boot activation was intentionally disabled. Release 1.8 fixed those source defects and added an exact forced-companion SSH exception rather
than a broad SSH bypass; 2.1 carries that implementation forward unchanged.

Exact 2.3 has now passed the targeted operations acceptance introduced by the 2.3 release: clean `rpm -V`, swap 0750 convergence, topology-aware status/verifier UX, `bc250 agent-mode normal`, degraded recovery, DRY_RUN/timer output, Tika restart semantics, baseline-aware identity restore, supported reboot reconstruction, live 40/40 and final authenticated 54/0/0. Preserve this as exact-2.3 evidence.

A separate exact-2.3 authenticated Open WebUI investigation found the application path healthy: HTTP readiness, task routing, Standard/Higher Quality/Deep Reasoning roles, translation 8/8 and bounded RAG 3/3 all passed. It also found three product-state ownership gaps addressed in the historical 2.4 source: Arena persistence, explicit ownership of implementation-model visibility, and persisted local/offline/upload policy in apply/status. Exact 0.12.1-0.6 then qualified the ordinary-user lifecycle, curated roles, raw testing-surface visibility, RAG and multi-model compare on OWUI 0.11.3. Current 0.12.2 keeps discovered normal main/task testing records, retires Qwen3.6 35B, keeps Qwen3.8 Unsloth and ISTA IQ3_S admin/testing-only, and leaves ISTA IQ3_XXS as the ordinary-user deployability comparison; it also crosses to OWUI 0.11.4 and therefore requires the bounded stored-record, browser-journey, ACL, reasoning-persistence and effective-request checks in the release handover rather than inheriting the 0.11.3 result.

The distinct `sudo systemctl reboot` invocation is device-proven unreliable on this BC-250: it enters a new boot and progresses substantially before the boot can become unusable/crash-recorded. Do not keep reproducing that failure. Exact-2.3 acceptance found one remaining reachable occurrence in the pinned CU live manager's interactive CPU-core-unlock reboot prompt. Source 2.4 patches that upstream path to `/usr/sbin/reboot` through the existing package patch while preserving its interactive/no-reboot-under-`--yes` contract.

Companion forced-command, idle S5/WOL and live upload deletion are separate acceptance work and become mandatory only when those optional features are about to be enabled or their boundary changed. Do not turn them into automatic gates for unrelated RPMs. The model unregister/re-apply support block is likewise optional unless the model lifecycle changed; if used, inspect protected source paths with privileged `test/stat` and avoid `refresh`/`remove` when the purpose is no-redownload lifecycle verification.

The current harness v4.8 qualifies the package-owned production roles for the 0.13.1-1.7 line and remains the milestone whole-appliance gate. It records starting swap, memory-pressure and residency evidence so state-dependent resource events are not misclassified as tuning effects.

For RAG, model selection is closed: use Gemma E4B for the production document role. Future RAG
acceptance should be one bounded real-office corpus pass (real PDFs/Tika/OCR, tables, multilingual
and multisource questions, upload/delete/re-upload, one unload/reload and a long resident session),
not another model zoo or a new benchmark framework. Treat this as product acceptance, not an
automatic RPM-release gate.

To preserve evidence value while avoiding redundant runtime, v4.6 keeps direct and
product-path semantic checks distinct, but removes the duplicate generic GPT-OSS edge
performance pass because the dedicated GPT-OSS/Jina coexistence stage is the stronger
resource check. Successful intermediate phases use lightweight checkpoints; full
snapshots remain at preflight, agent transitions, final restoration and failures.

Power ordering is now evidence-driven: prove the busy/defer guard and companion exception first,
then allow a real idle poweroff and prove S5 WOL/recovery. Backup export remains separate and lower
priority; backup restore/rollback is higher-value than export because it validates local recovery.

### Lane B — benchmark operations

Before trusting a large new benchmark campaign, establish that the measurement layer
still behaves correctly on the current installed package.

Use a **small production control set**, not every model:

- one normal generation run on a known production model;
- one role-quality benchmark such as `usecase` or `task`;
- one stateful benchmark only if its subsystem is about to be tested;
- verify canonical `meta.json`, `results.jsonl`, `summary.json`, `summary.txt`;
- verify result isolation and refusal to merge into a non-empty output directory;
- for mutating OWUI benchmarks, verify exact restoration and no secret leakage.

Once the benchmark substrate is trusted, specialist lanes can reuse it without
revalidating every formatter on every run.

### Lane C — task and translation role decisions

The current task search is **not** an open invitation to keep trying larger models.
`task-lfm25-1.2b-instruct-liquidai-q6-k` remains the production default. Installed
0.11.3-0.2 again produced the same `tags-de` double-JSON format miss, so 0.11.3-0.3
tightens only the tag prompt: broad/specific tags share one array and exactly one raw JSON
object is allowed. First retest the existing six canonical task cases; do not change the
strict evaluator or 128-token budget to make that result green. Qwen3 4B remains a
role-specific rejection despite 5/6 quality because both exact-source and bounded-4K task
staging caused global OOM and warm-main loss. Future materially larger task challengers
must pass one cheap quality screen, then the tiny warm-main survival gate, before
product-path or repeated quality work.

For translation, broad model/configuration qualification is now closed. Stage-2E selected
Translate-Gemma E4B with the exact explicit-direction v1 contract, thinking omitted and
`max_tokens=2048`. By maintainer decision, Translate-Gemma is now the package production
translation base behind the two package-owned direction roles. The current release still
needs one bounded post-install product-path verification before it is called fully
hardware-qualified. Corrected long-run evidence retires LFM from active comparison because it
reproduces the same recommendation→obligation failure; TIR is closed as the normal deployment
choice under current evidence.

Next translation sequence:

1. install the production translation model with
   `sudo bc250 model apply production prod-translate-gemma4-sub-e4b-17s-q4-k-xl`,
   then apply the source-owned `bc250-office-translation-de-fr` and
   `bc250-office-translation-fr-de` desired state;
2. verify the exact system prompt, non-global direction Filter, `max_tokens=2048`, and
   no forced `think` through authenticated Open WebUI desired state;
3. run one or two repetitions of the bounded final set only: canonical sanity plus the
   Stage-2 targeted protected-finance, bullets/table, `Avoir`, and both long-document
   cases;
4. verify preset/provider/function restoration or desired-state integrity, privacy,
   memory and serious GPU/OOM warnings;
5. if the integrated production path is unacceptable, classify the remaining defect
   before deciding whether rollback or product-layer handling is required; do not silently
   reopen broad model discovery.

Do not restart the broad translation candidate campaign or resume preservation prompt
micro-tuning. Exact byte-for-byte protected financial typography is not claimed by the
current integration; preserve the known caveat rather than weakening the evaluator.

### Lane D — RAG / office documents

RAG is a core office use case and is now model-selected for the current 16 GiB profile. The
2026-09-19 finalist campaign keeps Gemma E4B / `bc250-office-documents` as the production document
answer role because both finalists were strong in short product-path RAG but Qwen 9B reached the
residency campaign's 512 MiB safety floor after only a few resident subruns while Gemma completed
42/42 continuous-residency turns with about 2.7 GiB MemAvailable remaining. That is a
resource-safety/product-role decision, not a Qwen semantic-quality rejection.

Future RAG work should therefore proceed in layers without reopening the answer-model tournament:

1. **real document ingestion/extraction** with PDFs and actual Tika output;
2. **retrieval and grounded answer quality** on messy office material, tables, multilingual and
   multi-source questions, including abstention;
3. **collection lifecycle** including upload/delete/re-upload and reindex/reimport behavior;
4. **long-lived product use** with conversation growth, one deliberate unload/reload cycle and
   sustained telemetry;
5. only then A/B one retrieval/tuning axis at a time if real-document evidence exposes a problem.

Direct `rag-quality` isolation must also be state-preserving. Snapshot the main and embedding
Ollama residency sets before unloading anything, restore and verify the starting residency sets on every
exit path, and treat restoration failure as infrastructure failure. Embedding-only restoration must use
a real non-empty `/api/embed` probe; unit coverage must assert that payload directly so source tests do
not accept a request Ollama rejects at runtime. Resource evidence should show
resident-session MemAvailable start/min/end/delta and swap start/peak/end/`swap_peak_delta_mib` so
sustained pressure is visible without falsely describing peak-minus-start swap as cumulative growth.
These measurements are diagnostics/evidence; do not invent new thresholds from one campaign.

Direct RAG scoring must remain deterministic. Use boundary-aware acceptance for values and
explicit fixture alternatives/numeric equivalence; keep target/all-support retrieval, fact or
abstention, language and citation independent. A language-neutral short value may be
`not-measurable` without being a failure, and canonical quality evidence must contain every
expected case exactly once before it is treated as complete.

Expand the fixture around the failure modes that matter for office use:

- answer absent / required abstention;
- multiple required sources;
- conflicting documents;
- invoices/tables and OCR-derived text;
- German/French/multilingual documents;
- preservation of names, numbers and dates;
- citation/source correctness;
- privacy-restricted or insufficient-evidence questions.

Do not change retrieval and answer model/settings in the same experiment unless the
question explicitly requires an interaction study.

### Lane E — general assistant / main lane

Start with the production role map, not experimental candidates:

- `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` — standard office;
- `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` — RAG answer;
- `prod-qwen35-9b-unsloth-q6-k` — higher-quality office;
- `prod-gpt-oss20b-ggml-org-mxfp4` — deep reasoning / worst-case production memory reference.

The main lane itself stays warm under its normal 20-minute policy; GPT-OSS is not a permanently warm
universal model. Before opening another large-candidate search, answer the bounded product question:
**does GPT-OSS provide materially better deep-office reasoning than Qwen3.5 9B under their actual
production contracts, enough to justify its roughly 4 GiB higher memory cost?** Use one reusable
12–16 case `usecase` fixture with deterministic checks where objective and preserved full outputs for
manual/pairwise review where quality cannot safely be reduced to keywords.

Candidate qualification follows this funnel:

```text
load / resource / backend-aware completion integrity
-> tiny semantic sanity (`bc250 benchmark usecase`)
-> optional 4K/16K context performance where useful
-> gfx1013/runtime stability
-> optional sustained thermal/CU testing for finalists
-> full semantic + product-path + coexistence qualification
-> restoration/integrity verification
-> decision
```

Evidence must record the exact runtime/build/meaningful flags, KV cache type, memory/swap
and GPU-journal state. Use the highest-precision **feasible** KV configuration as the
correctness reference; compare compressed KV types model-by-model rather than changing a
global default. Do not force F16 or 32K when they make the candidate's intended envelope
infeasible.

For affected hybrid/SSM/direct-llama paths on gfx1013, compare runtime-default ubatch
against `384` as a conservative control only when warranted by the path. Do not set 384
globally from external GFX10 reports. Current CU/governor policy remains unchanged.

First establish current production `usecase` and representative generation/resource
metrics with normal task+embedding topology present. Only candidates that survive the
cheap gates advance to the broader human/general-office corpus. Human review should remain
explicit for subjective dimensions such as helpfulness, correction/follow-up quality and
overall daily-use acceptability. Do not manufacture a single precise score for inherently
subjective judgments.

### Lane F — agentic / coding

Agent mode is exclusive by design. Always capture normal topology before entry and
verify full restoration after leaving.

Keep two test layers separate:

1. `bc250 benchmark agent` — safe static shape/syntax/contract evidence;
2. actual `bc250 code` workflows on disposable inputs — review, refactor, tests,
   documentation, structured config work and commit-message generation.

The product helper must consume final content separately from native reasoning and fail
closed on nonterminal completion, output-limit truncation or literal reasoning markers.
Do not treat a successful HTTP response as valid inference unless terminal completion
integrity passes. Keep the package default output budget at 3072 until a bounded A/B
shows that a higher default improves complete product outputs without unacceptable cost;
use `CODING_AGENT_NUM_PREDICT` for that comparison.

Generated code must not be automatically executed as root. If behavior needs execution,
run deliberately reviewed output in a disposable/safe context and then run the relevant
real tests. The product claim remains a local coding helper, not an autonomous repository
agent.

For the next comparative funnel, use Ornith as baseline, then Qwable 9B, Qwen3.5 4B
Q6_K and Gemma 4 E4B Q4_K_M, followed by the baseline again. Reject cheaply on
completion integrity/static semantics before promoting candidates into broader real
`bc250 code` workflows. Only revisit Gemma 4 12B if the E4B comparison leaves that
question open.

### Lane G — MTP / speculative decoding

Broad MTP qualification is closed for the current BC-250/runtime combination. The package now
encodes the final selection directly in the existing disabled/download-only MTP catalog:

```text
qwen3.5-9b-mtp             primary fast,        ctx 16384 / draft 2
qwen3.8-27b-ymq-xs-ti-mtp  primary general 27B, ctx 8192  / draft 1
qwen3.8-27b-hauhaucs-mtp   specialist alternative, ctx 8192 / draft 2
```

`qwen3.6-27b-mtp` is retired from active discovery because optimized Qwen3.8 choices now provide
better absolute throughput, memory margin and completion efficiency; its positive historical
qualification remains preserved in the source-only graveyard. The stock Qwen3.6 35B-A3B fit
failure remains retired unchanged.

Do not run another broad MTP campaign for this release. A three-repeat YMQ depth-1 confirmation is
optional only if future policy demands symmetric confirmation for every default promotion.
`bc250 compare-mtp` remains the same-target evidence harness and `bc250 run-mtp [--no-mtp] ID` the
manual diagnostic path. Direct runs restore captured Ollama residency; comparison uses drain-only
isolation. Add framework only if new hardware evidence exposes a concrete lifecycle/measurement gap.

## 7. Routine revalidation vs specialist campaigns

Run full `bc250 revalidate` when:

- preparing a meaningful release candidate;
- runtime/service topology changed;
- a promoted role model changed;
- Open WebUI/package integration changed materially;
- enough independent changes accumulated that cross-lane interaction is uncertain.

Do **not** run full revalidation after a documentation-only/source-memory refresh.

Specialist campaigns should return to main integration with a compact handoff and should
not independently change production defaults, release metadata or cross-stream policy.

## 8. Promotion rules

Promotion requires all applicable gates:

```text
quality improvement or clear role benefit
real product-path success
resource safety on 16 GB shared GDDR6
acceptable latency/UX
repeatability
restoration/integrity clean
no regression of another production role
```

When a candidate is rejected, record **Retest only if** conditions so future work does
not repeat a disproven experiment without a material reason.
## 2026-09-19 operator-boundary hardening for 0.11.3-1.7

The current release closes several source-review boundary defects without changing appliance
topology or model defaults. Deterministic source coverage must preserve these contracts:

- `bc250 status` obtains `normal|degraded|stopped|agent` from the existing agent-mode classifier;
  agent inactivity alone must never imply a healthy normal topology.
- Explicit Open WebUI/Hugging Face token files are private credential files: regular, non-empty and
  not group/world accessible. Environment-provided tokens remain separate ephemeral inputs.
- `bc250 code` file-producing/structured modes reject an outer Markdown fence rather than silently
  stripping it or atomically writing fenced source.
- Installer completion reports Open WebUI baseline state independently from core verification;
  skipped/retry-required application setup remains nonfatal but visible.
- Safe-power remains deliberately conservative about protected TCP activity on either endpoint;
  wording/tests must not imply only inbound UI sessions are considered.
- Upload pruning must not assume an Open WebUI page size. Continue until zero records, advertised
  total completion, or no new IDs, while preserving uncertain metadata from deletion.

These are source/unit boundaries. The upcoming support/maintenance device campaign still owns real
S5 WOL, busy/defer, idle/allow, backup/export, timer and recovery qualification.



## 2026-09-20 support safety closure for 0.11.3-1.8

Deterministic source coverage must preserve these newly observed contracts:

- `ss -Htn state established` endpoint matching uses the final two fields, not fixed field numbers;
  an interactive local `:22` connection must defer public `request-shutdown`.
- The companion path may exempt only the validated OpenSSH `SSH_CONNECTION` tuple belonging to the
  restricted `bc250-power-control` forced command. Any second SSH session still defers.
- The final `poweroff`/`suspend` systemd request is non-blocking after guards pass, so the safe-power
  decision unit can finish cleanly.
- Live 40/40 routing with persistent boot activation intentionally disabled is healthy and must not
  inherit rc=1 from an absent persistent-config hint.
- Unprivileged status must label protected state as protected/unavailable rather than rendering it as
  zero or absent.
- Operator overlay files in `/etc/bc250-llm-server/models.d/` that are visible regular files but do
  not end in `.Modelfile` are configuration errors, not silently ignored input.
- Category `all` and selection `all` stay distinct. Destructive omission never means all.
- Prune arithmetic remains byte-precise; B/KiB/MiB/GiB is display-only operator UX.

The current 2.2 source owns the next hardware qualification; 1.8 remains the source release where
these fixes were introduced. First prove public SSH defer and healthy 40-CU return-code behavior.
Companion-only exemption, second-SSH defer and real idle S5/WOL are conditional acceptance gates
before unattended power behavior is enabled, not automatic gates for every RPM.

## 0.13.1-1.3 build/test rationalization

The normal RPM path performs cheap package-specific preflight before `rpmbuild`; `%check` owns the complete deterministic suite so the same expensive suite is not run twice for one RPM build. Ruff, ShellCheck, rpmlint and actual package build remain authoritative for their own domains. Release/manual CI additionally rebuilds the generated SRPM from a clean temporary RPM topdir. Source0 must be independent of host timezone, irrelevant checkout modes and local `sources/` cache state.
