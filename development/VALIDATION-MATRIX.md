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

Current source baseline while this file was refreshed: `0.11.2-0.5`.
This release keeps runtime/topology/model policy unchanged and fixes qualification/package-resource reliability: benchmark fixtures and Open WebUI desired-state inputs now use one source/install resolver, and CI installer tests no longer depend on host `jq` availability.
Task campaign results were collected on installed `0.11.1-0.10`; Stage-2E translation
configuration evidence was collected through authenticated Open WebUI on installed
`0.11.1-0.11` before the package-owned direction-role integration in this source. Older
operations/power evidence from `0.11.1-0.6` remains historical. Installed
`0.11.2-0.3.fc44` subsequently completed revalidation harness v4.0 with infrastructure
PASS, restoration PASS and full coverage; its evidence is recorded in
`development/model-runs/2026-09-18-installed-0.11.2-0.3-revalidation.md`. Installed
`0.11.2-0.4` subsequently reached revalidation harness v4.1 phase 5/6, where
`owui-translation` failed infrastructure before quality evaluation because the installed
libexec script looked for `/usr/examples/benchmark/translation-office.json`. Release
`0.11.2-0.5` fixes that source-vs-installed resource lookup and still needs its own external
RPM build/install plus a device rerun before it can be called current-device qualified.

| Area | Source/static | GitHub RPM | Real BC-250 | Current interpretation / next gate |
|---|---|---|---|---|
| repository/unit validation | SOURCE PARTIAL — focused affected tests plus repository preflight/syntax on 0.11.2-0.5; prior full-suite evidence belongs to earlier source | external | N/A | GitHub/workstation own full build/lint validation; do not relabel prior counts as current |
| RPM build/install | preflight only | PENDING/EXTERNAL for 0.11.2-0.5 | HISTORICAL REAL DEVICE — 0.11.2-0.4 installed and launched v4.1 | GitHub owns the new package build; install 0.5 before repeating device qualification |
| normal service topology | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.2-0.4 reached phase 5/6 without a topology infrastructure failure | 0.11.2-0.5 changes resource lookup/test portability only; re-check through the normal device rerun |
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
| whole-appliance revalidation v4.1 | SOURCE PASS — installed/source resource lookup is now shared by benchmark lanes | external | HISTORICAL/PARTIAL — 0.11.2-0.4 reached phase 5/6 then `owui-translation` infra-failed on the invalid `/usr/examples/...` fixture path | install 0.11.2-0.5 and rerun v4.1; quality failures before phase 5 remain separate evidence |
| task default: LFM2.5 1.2B | SOURCE PASS — evaluator accepts the observed `Traduction réglementaire` title | external | HISTORICAL REAL DEVICE — 0.11.2-0.3 returned 5/6 only because of that evaluator vocabulary gap | no task model/prompt change in 0.5; preserve the existing task evidence until the next full device result |
| translation production Translate-Gemma | SOURCE PASS — exact Stage-2E role contract plus shared installed fixture resolution | external | HISTORICAL REAL DEVICE — 0.11.2-0.3 direct canonical 8/8 plus authenticated live DE→FR and FR→DE role smoke; 0.11.2-0.4 OWUI qualification did not execute because fixture open failed first | 0.11.2-0.5 should finally exercise the canonical `owui-translation` quality path; LFM remains experimental rollback/reference |

| RAG direct quality | SOURCE PASS | external | HISTORICAL/PARTIAL — 0.11.2-0.4 revalidation reported 3/4 (`answer=1`) before the later OWUI infrastructure stop | keep this quality failure distinct from the fixture-path defect; broaden absent-answer, multisource, table/invoice and multilingual real-document cases |
| Open WebUI RAG path | SOURCE PASS | external | HISTORICAL REAL DEVICE — packaged synthetic path 3/3 on 0.11.2-0.3 | plumbing/product path works; real office documents/Tika/OCR breadth still pending |
| embeddings | SOURCE PASS | external | HISTORICAL REAL DEVICE | Jina baseline; Qwen remains comparison; revisit only if RAG evidence justifies |
| standard/general office roles | SOURCE PASS | external | HISTORICAL REAL DEVICE | run current production use-case baseline before comparing main-lane challengers |
| large main-lane candidates | SOURCE PASS | external | PENDING full fit/performance | candidate matrix is resource/performance evidence, not semantic promotion |
| agent default Ornith | SOURCE PASS | external | HISTORICAL/PARTIAL — 0.11.2-0.4 revalidation again reported 2/3, this time with one `empty-output`; 0.11.2-0.3 had a separate fenced-output miss | resources/topology are healthy, but behavioral/product qualification remains open; broaden actual `bc250-code` workflows next |
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
