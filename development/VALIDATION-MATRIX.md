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

Current source baseline while this file was refreshed: `0.11.1-0.11`.
This release keeps production model/runtime/topology policy unchanged while integrating
current task/translation campaign evidence and safer role-specific qualification tools.
Real-device task/translation campaign results were collected on installed `0.11.1-0.10`;
older operations/power evidence from `0.11.1-0.6` remains historical. Neither by itself
qualifies the unpublished `0.11.1-0.11` RPM.

| Area | Source/static | GitHub RPM | Real BC-250 | Current interpretation / next gate |
|---|---|---|---|---|
| repository/unit validation | SOURCE PASS — 82 focused packaging/documentation/catalog tests plus repository/RPM preflight and shell/Python syntax pass on the final reviewed 0.11 source; the long telemetry class still needs the normal full source gate | external | N/A | run the complete suite in the normal pre-publish/GitHub path; report exact checks |
| RPM build/install | preflight only | PENDING/EXTERNAL | PENDING for regenerated source | GitHub owns package build; do not emulate it locally |
| normal service topology | SOURCE PASS | external | HISTORICAL REAL DEVICE | re-check with `bc250-verify` after installing the unpublished 0.11 RPM before new hardware campaigns |
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
| whole-appliance revalidation v4 | SOURCE PASS | external | HISTORICAL/PARTIAL | use for milestone/release qualification, not after every small patch |
| task default: LFM2.5 1.2B | SOURCE PASS | external | HISTORICAL REAL DEVICE — latest campaign ran on 0.10 | promotion evidence remains 15/18 direct + 15/18 live + 9/9 overlap; Qwen3 4B is role-rejected after global OOM despite 5/6 quality |
| translation production LFM8B | SOURCE PASS | external | HISTORICAL REAL DEVICE — latest campaign ran on 0.10 | fresh 6/8 reproduces known weaknesses; retain only until a challenger completes Stage-2 + product-path qualification |
| translation challengers | SOURCE PASS | external | HISTORICAL REAL DEVICE — latest campaign ran on 0.10 | eight-case screen is saturated; next gate is Stage-2 hard corpus, then authenticated OWUI only for narrowed finalists |
| RAG direct quality | SOURCE PASS | external | HISTORICAL/PARTIAL | broaden absent-answer, multisource, table/invoice and multilingual cases |
| Open WebUI RAG path | SOURCE PASS | external | HISTORICAL/PARTIAL | qualify packaged settings before tuning; restore every mutation |
| embeddings | SOURCE PASS | external | HISTORICAL REAL DEVICE | Jina baseline; Qwen remains comparison; revisit only if RAG evidence justifies |
| standard/general office roles | SOURCE PASS | external | HISTORICAL REAL DEVICE | run current production use-case baseline before comparing main-lane challengers |
| large main-lane candidates | SOURCE PASS | external | PENDING full fit/performance | candidate matrix is resource/performance evidence, not semantic promotion |
| agent default Ornith | SOURCE PASS | external | HISTORICAL REAL DEVICE | 3/3 repeated static contract; broaden actual `bc250-code` workflows next |
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
