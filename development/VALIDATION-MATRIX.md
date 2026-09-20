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

Current source baseline while this file was refreshed: `0.11.3-2.1`.
Release 2.1 carries the 1.8 support/model-manager safety fixes forward and adds only bounded RAG evidence/schema and documentation cleanup on top of exact installed 1.7.
It preserves production roles, normal/agent topology, hard resource thresholds, MTP defaults and
GGUF provenance while fixing real-device support findings: safe-power endpoint parsing, the exact
restricted-companion SSH exception, non-blocking final power requests, and 40-CU rc handling when
persistent boot activation is intentionally disabled. It also hardens operator model overlays/CLI
guidance, protected-state/status wording, maintenance-policy/prune-size UX and reduces the existing
ISTA Qwen3.8 IQ3_XXS experiment from 16K to 8K without changing its verified source bytes.

Newest full revalidation execution is exact installed
`bc250-llm-server-0.11.3-1.7.fc44.x86_64` from 2026-09-20. Guided install/core verification passed
54/0/0 and Open WebUI baseline was APPLIED + VERIFIED. Revalidation completed with infrastructure
PASS, quality **8/8**, restoration PASS and FULL coverage. GPT-OSS/Jina passed policy at 167 MiB
minimum MemAvailable (>128 MiB hard floor, <512 MiB tight diagnostic); 8662 -> 8320 prompt truncation
remained a non-severe diagnostic. See
`development/model-runs/2026-09-20-installed-0.11.3-1.7-revalidation.md`.

A separate exact-1.7 support campaign then passed normal<->agent restoration, degraded detection and
recovery, verified local config/users backups and prune dry-run, but failed the interactive-SSH
safe-power defer test and exposed the healthy-40-CU rc=1 defect. Model unregister/re-apply blocks
were NOT RUN because their external wrapper used an unprivileged file test below protected `/var/lib`.
Real S5/WOL, Pi forced-command shutdown, backup restore and live pruning remain pending exact-2.1
device qualification. See
`development/model-runs/2026-09-20-installed-0.11.3-1.7-support-maintenance.md`.

