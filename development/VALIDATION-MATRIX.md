# BC-250 validation matrix

This file tracks **what kind of evidence exists** and what still needs qualification.
It is development memory, not an installed operator contract. Do not convert `historical`
into `current` merely because a past run was successful.

Status vocabulary:

- **SOURCE PASS** — source-side/unit/static validation exists for the current source.
- **SOURCE IN PROGRESS** — focused source checks exist, but the current source has not completed release/package closure.
- **HISTORICAL REAL DEVICE** — useful BC-250 evidence exists, but not necessarily from
  the current source release.
- **CURRENT REAL DEVICE PASS** — explicitly requalified on the installed current release.
- **PENDING** — no sufficient evidence yet.
- **N/A** — that validation class does not apply.

Current source baseline while this file was refreshed: `0.11.3-1.4`.
This source carries forward the greenfield `bc250-model` lifecycle, v4.2 revalidation, refined
installer/maintenance UX, deterministic RAG/Open WebUI qualification and hardened experimental MTP
lane. Release 1.4 records the completed RAG finalist decision, corrects RAG residency restoration
semantics so the starting model set is restored under each lane's normal keep-alive policy, and
renames the resident-session swap summary to the precise `swap_peak_delta_mib`. The production
document/RAG role remains Gemma E4B / `bc250-office-documents` on the current 16 GiB profile; Qwen
9B remains a separate heavier general-office role. Whole-appliance hard thresholds, runtime
topology, model bytes, GGUF provenance/SHA policy, MTP model/runtime settings and CU/governor
policy are unchanged.

Newest complete real-device evidence is exact installed
`bc250-llm-server-0.11.3-0.4.fc44.x86_64` from 2026-09-19. The refined installer completed
with the expected concise/current model UX and `bc250-verify` reported 54 ok / 0 warn / 0
fail. Revalidation v4.2 then completed in 13:56 with infrastructure/restoration PASS, full
coverage and **8 pass / 0 quality-fail / 0 skipped**. Task passed 6/6, translation 8/8,
direct RAG 4/4, production use cases 5/5, agent 3/3, Open WebUI translation 8/8 and Open
WebUI RAG 3/3. GPT-OSS/Jina passed policy while reaching 193.36 MiB minimum MemAvailable
and recording 8662 -> 8320 non-severe context truncation; `office-draft-e2b` passed semantic
acceptance with an `output-budget` diagnostic. Exact evidence is recorded in
`development/model-runs/2026-09-19-installed-0.11.3-0.4-revalidation.md`; bundle SHA-256 is
`8cdf52fb18336b711ecaf4b6118517bd13642a3f450aeba05b8ea0c3c5db7c5f`.
Older exact-release evidence remains historical rather than being rewritten as current.

