# BC-250 validation matrix

This file tracks **what kind of evidence exists** and what still needs qualification.
It is development memory, not an installed operator contract. Do not convert `historical`
into `current` merely because a past run was successful.

Status vocabulary:

- **SOURCE PASS** — source-side/unit/static validation exists for the current source.
- **HISTORICAL REAL DEVICE** — useful BC-250 evidence exists, but not necessarily from
  the current source release.
- **CURRENT REAL DEVICE PASS** — explicitly requalified on the installed current release.
- **PENDING** — no sufficient evidence yet.
- **N/A** — that validation class does not apply.

Current source baseline while this file was refreshed: `0.11.3-0.2`.
This source carries forward the 0.11.2-0.6 task/agent diagnostic and `bc250-code` changes and
adds the greenfield `bc250-model` lifecycle rewrite plus active-caller/document migration.
It does not change normal service topology, office production roles, Open WebUI role policy,
CU/governor policy or benchmark acceptance thresholds.

Newest real-device package evidence is historical
`bc250-llm-server-0.11.2-0.5.fc44.x86_64`. Installer verification was 54/0/0 and
revalidation harness v4.1 completed with infrastructure/restoration PASS and full coverage:
production use-case 5/5, task 5/6, direct translation 8/8, direct RAG 4/4, embeddings 1/1,
agent 3/3, authenticated Open WebUI translation 8/8 and Open WebUI RAG 3/3. The one task
miss was `tags-de`, which emitted two JSON objects. Exact evidence is recorded in
`development/model-runs/2026-09-18-installed-0.11.2-0.5-revalidation.md`. Historical
`0.11.2-0.4` remains the run that exposed the installed translation-fixture path defect;
do not rewrite either record to the current source NVR.

