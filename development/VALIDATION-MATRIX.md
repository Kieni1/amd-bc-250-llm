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

Current source baseline while this file was refreshed: `0.11.2-0.4`.
This release keeps runtime/topology policy unchanged while normalizing task/translation model roles: LFM2.5 1.2B remains the sole task model and Translate-Gemma becomes the production translation base, with the former LFM translator retained as an experimental rollback/reference.
Task campaign results were collected on installed `0.11.1-0.10`; Stage-2E translation
configuration evidence was collected through authenticated Open WebUI on installed
`0.11.1-0.11` before the package-owned direction-role integration in this source. Older
operations/power evidence from `0.11.1-0.6` remains historical. Installed
`0.11.2-0.3.fc44` subsequently completed revalidation harness v4.0 with infrastructure
PASS, restoration PASS and full coverage; its evidence is recorded in
`development/model-runs/2026-09-18-installed-0.11.2-0.3-revalidation.md`. The current
`0.11.2-0.4` source changes installer/verification/revalidation coverage rather than the
production model contract, so it still needs its own external RPM build/install before it
can be called current-device qualified.

| Area | Source/static | GitHub RPM | Real BC-250 | Current interpretation / next gate |
|---|---|---|---|---|
| repository/unit validation | SOURCE PARTIAL — focused affected tests/syntax on 0.11.2-0.4; prior full-suite evidence belongs to earlier source | external | N/A | GitHub/workstation own full build/lint validation; do not relabel prior counts as current |
| RPM build/install | preflight only | PENDING/EXTERNAL for 0.11.2-0.4 | HISTORICAL REAL DEVICE — 0.11.2-0.3 installed cleanly | GitHub owns the new package build; installed 0.3 evidence remains the immediate baseline |
| normal service topology | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.2-0.3: install verify 49/0/0; revalidation infrastructure PASS | 0.11.2-0.4 adds required-role model checks; re-check after installing the new RPM |
| office HTTP readiness | SOURCE PASS | external | HISTORICAL REAL DEVICE | include in first operations/power batch |
| maintenance companion | SOURCE PASS | external | PENDING | status/readiness first, then restricted-control test |
| WOL NIC configuration | SOURCE PASS | external | PENDING on current maintenance contract | inspect read-only first |
| real S5 Wake-on-LAN | N/A | N/A | PENDING | highest-value power qualification after baseline |
| safe shutdown defer/allow | SOURCE PASS | external | PENDING | test busy/defer then idle/allow only after S5 WOL succeeds |
| optional backup export | SOURCE PASS | external | PENDING | lower priority; no need to gate office qualification |
| model lifecycle/reconciliation | SOURCE PASS | external | HISTORICAL REAL DEVICE | current role models previously reconciled without needless refetch |
| storage transient-import behavior | N/A | N/A | HISTORICAL REAL DEVICE | Ollama startup pruned four unreferenced conversion/import blobs |
| XFS dedupe correctness | SOURCE PASS | external | HISTORICAL/PARTIAL | preserve GGUFs; current batched implementation still deserves performance qualification |
| benchmark result contract | SOURCE PASS | external | HISTORICAL/PARTIAL | re-establish one current production baseline; new main-candidate gates need real BC-250 evidence |
| whole-appliance revalidation v4.1 | SOURCE PASS — adds live OWUI translation roles, explicit 2048 direct translation budget and clearer mixed-quality summary | external | HISTORICAL REAL DEVICE — v4.0 on 0.11.2-0.3 completed full coverage with infrastructure/restoration PASS | run v4.1 once after 0.11.2-0.4 install; use milestone/release qualification, not every small patch |
| task default: LFM2.5 1.2B | SOURCE PASS — evaluator now accepts the observed `Traduction réglementaire` title | external | HISTORICAL REAL DEVICE — 0.11.2-0.3 returned 5/6 only because of that evaluator vocabulary gap | treat the live output as usable; rerun on 0.11.2-0.4 should confirm 6/6 without changing model/prompt |
| translation production Translate-Gemma | SOURCE PASS — exact Stage-2E role contract; revalidation now includes real OWUI role/filter path | external | HISTORICAL REAL DEVICE — 0.11.2-0.3 direct canonical 8/8 plus authenticated live DE→FR and FR→DE role smoke with no drift | 0.11.2-0.4 should reproduce this via `owui-translation`; LFM remains experimental rollback/reference |

| RAG direct quality | SOURCE PASS | external | HISTORICAL REAL DEVICE — packaged synthetic screen 4/4 on 0.11.2-0.3 | broaden absent-answer, multisource, table/invoice and multilingual real-document cases |
| Open WebUI RAG path | SOURCE PASS | external | HISTORICAL REAL DEVICE — packaged synthetic path 3/3 on 0.11.2-0.3 | plumbing/product path works; real office documents/Tika/OCR breadth still pending |
| embeddings | SOURCE PASS | external | HISTORICAL REAL DEVICE | Jina baseline; Qwen remains comparison; revisit only if RAG evidence justifies |
| standard/general office roles | SOURCE PASS | external | HISTORICAL REAL DEVICE | run current production use-case baseline before comparing main-lane challengers |
| large main-lane candidates | SOURCE PASS | external | PENDING full fit/performance | candidate matrix is resource/performance evidence, not semantic promotion |
| agent default Ornith | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.2-0.3 revalidation 2/3; valid Bash was fenced and therefore failed raw-output format contract | resources/topology are healthy, but behavioral/product qualification remains open; broaden actual `bc250-code` workflows next |
| agent mode restoration | SOURCE PASS | external | HISTORICAL REAL DEVICE | always verify normal topology after exclusive mode |
| OCR comparison | SOURCE PASS | external | HISTORICAL REAL DEVICE | GLM leads fidelity on current small baseline; expand only if OCR becomes product priority |
| MTP runner/catalog | SOURCE PASS | external | PENDING runtime qualification | optional external llama.cpp path; test after higher-priority office lanes |
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
