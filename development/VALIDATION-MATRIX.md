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

Current source baseline while this file was refreshed: `0.11.3-1.7`.
This source carries forward the greenfield `bc250-model` lifecycle, v4.2 revalidation, refined
installer/maintenance UX, deterministic RAG/Open WebUI qualification and hardened experimental MTP
lane. Release 1.6 closed the current MTP qualification/optimization evidence state without changing
MTP runtime defaults. Release 1.7 keeps that state and the 1.5 embedding-residency fix while
hardening operator boundaries: status topology classification, explicit secret-file permissions,
raw coding output, installer Open WebUI completion state and maintenance pagination/wording. Active
hardware focus remains support/maintenance qualification. The production
document/RAG role remains Gemma E4B / `bc250-office-documents` on the current 16 GiB profile; Qwen
9B remains a separate heavier general-office role. Whole-appliance hard thresholds, runtime
topology, model bytes, GGUF provenance/SHA policy, MTP model/runtime settings and CU/governor
policy are unchanged.

Newest full revalidation execution is exact installed
`bc250-llm-server-0.11.3-1.6.fc44.x86_64` from 2026-09-19. Guided install/core verification passed
54/0/0; v4.2 revalidation completed with infrastructure/restoration PASS and FULL coverage. Quality
was scored 7 pass / 1 quality-fail because `tags-en` returned relevant `Document Analysis` / `Text
Recognition` / `Multilingual Data` tags but the fixture did not recognize `Text Recognition` as an
OCR synonym. Current source corrects that narrow evaluator vocabulary gap without lowering the
relevance threshold. RAG passed 4/4 and Jina restoration succeeded, closing the earlier restoration
defect. GPT-OSS/Jina passed policy at 79.293 tok/s while reaching a tighter 156.266 MiB minimum
MemAvailable, 17.066 MiB swap peak delta and 72 C maximum temperature; 8662 -> 8320 prompt
truncation remained a non-severe diagnostic. See
`development/model-runs/2026-09-19-installed-0.11.3-1.6-revalidation.md`.

Exact 0.11.3-0.4 remains the newest all-green 8/8 quality run under its then-current fixtures. Older
exact-release evidence remains historical rather than being rewritten as current.

Newer **partial** installed-device evidence exists for exact
`bc250-llm-server-0.11.3-1.4.fc44.x86_64`. Its guided install and core verifier passed **54/0/0**;
IQ3_S Modelfile drift was reconciled from the verified source and IQ3_XXS downloaded/registered
successfully. Revalidation then stopped in `rag-quality`: semantic RAG acceptance was **4/4 PASS**,
but post-benchmark Jina residency restoration failed because the embedding fallback sent an empty
input that Ollama 0.34 rejects. Task had a separate 5/6 quality result (`tags-en: relevance`). This
is exact-1.4 installed evidence, not a complete revalidation pass. See
`development/model-runs/2026-09-19-installed-0.11.3-1.4-partial-revalidation.md`.

