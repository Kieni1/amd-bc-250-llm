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

Current source baseline while this file was refreshed: `0.11.3-2.3`.
Release 2.3 carries the settled 2.2 policy forward and applies a bounded operations/UX cleanup
forward, then encodes the completed MTP selection in the existing catalog without adding another
policy framework. Production Open WebUI roles, normal/agent topology, hard resource thresholds,
power policy and GGUF provenance are unchanged. MTP remains standalone/disabled/download-only; only
its active selection, role labels and qualified context/draft defaults change.

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
Exact 2.2 has now passed active-admin-SSH defer, healthy live 40/40 with persistent activation disabled, normal↔agent/degraded recovery, verified backup creation/retention, configuration restore, automatic identity rollback, non-translation production/task runtime qualification, individual/grouped service recovery, externally verified LAN isolation, successful appliance reconstruction through `sudo reboot`, and final authenticated 54/0/0 verification. Identity restore exposed a baseline-FK validation defect fixed in 2.3. Routine Tika restart exposed expected SIGTERM/143 being logged as a failed old instance, also fixed in 2.3. A separate `systemctl reboot` invocation is device-proven unreliable and package-controlled 2.3 reboot paths now use `/usr/sbin/reboot`; real S5/WOL, Pi forced-command shutdown and live pruning remain conditional device qualification. See
`development/model-runs/2026-09-20-installed-0.11.3-1.7-support-maintenance.md`,
`development/model-runs/2026-09-20-installed-0.11.3-2.2-operations-batches-04-06.md`, and
`development/model-runs/2026-09-20-installed-0.11.3-2.2-operations-batches-07-09.md`.