| Area | Source/static | GitHub RPM | Real BC-250 | Current interpretation / next gate |
|---|---|---|---|---|
| repository/unit validation | SOURCE PASS — `make validate` passed repository/RPM preflight, packaged shell syntax and 367/367 deterministic tests on current 0.11.3-0.2 source | PENDING/EXTERNAL | N/A | Ruff/ShellCheck remain workstation-owned and were not run here; GitHub build remains external |
| RPM build/install | source metadata and release closure are current at 0.11.3-0.2 | PENDING/EXTERNAL for 0.11.3-0.2 | HISTORICAL REAL DEVICE — 0.11.2-0.5.fc44 installed cleanly | GitHub builds 0.11.3-0.2; capture exact installed NEVRA before device conclusions |
| normal service topology | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.2-0.5 full revalidation/restoration PASS | unchanged by the 0.11.3 model-manager rewrite; verify normal topology after install |
| office HTTP readiness | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.2-0.5 Open WebUI reachable/drift none | include in normal post-install verifier; power campaign remains separate |
| maintenance companion | SOURCE PASS | external | HISTORICAL/PARTIAL — companion intentionally unconfigured on 0.11.2-0.5 run | status/readiness first when power work resumes |
| WOL NIC configuration | SOURCE PASS | external | PENDING on current maintenance contract | inspect read-only first |
| real S5 Wake-on-LAN | N/A | N/A | PENDING | highest-value next power qualification, but do not mix with agent campaign |
| safe shutdown defer/allow | SOURCE PASS | external | PENDING | test busy/defer then idle/allow only after S5 WOL succeeds |
| optional backup export | SOURCE PASS | external | PENDING | lower priority; no need to gate agent/source qualification |
| model lifecycle/reconciliation | SOURCE PASS — new list/status/path/apply/refresh/unregister/remove/purge-retired contract, active callers, migration hints and lifecycle state semantics are covered by the current 367/367 source gate | external | HISTORICAL REAL DEVICE for pre-rewrite lifecycle | qualify reconciliation on installed 0.11.3-0.2 before treating it as current device evidence |
| storage transient-import behavior | N/A | N/A | HISTORICAL REAL DEVICE | preserve prior Ollama cleanup/dedupe lessons |
| XFS dedupe correctness | SOURCE PASS | external | HISTORICAL/PARTIAL | preserve GGUFs; batched implementation still deserves performance qualification |
| benchmark result contract | SOURCE PASS — mixed-quality summaries retain failed case IDs; task structural failure attribution is non-cascading | external | HISTORICAL REAL DEVICE on 0.5 pre-change reporting | first 0.11.3 device benchmark should confirm case-level status UX without changing acceptance |
| whole-appliance revalidation v4.2 | SOURCE PASS — target is 0.11.3; diagnostics/checkpoint/GPT-OSS ownership changes covered by source tests | external | HISTORICAL REAL DEVICE — 0.11.2-0.5 completed v4.1 infrastructure/restoration PASS with full coverage | rerun v4.2 on installed 0.11.3-0.2; do not relabel the 0.5 v4.1 run current |
| task default: LFM2.5 1.2B | SOURCE PASS — `tags-de` double JSON stays `format-contract` without derivative language/relevance causes | external | HISTORICAL REAL DEVICE — 0.11.2-0.5 task 5/6 | preserve the real quality miss; do not weaken strict single-object JSON |
| translation production Translate-Gemma | SOURCE PASS — production contract unchanged | external | HISTORICAL REAL DEVICE — 0.11.2-0.5 direct 8/8 + OWUI 8/8 | no translation retuning required by the model-manager rewrite |
| RAG direct quality | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.2-0.5 direct 4/4 | broaden real-document cases only in a separate RAG campaign |
| Open WebUI RAG path | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.2-0.5 packaged path 3/3 | plumbing/product path healthy; real-office breadth remains separate |
| embeddings | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.2-0.5 embedding 1/1 plus coexistence infrastructure PASS | Jina baseline unchanged |
| standard/general office roles | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.2-0.5 production use-case 5/5 | no main-role change in the model-manager rewrite |
| large main-lane candidates | SOURCE PASS | external | PENDING full fit/performance | unchanged; do not mix with current agent funnel |
| agent default Ornith static benchmark | SOURCE PASS — reasoning leakage is now an explicit format failure | external | HISTORICAL REAL DEVICE — 0.11.2-0.5 canonical agent 3/3 | keep Ornith baseline; static success is not product-path completion proof |
| `bc250-code` product route | SOURCE PASS — route/default/fail-closed/atomic-update contract asserted from source and shell syntax checked; no live helper execution | external | PENDING for 0.11.3-0.2 | first bounded device check: final-content separation, terminal/length refusal, 3072 vs 6144 only on explicit truncation |
| new Qwen3.5 4B / Gemma E4B agent challengers | SOURCE PASS — Modelfiles discoverable/strict | external | PENDING | compare only after baseline product route is proven; no promotion claims yet |
| agent mode restoration | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.2-0.5 restoration PASS | verify again on installed 0.11.3-0.2 after the focused product-route check |
| OCR comparison | SOURCE PASS | external | HISTORICAL REAL DEVICE | GLM leads current small fidelity baseline; unchanged |
| MTP lifecycle/runner/catalog | SOURCE PASS | external llama.cpp | PENDING runtime qualification | 0.11.3-0.2: explicit disabled-entry fetch path, stable global indexes and lifecycle integration covered; no hardware claim |
| MTP speedup/acceptance | N/A | N/A | PENDING | compare same useful workload and record acceptance rate, quality and memory—not speed alone |

## How to update this matrix

After a meaningful real-device batch, change only the affected rows. Record the exact
installed NEVRA and evidence artifact in the corresponding model-run/decision record;
do not turn this table into a long run log.

A package change does **not** automatically invalidate every historical row. Requalify
by impact:

- runtime/service/package topology change → operations + affected integration lanes;
- model/Modelfile/prompt change → affected quality lane + resource/coexistence if needed;
- benchmark implementation change → benchmark-operation baseline before trusting new scores;
- documentation/test-only change → source gate is normally sufficient;
- milestone or pre-v1.0 release candidate → full `bc250-revalidate` plus selected human-use cases.
