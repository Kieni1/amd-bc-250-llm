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

Current source baseline while this file was refreshed: `0.12.1-0.6`. Historical rows below retain
the exact release labels of the evidence they describe. Current 0.6 preserves the qualified runtime
architecture and closes application-plane policy gaps: ordinary-user visibility is synchronized from
the actual normal main/task inventories, model-specific Qwen request policy is centralized in the
existing Open WebUI model authority, translation receives bounded modality/literal-integrity checks,
and status/revalidation/support evidence becomes more explicit. Production RAG/task/embedding choices,
normal/agent topology, hard resource thresholds and live 40-CU policy remain unchanged.

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
Exact 2.3 has now passed the targeted operations acceptance introduced through 2.3: clean RPM verification, swap 0750 convergence, topology/status/verifier UX, normal convergence, maintenance presentation, Tika restart semantics, baseline-aware identity restore, supported reboot reconstruction, live 40/40 and final authenticated 54/0/0. A separate exact-2.3 Open WebUI investigation passed HTTP/task/curated-role/translation/RAG behavior while identifying three desired-state ownership gaps now addressed in 2.4; the same investigation also recorded pinned-v0.11.3 OpenAI-style adapter limitations that 2.4 documents rather than vendor-patching. Exact 2.2 remains the source of earlier backup/config-restore, production/task runtime, service-restart and external-LAN evidence. Exact-2.3 installed inspection also found one remaining reachable `systemctl reboot` in the pinned CU live-manager CPU-unlock prompt; 2.4 patches that upstream path. Real S5/WOL, Pi forced-command shutdown and live pruning remain conditional device qualification. See
`development/model-runs/2026-09-20-installed-0.11.3-1.7-support-maintenance.md`,
`development/model-runs/2026-09-20-installed-0.11.3-2.2-operations-batches-04-06.md`, and
`development/model-runs/2026-09-20-installed-0.11.3-2.2-operations-batches-07-09.md`, and
`development/model-runs/2026-09-20-installed-0.11.3-2.3-operations-acceptance.md`, and
`development/model-runs/2026-09-20-installed-0.11.3-2.3-openwebui-investigation.md`.