| Area | Source/static | GitHub RPM | Real BC-250 | Current interpretation / next gate |
|---|---|---|---|---|
| repository/unit validation | SOURCE PASS — repository preflight PASS; existing deterministic suite 432/432 PASS; Python compileall PASS; bash syntax 64 shell/bootstrap entrypoints PASS. Ruff/ShellCheck were unavailable in this environment | PENDING/EXTERNAL | N/A | RPM/SRPM bundling/build tests intentionally skipped as requested; exact-source device qualification remains separate |
| RPM build/install | source metadata targets 0.11.3-2.1; RPM/SRPM bundling/build tests intentionally skipped for this code-focused release closure | PENDING/EXTERNAL | EXACT 1.7 — installed upgrade/core verify 54/0/0 and full revalidation PASS | build/install exact 2.1 externally before claiming current-release hardware qualification |
| normal service topology | SOURCE PASS — canonical normal/degraded/stopped/agent classifier retained; status version probing now follows an active lane | external | EXACT 1.7 — normal->agent->normal and deliberate degraded->normal recovery PASS, final verify clean | no topology retest is required solely for 2.1; include a short smoke only when installing for the still-unqualified 1.8 safety checks |
| office HTTP readiness | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 Open WebUI reachable/drift none | power/support campaign remains separate |
| maintenance companion | SOURCE PASS — forced-command identity preserves `SSH_CONNECTION` only for an exact internal companion request; second SSH remains protected | external | PENDING — exact 1.7 companion path was not exercised after safe-power failure | on exact 2.1 prove companion-only allow plus second-SSH defer before real idle poweroff |
| WOL NIC configuration | SOURCE PASS | external | PENDING on current maintenance contract | inspect read-only first |
| real S5 Wake-on-LAN | N/A | N/A | PENDING | run only after exact-2.1 SSH/companion guards and backup restore pass |
| safe shutdown defer/allow | SOURCE PASS — final-two-field endpoint parsing, exact companion tuple exemption, second-SSH guard and non-blocking power action covered behaviorally | external | EXACT 1.7 busy/defer FAIL — active local SSH was missed and poweroff began far enough to reset the session before cancellation | first exact-2.1 power gate: interactive SSH must defer with no broadcast/session loss; then companion/second-SSH; idle allow only afterward |
| optional backup export | SOURCE PASS | external | PENDING | lower priority; no need to gate agent/source qualification |
| model lifecycle/reconciliation | SOURCE PASS — explicit category/selection grammar clarified; malformed operator overlay filenames fail visibly; MTP still excluded from generic convergence | external | EXACT 1.7 installer showed required/optional/MTP separation; later unregister/re-apply support blocks were NOT RUN because the external wrapper lacked permission to stat protected GGUF paths | optional operator-lifecycle acceptance: if exercised, use privileged source existence/stat and unregister/apply only; it is not a 2.1 code-release gate |
| storage transient-import behavior | N/A | N/A | HISTORICAL REAL DEVICE | preserve prior Ollama cleanup/dedupe lessons |
| XFS dedupe correctness | SOURCE PASS | external | HISTORICAL/PARTIAL | preserve GGUFs; batched implementation still deserves performance qualification |
| benchmark result contract | SOURCE PASS — deterministic scorer, structural completeness, fail-early OWUI preset resolution, residency-set restoration and resident-session MemAvailable/swap-peak-delta reporting are covered by source regressions | external | HISTORICAL REAL DEVICE — final RAG finalist campaign ran on exact installed 0.11.3-0.4; the newer scorer/lifecycle source is not itself device-qualified | preserve the final model-role decision, but re-run exact-source qualification only when a current-release hardware claim is needed |
| whole-appliance revalidation v4.2 | SOURCE PASS — 1.7 evaluator/restoration fixes retained | external | EXACT 1.7 — COMPLETED, infrastructure PASS, quality 8/8, restoration PASS, FULL coverage, final health PASS | 2.1 carries the unqualified 1.8 support fixes; targeted SSH/40-CU checks come first, and full revalidation is optional unless a current whole-appliance qualification claim is needed |
| task default: LFM2.5 1.2B | SOURCE PASS — strict single-object contract and narrow OCR synonym correction retained | external | EXACT 1.7 — whole-appliance quality 8/8, closing the prior task false negative | no task retuning required |
| translation production Translate-Gemma | SOURCE PASS — production contract unchanged | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 direct 8/8 + OWUI 8/8 | no translation retuning required |
| RAG direct quality | SOURCE PASS — evaluator/restoration coverage retained; explicit `--token-file` now enforces the same private non-empty regular-file contract as other Open WebUI credentials | external | PARTIAL CURRENT-LINE DEVICE EVIDENCE — exact 1.4 RAG acceptance 4/4, followed by infrastructure failure during embedding residency restore; final 0.11.3-0.4 finalist campaign remains the broader completed quality evidence | Gemma remains production RAG default; supplied Qwen3.8 IQ3_XXS 16K follow-up was 5/5 early quality but memory-unsafe (~0.28 GiB before abort); do not hard-code manually adjudicated scores or reopen the model tournament |
| Open WebUI RAG path | SOURCE PASS — active preset/base-model resolution occurs before temporary KB/upload state and readiness is HTTP-based with a bounded slow-start allowance | external | HISTORICAL REAL DEVICE — final 0.11.3-0.4 RAG campaign: 36/36 short-path turns per finalist; Gemma 42/42 continuous-residency turns with ~2.7 GiB headroom, while Qwen reached the campaign 512 MiB safety floor after a few resident subruns | keep Gemma E4B / bc250-office-documents as the long-lived RAG default on 16 GiB; real arbitrary-document acceptance remains pending |
| embeddings | SOURCE PASS — embedding-only restore probe uses non-empty input | external | EXACT 1.7 — full revalidation restoration PASS | preserve model/default |
| standard/general office roles | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 production use-case 5/5; one accepted office draft reached output budget | diagnostics remain visible; no acceptance change in 1.4 |
| large main-lane / deep-reasoning quality | SOURCE PASS for existing usecase/runtime machinery | external | EVIDENCE GAP — GPT-OSS is runtime-qualified but substantive semantic comparison against Qwen3.5 9B is still weak | run one bounded 12–16 case GPT-OSS vs Qwen9B office/deep-reasoning fixture before opening 27B/35B candidate work |
| agent default Ornith static benchmark | SOURCE PASS — reasoning leakage remains an explicit format failure | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 canonical agent 3/3 | keep Ornith baseline; static success is not product-path completion proof |
| `bc250-code` product route | SOURCE PASS — route/default/truncation/reasoning/outer-fence fail-closed and atomic-update contract asserted from source | external | PENDING bounded direct product-route smoke | first live helper check remains separate from support/power work |
| new Qwen3.5 4B / Gemma E4B agent challengers | SOURCE PASS — Modelfiles discoverable/strict | external | PENDING | compare only after baseline product route is proven; no promotion claims yet |
| agent mode restoration | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 restoration PASS | 1.4 does not alter lane topology; rerun in exact-source qualification |
| OCR comparison | SOURCE PASS | external | HISTORICAL REAL DEVICE | GLM leads current small fidelity baseline; unchanged |
| MTP lifecycle/runner/catalog | SOURCE PASS — standalone/non-selectable inventory, direct snapshot/drain/restore and compare drain-only isolation retained | external llama.cpp | REAL DEVICE PERFORMANCE EVIDENCE exists for all four active candidates; direct post-1.7 restoration semantics remain source-validated only | broad MTP qualification stays closed; opportunistic smoke only after support work |
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