| Area | Source/static | GitHub RPM | Real BC-250 | Current interpretation / next gate |
|---|---|---|---|---|
| repository/unit validation | SOURCE PASS — full deterministic `make validate` completed for the current source: 413/413 tests PASS; Python compileall and packaged shell syntax also pass | PENDING/EXTERNAL | N/A | source validation is complete; RPM/SRPM and exact-source device qualification remain separate external gates |
| RPM build/install | source metadata targets 0.11.3-1.7; no RPM/SRPM build is claimed from this environment | PENDING/EXTERNAL | CURRENT-LINE DEVICE EVIDENCE — exact 1.6 guided install completed with verifier 54/0/0 and full revalidation execution | build/install exact 1.7 externally before claiming current-release hardware qualification |
| normal service topology | SOURCE PASS — runtime topology unchanged; `bc250-status` now reuses the agent-mode normal/degraded/stopped/agent classifier | external | HISTORICAL REAL DEVICE — exact 0.11.3-0.4 v4.2 revalidation/restoration PASS | verify again only after exact 1.4 installation; 1.4 does not intentionally alter topology |
| office HTTP readiness | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 Open WebUI reachable/drift none | power/support campaign remains separate |
| maintenance companion | SOURCE PASS | external | HISTORICAL/PARTIAL — companion intentionally unconfigured on 0.11.2-0.5 run | status/readiness first when power work resumes |
| WOL NIC configuration | SOURCE PASS | external | PENDING on current maintenance contract | inspect read-only first |
| real S5 Wake-on-LAN | N/A | N/A | PENDING | highest-value next power qualification, but do not mix with agent campaign |
| safe shutdown defer/allow | SOURCE PASS — conservative both-endpoint protected-TCP guard retained; message now describes actual policy | external | PENDING | test busy/defer then idle/allow only after S5 WOL succeeds |
| optional backup export | SOURCE PASS | external | PENDING | lower priority; no need to gate agent/source qualification |
| model lifecycle/reconciliation | SOURCE PASS — lifecycle semantics unchanged; 1.5 only suppresses redundant processed-count output when an entire required category is already current | external | PARTIAL CURRENT-LINE DEVICE EVIDENCE — exact 1.4 installer showed correct `[CURRENT]`/deferred/MTP separation and verifier 54/0/0, but still printed redundant `Done` lines | preserve semantics; confirm concise no-op output plus Open WebUI completion state on exact 1.7 installer rerun |
| storage transient-import behavior | N/A | N/A | HISTORICAL REAL DEVICE | preserve prior Ollama cleanup/dedupe lessons |
| XFS dedupe correctness | SOURCE PASS | external | HISTORICAL/PARTIAL | preserve GGUFs; batched implementation still deserves performance qualification |
| benchmark result contract | SOURCE PASS — deterministic scorer, structural completeness, fail-early OWUI preset resolution, residency-set restoration and resident-session MemAvailable/swap-peak-delta reporting are covered by source regressions | external | HISTORICAL REAL DEVICE — final RAG finalist campaign ran on exact installed 0.11.3-0.4; the newer scorer/lifecycle source is not itself device-qualified | preserve the final model-role decision, but re-run exact-source qualification only when a current-release hardware claim is needed |
| whole-appliance revalidation v4.2 | SOURCE PASS — non-empty embedding reload probe retained; task OCR vocabulary gap corrected without weakening thresholds | external | EXACT 1.6 — COMPLETED, infrastructure/restoration PASS, FULL coverage, quality 7 pass / 1 fixture relevance miss; RAG 4/4 and final health PASS | rerun on installed exact 1.7 for current-release qualification |
| task default: LFM2.5 1.2B | SOURCE PASS — strict single-object contract unchanged; OCR semantic group now accepts `text recognition` / `optical character recognition` | external | EXACT 1.6 produced 5/6 only because the valid `Text Recognition` tag missed the old literal OCR vocabulary; response was otherwise relevant strict JSON | rerun current fixture on exact 1.7; do not lower semantic-group threshold or retune the model from this evaluator gap |
| translation production Translate-Gemma | SOURCE PASS — production contract unchanged | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 direct 8/8 + OWUI 8/8 | no translation retuning required |
| RAG direct quality | SOURCE PASS — evaluator/restoration coverage retained; explicit `--token-file` now enforces the same private non-empty regular-file contract as other Open WebUI credentials | external | PARTIAL CURRENT-LINE DEVICE EVIDENCE — exact 1.4 RAG acceptance 4/4, followed by infrastructure failure during embedding residency restore; final 0.11.3-0.4 finalist campaign remains the broader completed quality evidence | Gemma remains production RAG default; do not hard-code manually adjudicated scores as fixture expectations |
| Open WebUI RAG path | SOURCE PASS — active preset/base-model resolution occurs before temporary KB/upload state and readiness is HTTP-based with a bounded slow-start allowance | external | HISTORICAL REAL DEVICE — final 0.11.3-0.4 RAG campaign: 36/36 short-path turns per finalist; Gemma 42/42 continuous-residency turns with ~2.7 GiB headroom, while Qwen reached the campaign 512 MiB safety floor after a few resident subruns | keep Gemma E4B / bc250-office-documents as the long-lived RAG default on 16 GiB; real arbitrary-document acceptance remains pending |
| embeddings | SOURCE PASS — embedding-only restore probe uses non-empty input | external | EXACT 1.6 — Jina qualification and post-RAG residency restoration PASS | preserve model/default; exact 1.7 revalidation remains the current-release gate |
| standard/general office roles | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 production use-case 5/5; one accepted office draft reached output budget | diagnostics remain visible; no acceptance change in 1.4 |
| large main-lane / deep-reasoning quality | SOURCE PASS for existing usecase/runtime machinery | external | EVIDENCE GAP — GPT-OSS is runtime-qualified but substantive semantic comparison against Qwen3.5 9B is still weak | run one bounded 12–16 case GPT-OSS vs Qwen9B office/deep-reasoning fixture before opening 27B/35B candidate work |
| agent default Ornith static benchmark | SOURCE PASS — reasoning leakage remains an explicit format failure | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 canonical agent 3/3 | keep Ornith baseline; static success is not product-path completion proof |
| `bc250-code` product route | SOURCE PASS — route/default/truncation/reasoning/outer-fence fail-closed and atomic-update contract asserted from source; no live helper execution | external | PENDING for current 0.11.3-1.7 | first bounded device check: final-content separation, terminal/length refusal, 3072 vs 6144 only on explicit truncation |
| new Qwen3.5 4B / Gemma E4B agent challengers | SOURCE PASS — Modelfiles discoverable/strict | external | PENDING | compare only after baseline product route is proven; no promotion claims yet |
| agent mode restoration | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 restoration PASS | 1.4 does not alter lane topology; rerun in exact-source qualification |
| OCR comparison | SOURCE PASS | external | HISTORICAL REAL DEVICE | GLM leads current small fidelity baseline; unchanged |
| MTP lifecycle/runner/catalog | SOURCE PASS — MTP remains standalone/non-selectable in normal convergence; installer shows read-only inventory; direct runs snapshot+drain Ollama and restore pre-run residency, while compare uses explicit drain-only isolation; effective draft depth remains verified | external llama.cpp | REAL DEVICE PERFORMANCE EVIDENCE exists for all four active candidates under specialist cold-residency isolation; new package direct-run restoration semantics are source-validated only | broad MTP qualification closed; device-check direct restoration opportunistically with exact 1.7, not a new campaign |
| MTP speedup/acceptance | SOURCE PASS — same GGUF/build/settings baseline-off vs MTP-on contract plus acceptance/resource/journal evidence; requested draft depth must match emitted server flags | N/A | REAL DEVICE EVIDENCE — corrected 1/2/3/4 sweep supports keeping depth 2 for Qwen3.6 and HauhauCS; Qwen3.5 depth 2 is the strongest exploratory candidate with a material advantage over packaged depth 3; YMQ passes at depth 2 with stronger long-form absolute throughput than HauhauCS but lower observed memory headroom | keep current defaults; confirm only Qwen3.5 depth 2 if a package-default change is desired |

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