| Area | Source/static | GitHub RPM | Real BC-250 | Current interpretation / next gate |
|---|---|---|---|---|
| repository/unit validation | 2.3 closure: repository/RPM preflight PASS; complete deterministic suite **439/439 PASS** when run in split modules after the monolithic runner exceeded the execution window without reporting a failure; `bash -n` **64/64 PASS**; Python compileall PASS. Ruff/ShellCheck unavailable and not claimed. | PENDING/EXTERNAL | N/A | RPM/SRPM and exact-device qualification remain separate; do not turn the runner-duration issue into a product failure or weaken coverage |
| RPM build/install | source metadata targets 0.11.3-2.3; RPM/SRPM build remains an external package-build gate | PENDING/EXTERNAL | EXACT 1.7 — installed upgrade/core verify 54/0/0 and full revalidation PASS | build/install exact 2.3 before claiming current-release hardware qualification |
| normal service topology | SOURCE PASS — canonical normal/degraded/stopped/agent classifier retained; status version probing now follows an active lane | external | EXACT 2.2 — normal↔agent/degraded recovery plus individual/grouped Ollama service restarts PASS; final failed units 0 and verifier clean | retest only the 2.3 changed presentation/convergence surfaces |
| office HTTP readiness | SOURCE PASS — installer/verifier/revalidation/OWUI benchmarks distinguish HTTP/API readiness from mere service activity | external | EXACT 2.2 — Open WebUI/nginx recovered after restart and after supported reboot; Open WebUI service became active before HTTP readiness by ~20 s | preserve HTTP-based readiness; no new health framework required |
| Tika restart semantics | SOURCE PASS — Quadlet accepts only expected SIGTERM exit 143 as successful; other abnormal exits remain failures | external | EXACT 2.2 — routine restart recovered but old instance produced misleading exit-code failure telemetry | exact-2.3 one-restart acceptance should show recovery without false failed-result telemetry |
| external LAN isolation | SOURCE PASS — deterministic listener/firewall configuration retained | external | EXACT 2.2 — external Fedora host reached only intended SSH :22 / office HTTP :80; 3000/9998/11434-11437 filtered | preserve current firewalld boundary; source tests do not substitute for external network evidence |
| reboot persistence / invocation | SOURCE PASS — package-owned 40-CU reboot paths use `/usr/sbin/reboot`; no executable `systemctl reboot` remains | external | EXACT 2.2 — `sudo reboot` repeatedly reconstructed services/network/timers/firewall/40/40/54-0-0; `sudo systemctl reboot` can yield an unusable crash-recorded subsequent boot after substantial startup | do not reproduce known-bad invocation; one exact-2.3 supported reboot-path acceptance after install |
| maintenance companion | SOURCE PASS — forced-command identity preserves `SSH_CONNECTION` only for an exact internal companion request; second SSH remains protected | external | PENDING — exact 1.7 companion path was not exercised after safe-power failure | companion remains conditional; prove companion-only allow plus second-SSH defer before real idle poweroff if deploying it |
| WOL NIC configuration | SOURCE PASS | external | PENDING on current maintenance contract | inspect read-only first |
| real S5 Wake-on-LAN | N/A | N/A | PENDING | run only when unattended power is being enabled; active-admin-SSH defer is already proven on exact 2.2 |
| safe shutdown defer/allow | SOURCE PASS — final-two-field endpoint parsing, exact companion tuple exemption, second-SSH guard and non-blocking power action covered behaviorally | external | EXACT 2.2 — active administrator SSH defer PASS; session preserved and no shutdown initiated | 2.3 regression smoke: preserve active-SSH defer; companion/idle allow remain conditional follow-up |
| optional backup export | SOURCE PASS | external | PENDING | lower priority; no need to gate agent/source qualification |
| model lifecycle/reconciliation | SOURCE PASS — explicit category/selection grammar clarified; malformed operator overlay filenames fail visibly; MTP still excluded from generic convergence | external | EXACT 1.7 installer showed required/optional/MTP separation; later unregister/re-apply support blocks were NOT RUN because the external wrapper lacked permission to stat protected GGUF paths | optional operator-lifecycle acceptance: if exercised, use privileged source existence/stat and unregister/apply only; it is not a 2.2 code-release gate |
| storage transient-import behavior | N/A | N/A | HISTORICAL REAL DEVICE | preserve prior Ollama cleanup/dedupe lessons |
| XFS dedupe correctness | SOURCE PASS | external | HISTORICAL/PARTIAL | preserve GGUFs; batched implementation still deserves performance qualification |
| benchmark result contract | SOURCE PASS — deterministic scorer, structural completeness, fail-early OWUI preset resolution, residency-set restoration and resident-session MemAvailable/swap-peak-delta reporting are covered by source regressions | external | HISTORICAL REAL DEVICE — final RAG finalist campaign ran on exact installed 0.11.3-0.4; the newer scorer/lifecycle source is not itself device-qualified | preserve the final model-role decision, but re-run exact-source qualification only when a current-release hardware claim is needed |
| whole-appliance revalidation v4.2 | SOURCE PASS — 1.7 evaluator/restoration fixes retained | external | EXACT 1.7 — COMPLETED, infrastructure PASS, quality 8/8, restoration PASS, FULL coverage, final health PASS | 2.2 has bounded operations proof for SSH/40-CU/topology; 2.3 needs affected-boundary acceptance, while full revalidation remains optional unless a current whole-appliance qualification claim is needed |
| task default: LFM2.5 1.2B | SOURCE PASS — strict single-object contract and narrow OCR synonym correction retained | external | EXACT 1.7 — whole-appliance quality 8/8, closing the prior task false negative | no task retuning required |
| translation production Translate-Gemma | SOURCE PASS — production contract unchanged | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 direct 8/8 + OWUI 8/8 | no translation retuning required |
| RAG direct quality | SOURCE PASS — corrected deterministic scorer/restoration coverage retained; Open WebUI token files use the private non-empty regular-file contract | external | HISTORICAL REAL DEVICE — corrected finalist conclusion: Gemma 94/96 overall vs Qwen 93/96 with both 36/36 on short OWUI RAG; Qwen3.8 IQ3_XXS 16K was only 5/5 partial before memory abort | Gemma remains production RAG default; do not compare the partial 27B run to the full finalist corpus or reopen the tournament without a new product reason |
| Open WebUI RAG path | SOURCE PASS — active preset/base-model resolution occurs before temporary KB/upload state and readiness is HTTP-based with a bounded slow-start allowance | external | HISTORICAL REAL DEVICE — final 0.11.3-0.4 RAG campaign: 36/36 short-path turns per finalist; Gemma 42/42 continuous-residency turns with ~2.7 GiB headroom, while Qwen reached the campaign 512 MiB safety floor after a few resident subruns | keep Gemma E4B / bc250-office-documents as the long-lived RAG default on 16 GiB; real arbitrary-document acceptance remains pending |
| embeddings | SOURCE PASS — embedding-only restore probe uses non-empty input | external | EXACT 1.7 — full revalidation restoration PASS | preserve model/default |
| standard/general office roles | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 production use-case 5/5; one accepted office draft reached output budget | diagnostics remain visible; no acceptance change in 1.4 |
| large main-lane / deep-reasoning quality | SOURCE PASS for existing usecase/runtime machinery | external | EVIDENCE GAP — GPT-OSS is runtime-qualified but substantive semantic comparison against Qwen3.5 9B is still weak | run one bounded 12–16 case GPT-OSS vs Qwen9B office/deep-reasoning fixture before opening 27B/35B candidate work |
| agent default Ornith static benchmark | SOURCE PASS — reasoning leakage remains an explicit format failure | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 canonical agent 3/3 | keep Ornith baseline; static success is not product-path completion proof |
| `bc250-code` product route | SOURCE PASS — route/default/truncation/reasoning/outer-fence fail-closed and atomic-update contract asserted from source | external | PENDING bounded direct product-route smoke | first live helper check remains separate from support/power work |
| new Qwen3.5 4B / Gemma E4B agent challengers | SOURCE PASS — Modelfiles discoverable/strict | external | PENDING | compare only after baseline product route is proven; no promotion claims yet |
| agent mode restoration | SOURCE PASS | external | HISTORICAL REAL DEVICE — 0.11.3-0.4 restoration PASS | 1.4 does not alter lane topology; rerun in exact-source qualification |
| OCR comparison | SOURCE PASS | external | HISTORICAL REAL DEVICE | GLM leads current small fidelity baseline; unchanged |
| MTP lifecycle/runner/catalog | SOURCE PASS — standalone/non-selectable inventory, direct snapshot/drain/restore, compare drain-only isolation and catalog policy metadata retained | external llama.cpp | HISTORICAL REAL DEVICE — all three active choices have qualifying evidence; Qwen3.6 27B also passed historically but is now superseded; 35B-A3B remains a fit failure | broad MTP qualification stays closed; exact-source direct smoke is optional rather than a release gate |
| MTP speedup/acceptance | SOURCE PASS — active catalog pins Qwen3.5 16K/d2, YMQ 8K/d1 and HauhauCS 8K/d2; list output exposes primary/alternative role metadata without enabling models | N/A | HISTORICAL REAL DEVICE — Qwen3.5 d2 confirmation and YMQ d1 optimization support the final package selection; HauhauCS retains the specialist niche | no further broad campaign; symmetric YMQ d1 repeats are optional only if future policy requires them |

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