| Area | Source/static | GitHub RPM | Real BC-250 | Current interpretation / next gate |
|---|---|---|---|---|
| repository/unit validation | SOURCE PASS — RPM preflight PASS, deterministic suite 473/473 PASS, bash -n 65/65; `development/` is excluded from both repository shell validation and unittest discovery | PENDING/EXTERNAL | EXACT 2.3 targeted operations acceptance PASS | 0.12.1-0.6 source is under pre-release review; RPM/SRPM build remains external |
| RPM build/install | source metadata targets 0.12.1-0.6; RPM/SRPM build remains an external package-build gate | PENDING/EXTERNAL | EXACT 2.3 — installed targeted operations acceptance PASS; exact 1.7 remains newest full whole-appliance revalidation | build/install exact 0.12.1-0.6, then run bounded changed-surface acceptance |
| normal service topology | SOURCE PASS — canonical normal/degraded/stopped/agent classifier retained; status version probing follows an active lane | external | EXACT 2.3 — normal/degraded/agent convergence UX accepted; final failed units 0 and verifier clean | preserve; next work is OWUI application behavior rather than topology replay |
| office HTTP readiness | SOURCE PASS — installer/verifier/revalidation/OWUI benchmarks distinguish HTTP/API readiness from mere service activity | external | EXACT 2.2 — Open WebUI/nginx recovered after restart and after supported reboot; Open WebUI service became active before HTTP readiness by ~20 s | preserve HTTP-based readiness; no new health framework required |
| Open WebUI product surface / desired state | SOURCE PASS — current 0.6 keeps Arena/local-offline policy and curated roles while intentionally exposing and synchronizing all discovered normal main/task models for pre-v1 ordinary-user comparison; 2.4's hidden-implementation state is historical evidence only; pinned-v0.11.3 adapter limitations remain documented rather than vendor-patched | external | EXACT 0.5 testing found provider-unrestricted state alone did not prove ordinary-user selector coverage; 0.6 closes that source gap and needs focused installed verification | install exact 0.6, compare ordinary-user selector with actual 11434/11435 inventories, verify 11436/11437 exclusion and harmless reconvergence |
| Tika restart semantics | SOURCE PASS — Quadlet accepts only expected SIGTERM exit 143 as successful; other abnormal exits remain failures | external | EXACT 2.3 — routine restart PASS; Result=success and no false failed-result telemetry | preserve; no further source change |
| external LAN isolation | SOURCE PASS — deterministic listener/firewall configuration retained | external | EXACT 2.2 — external Fedora host reached only intended SSH :22 / office HTTP :80; 3000/9998/11434-11437 filtered | preserve current firewalld boundary; source tests do not substitute for external network evidence |
| reboot persistence / invocation | SOURCE PASS — repository-native 40-CU paths use `/usr/sbin/reboot`; 2.4 also patches the pinned live-manager CPU-unlock interactive reboot path to `/usr/sbin/reboot` | external | EXACT 2.3 — supported `sudo reboot` reconstructed SSH/HTTP/topology/timers/firewall/40/40 and final 54/0/0; installed live manager still exposed one reachable `systemctl reboot` CPU-unlock prompt | do not reproduce known-bad invocation; verify built 2.4 live-manager path contains the patched command |
| maintenance companion | SOURCE PASS — forced-command identity preserves `SSH_CONNECTION` only for an exact internal companion request; second SSH remains protected | external | PENDING — exact 1.7 companion path was not exercised after safe-power failure | companion remains conditional; prove companion-only allow plus second-SSH defer before real idle poweroff if deploying it |
| WOL NIC configuration | SOURCE PASS | external | PENDING on current maintenance contract | inspect read-only first |
| real S5 Wake-on-LAN | N/A | N/A | PENDING | run only when unattended power is being enabled; active-admin-SSH defer is already proven on exact 2.2 |
| safe shutdown defer/allow | SOURCE PASS — final-two-field endpoint parsing, exact companion tuple exemption, second-SSH guard and non-blocking power action covered behaviorally | external | EXACT 2.2 — active administrator SSH defer PASS; exact 2.3 protected-endpoint defer remained healthy | companion/idle allow remain conditional follow-up; dedicated 2.3 SSH-message-only rerun is low priority |
| optional backup export | SOURCE PASS | external | PENDING | lower priority; no need to gate agent/source qualification |
| model lifecycle/reconciliation | SOURCE PASS — explicit category/selection grammar clarified; malformed operator overlay filenames fail visibly; MTP still excluded from generic convergence | external | EXACT 1.7 installer showed required/optional/MTP separation; later unregister/re-apply support blocks were NOT RUN because the external wrapper lacked permission to stat protected GGUF paths | optional operator-lifecycle acceptance: if exercised, use privileged source existence/stat and unregister/apply only; it is not a 2.2 code-release gate |
| storage transient-import behavior | N/A | N/A | HISTORICAL REAL DEVICE | preserve prior Ollama cleanup/dedupe lessons |
| XFS dedupe correctness | SOURCE PASS | external | HISTORICAL/PARTIAL | preserve GGUFs; batched implementation still deserves performance qualification |
| benchmark result contract | SOURCE PASS — deterministic scorer, structural completeness, fail-early OWUI preset resolution, residency-set restoration and resident-session MemAvailable/swap-peak-delta reporting are covered by source regressions | external | HISTORICAL REAL DEVICE — final RAG finalist campaign ran on exact installed 0.11.3-0.4; the newer scorer/lifecycle source is not itself device-qualified | preserve the final model-role decision, but re-run exact-source qualification only when a current-release hardware claim is needed |
| whole-appliance revalidation v4.5 | SOURCE PASS — current v4.5 harness retains the exact-1.7 evaluator/restoration fixes; exact 1.7 was qualified with v4.2 | external | EXACT 1.7 — COMPLETED, infrastructure PASS, quality 8/8, restoration PASS, FULL coverage, final health PASS; exact 2.3 has targeted operations acceptance | full revalidation remains optional unless a current whole-appliance qualification claim is needed |
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