| Area | Source/static | GitHub RPM | Real BC-250 | Current interpretation / next gate |
|---|---|---|---|---|
| repository/unit validation | SOURCE PASS — full deterministic `make validate` completed for the current source: 402/402 tests PASS; Python compileall and packaged shell syntax also pass | PENDING/EXTERNAL | N/A | source validation is complete; RPM/SRPM and exact-source device qualification remain separate external gates |
| RPM build/install | source metadata targets 0.11.3-1.4; no RPM/SRPM build is claimed from this environment | PENDING/EXTERNAL | HISTORICAL REAL DEVICE — exact refined 0.11.3-0.4.fc44 guided install completed with verifier 54/0/0 | build/install exact 1.4 externally before claiming current-release hardware qualification |
| normal service topology | SOURCE PASS — unchanged by 1.4 | external | HISTORICAL REAL DEVICE — exact 0.11.3-0.4 v4.2 revalidation/restoration PASS | verify again only after exact 1.4 installation; 1.4 does not intentionally alter topology |
| office HTTP readiness | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 Open WebUI reachable/drift none | power/support campaign remains separate |
| maintenance companion | SOURCE PASS | external | HISTORICAL/PARTIAL — companion intentionally unconfigured on 0.11.2-0.5 run | status/readiness first when power work resumes |
| WOL NIC configuration | SOURCE PASS | external | PENDING on current maintenance contract | inspect read-only first |
| real S5 Wake-on-LAN | N/A | N/A | PENDING | highest-value next power qualification, but do not mix with agent campaign |
| safe shutdown defer/allow | SOURCE PASS | external | PENDING | test busy/defer then idle/allow only after S5 WOL succeeds |
| optional backup export | SOURCE PASS | external | PENDING | lower priority; no need to gate agent/source qualification |
| model lifecycle/reconciliation | SOURCE PASS for carried-forward 0.4 behavior; 1.4 does not change lifecycle semantics | external | HISTORICAL REAL DEVICE — refined 0.11.3-0.4 installer showed concise `[CURRENT]` rows, deferred agent rows and MTP outside the generic picker; required models summarized as current | preserve this behavior while qualifying exact 1.4 |
| storage transient-import behavior | N/A | N/A | HISTORICAL REAL DEVICE | preserve prior Ollama cleanup/dedupe lessons |
| XFS dedupe correctness | SOURCE PASS | external | HISTORICAL/PARTIAL | preserve GGUFs; batched implementation still deserves performance qualification |
| benchmark result contract | SOURCE PASS — deterministic scorer, structural completeness, fail-early OWUI preset resolution, residency-set restoration and resident-session MemAvailable/swap-peak-delta reporting are covered by source regressions | external | HISTORICAL REAL DEVICE — final RAG finalist campaign ran on exact installed 0.11.3-0.4; the newer scorer/lifecycle source is not itself device-qualified | preserve the final model-role decision, but re-run exact-source qualification only when a current-release hardware claim is needed |
| whole-appliance revalidation v4.2 | SOURCE PASS — diagnostic visibility and existing hard policy are covered by source tests; no threshold change in 1.4 | external | HISTORICAL REAL DEVICE — exact 0.11.3-0.4 completed v4.2 infrastructure/restoration PASS, quality 8/8 and full coverage | rerun once on installed exact 1.4 for current-release appliance qualification |
| task default: LFM2.5 1.2B | SOURCE PASS — strict single-object contract unchanged in 1.2 | external | HISTORICAL REAL DEVICE — exact 0.11.3-0.4 task 6/6, including the previously failing `tags-de` case | retain evaluator/prompt unless new real evidence fails |
| translation production Translate-Gemma | SOURCE PASS — production contract unchanged | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 direct 8/8 + OWUI 8/8 | no translation retuning required |
| RAG direct quality | SOURCE PASS — boundary-aware deterministic evaluator, explicit alternatives/numeric values, language measurability, exact case completeness, residency-set restoration and session resources have source coverage | external | HISTORICAL REAL DEVICE — final 0.11.3-0.4 campaign: both finalists 96/96 target + all-support retrieval and 8/8 abstention; effective quality remained close after manual adjudication of known old-scorer false negatives | Gemma remains production RAG default; do not hard-code manually adjudicated scores as fixture expectations |
| Open WebUI RAG path | SOURCE PASS — active preset/base-model resolution occurs before temporary KB/upload state and readiness is HTTP-based with a bounded slow-start allowance | external | HISTORICAL REAL DEVICE — final 0.11.3-0.4 RAG campaign: 36/36 short-path turns per finalist; Gemma 42/42 continuous-residency turns with ~2.7 GiB headroom, while Qwen reached the campaign 512 MiB safety floor after a few resident subruns | keep Gemma E4B / bc250-office-documents as the long-lived RAG default on 16 GiB; real arbitrary-document acceptance remains pending |
| embeddings | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 embedding qualification PASS plus coexistence/concurrency PASS | Jina baseline unchanged |
| standard/general office roles | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 production use-case 5/5; one accepted office draft reached output budget | diagnostics remain visible; no acceptance change in 1.4 |
| large main-lane / deep-reasoning quality | SOURCE PASS for existing usecase/runtime machinery | external | EVIDENCE GAP — GPT-OSS is runtime-qualified but substantive semantic comparison against Qwen3.5 9B is still weak | run one bounded 12–16 case GPT-OSS vs Qwen9B office/deep-reasoning fixture before opening 27B/35B candidate work |
| agent default Ornith static benchmark | SOURCE PASS — reasoning leakage remains an explicit format failure | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 canonical agent 3/3 | keep Ornith baseline; static success is not product-path completion proof |
| `bc250-code` product route | SOURCE PASS — route/default/fail-closed/atomic-update contract asserted from source and shell syntax checked; no live helper execution | external | PENDING for current 0.11.3-1.4 | first bounded device check: final-content separation, terminal/length refusal, 3072 vs 6144 only on explicit truncation |
| new Qwen3.5 4B / Gemma E4B agent challengers | SOURCE PASS — Modelfiles discoverable/strict | external | PENDING | compare only after baseline product route is proven; no promotion claims yet |
| agent mode restoration | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 restoration PASS | 1.4 does not alter lane topology; rerun in exact-source qualification |
| OCR comparison | SOURCE PASS | external | HISTORICAL REAL DEVICE | GLM leads current small fidelity baseline; unchanged |
| MTP lifecycle/runner/catalog | SOURCE PASS — 0.4 exact-ID/provenance/preflight/privilege and generic-exclusion contracts are unchanged; later source additionally requires SID+PGID ownership proof before negative-PID process-group cleanup | external llama.cpp | PENDING runtime qualification | RAG selection is closed; run the separate bounded MTP campaign one candidate at a time without additional framework work |
| MTP speedup/acceptance | SOURCE PASS — comparison contract now uses the same GGUF/build/settings for baseline MTP-off versus MTP-on and captures acceptance/resource/journal evidence | N/A | PENDING | start with qwen3.5-9b-mtp, then retained qwen3.6-27b control; compare HauhauCS Qwen3.8 27B control against YMQ XS-TI challenger before 35B-A3B, one candidate at a time; speed alone is insufficient |

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
