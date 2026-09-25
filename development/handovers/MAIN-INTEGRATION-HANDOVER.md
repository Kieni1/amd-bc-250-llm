# AMD BC-250 LLM appliance — main integration handover

## Purpose and authority

This is the durable state transfer for a fresh **main integration** chat. It should contain the
current appliance contract, durable constraints, current evidence, important negative results and
open work. Release-by-release chronology belongs in `docs/CHANGELOG.md`; detailed rationale belongs
in `development/DECISIONS.md`; exact campaign evidence belongs in `development/model-runs/`.

When information disagrees, use this order:

1. current user instruction;
2. newest supplied source/package;
3. real-device evidence from the exact installed revision;
4. validation evidence for that revision;
5. current decisions/handovers;
6. older logs, chats, handovers and patches.

Do not relabel evidence from one NVR as qualification of another NVR.

---

# 1. Current release and evidence state

Current source release:

```text
VERSION       0.12.1
RPM Release   0.6%{?dist}
NVR           bc250-llm-server-0.12.1-0.6
```

`0.12.1-0.6` is the current source release target. It preserves the qualified 0.5 runtime/hardware architecture (Ollama 0.34.2, Open WebUI 0.11.3, Jina, Deep `keep_alive=0`, TTM 4194304/4194304 and the proven live 40-CU path) and closes application-plane policy gaps exposed by 0.5 testing: ordinary-user visibility is synchronized from the actual normal main/task inventories, DE↔FR output receives bounded modality/literal-integrity protection, qualified Qwen request policy is centralized in the existing Open WebUI model authority, and status/revalidation/support evidence is clearer. It deliberately does not repack Qwen templates, add a memory scheduler, or productize the two-host model-only profile.

Exact installed `0.12.1-0.4.fc44.x86_64` reached package convergence, authenticated verifier 54/0, healthy normal topology, Ollama 0.34.2, current Fedora kernel operation, packaged revalidation infrastructure/quality/restoration PASS and the first bounded RAG filesystem/security gate. Device testing then found two source blockers: the RAG agent path consumed native reasoning as document text and could falsely satisfy fidelity checks, while `bc250-revalidate status --raw` discarded its option. Those findings block 0.4 release acceptance but do not invalidate its broad runtime/model evidence. 0.5 therefore needs focused RAG-preparation/CLI/UX acceptance rather than replaying the completed broad model campaign. Exact-installed 2.4 remains historical broad operations evidence only.

The consolidated exact-2.3 Open WebUI investigation also isolated three pinned-v0.11.3
OpenAI-style adapter limitations: root `max_tokens` is not a reliable Ollama cap, reasoning-token
usage can report zero despite reasoning content, and length termination can surface as
`finish_reason=stop`. 2.4 documents that boundary and keeps package-owned hard caps on nested
`options.num_predict`; it does not vendor-patch Open WebUI for an external API contract the appliance
does not currently advertise.

The release incorporates defects found during exact installed `0.11.3-1.7` support testing:

- safe-power now inspects the final two `ss` endpoint fields, so local SSH/UI/Ollama activity is not
  missed by a fixed-column parser;
- public `request-shutdown` has no bypass and must defer on its own interactive SSH session;
- the dedicated Pi forced-command path may exempt only its exact authenticated `SSH_CONNECTION`
  tuple; any other protected TCP connection still defers;
- the final `poweroff`/`suspend` request is non-blocking after all guards pass;
- healthy live 40/40 CU operation returns success even when persistent boot activation is
  intentionally disabled;
- model-manager legacy guidance now points to `sudo bc250-model apply all all`, while omitted
  destructive selection still never means all;
- visible non-`.Modelfile` files in the operator overlay fail clearly instead of disappearing from
  discovery;
- unprivileged status reports protected state as protected/unavailable rather than zero or absent;
- normal agent inactivity and maintenance configuration are described without misleading alarm;
- upload-prune output uses useful B/KiB/MiB/GiB sizes while policy calculations remain byte-precise;
- installer MTP inventory is read-only/non-indexed with explicit fetched-state wording;
- `exp-qwen38-27b-ista-gsq-rco-iq3-xxs` is bounded to 8K context after sustained 16K operation
  reached the low-memory boundary. It keeps the same model identity and verified GGUF, so applying
  the new definition does not require a source re-download.

Exact installed `0.11.3-2.4.fc44.x86_64` is now the latest broad operations baseline. Operator-supplied
acceptance through Batch 20 closed non-OWUI operations with clean package integrity, bounded storage/
residue state, normal topology, live 40/40 routing and successful complete reconstruction after a
supported `sudo reboot`. The separate final Open WebUI investigation also proved the ordinary-user
ACL and Deep Reasoning memory defects and their narrow temporary mitigations on exact 2.4. Those
results motivate 0.12.1-0.1 but do not qualify the new NVR.

Current 0.12.1-0.6 evidence boundary:

```text
release metadata               0.12.1-0.6
exact-installed 0.4 runtime    PASS for broad model/revalidation/device health
0.5 deterministic source gate  PASS (471/471 in testing handoff)
0.5 device findings            model-selector ACL/surface gap + translation modality drift; compare resource behavior safe in tested cases
0.6 focused source checks      main-integration light gate only; authoritative full build remains external
GitHub full source/build gate   pending
exact-0.12.1-0.6 focused gate  pending
```

Exact installed `0.11.3-2.3.fc44.x86_64` targeted operations acceptance has now demonstrated:

```text
rpm -V after convergence           PASS / clean
swap runtime directory             root:root 0750
status/verifier/recovery UX        PASS
bc250-agent-mode normal            PASS / idempotent
DRY_RUN/timer presentation         PASS
Tika routine restart               PASS / no false failed result
identity restore                   PASS with baseline FK=142, new FK=0
supported sudo reboot              PASS / appliance reconstructed
live CU routing                    40/40 healthy
failed units                       0
final authenticated bc250-verify   54 ok / 0 warn / 0 fail
```

One remaining installed-package source issue was found: the pinned upstream CU live manager still
had a reachable interactive CPU-core-unlock branch that called `systemctl reboot`. 2.4 patches only
that upstream call through the existing RPM-prep patch. The known-bad invocation should not be
deliberately reproduced.

Exact installed `0.11.3-2.2.fc44.x86_64` operations testing has now demonstrated:

```text
bc250-install convergence          PASS
live CU routing                    40/40 healthy
persistent 40-CU boot activation   intentionally disabled
active administrator SSH shutdown  DEFER PASS; session preserved
normal -> agent -> normal           PASS
deliberate degraded topology       detected; recovery PASS
config/users backups + retention   PASS
configuration restore              PASS
automatic identity rollback        PASS
production use-case suite          4/4 PASS
task suite                         6/6 PASS
bounded generation-edge infra      17/17 PASS
individual/grouped service restart  PASS; failed units 0 after recovery
external LAN isolation              PASS; internal app ports filtered externally
reboot via sudo reboot              PASS; services/timers/firewall/40-CU reconstructed
systemctl reboot path               DEVICE DEFECT; later boot became unusable after substantial startup
final authenticated bc250-verify   54 ok / 0 warn / 0 fail
```

Identity restore itself exposed one validation defect rather than a rollback defect: the real DB
already contained unrelated `foreign_key_check` rows while passing `integrity_check`, and the old
validator rejected those unchanged baseline rows. The 2.3 release now compares canonical pre/post FK
sets and fails only on newly introduced violations while keeping strict integrity checking. Its
operator output now reports strict integrity, baseline/new FK counts and explicit rollback success
without dumping unrelated baseline rows.

This is strong operations evidence for 2.2, but it is not a full 2.2 whole-appliance revalidation.

Newest full whole-appliance hardware evidence is exact installed
`bc250-llm-server-0.11.3-1.7.fc44.x86_64`:

```text
installer/core verify     54 OK / 0 warn / 0 fail
revalidation              infrastructure PASS
quality                   8/8 PASS
restoration               PASS
coverage                  FULL
Open WebUI desired state  unchanged / PASS
```

The GPT-OSS/Jina edge case passed policy with minimum MemAvailable **167 MiB**, below the 512 MiB
tight-headroom diagnostic but above the unchanged 128 MiB hard floor. A prompt diagnostic observed
`8662 -> 8320` tokens; this is not evidence of clean 16K real-prompt execution. See
`development/model-runs/2026-09-20-installed-0.11.3-1.7-revalidation.md`.

Exact-1.7 support/maintenance evidence additionally proved normal↔agent restoration, degraded-mode
detection/recovery, verified local config/users backups and upload-prune dry-run. It exposed the
safe-power and 40-CU return-code defects fixed in 1.8. Exact 2.2 has since proven those two
boundaries plus backup retention, configuration restore, identity rollback and bounded production/task
runtime health. Real idle S5/WOL, Pi forced-command shutdown and live pruning remain conditional
follow-up work. See `development/model-runs/2026-09-20-installed-0.11.3-1.7-support-maintenance.md`
and the exact-2.2 operations records:
`development/model-runs/2026-09-20-installed-0.11.3-2.2-operations-batches-04-06.md` and
`development/model-runs/2026-09-20-installed-0.11.3-2.2-operations-batches-07-09.md`, plus exact-2.3 targeted acceptance in
`development/model-runs/2026-09-20-installed-0.11.3-2.3-operations-acceptance.md` and
`development/model-runs/2026-09-20-installed-0.11.3-2.3-openwebui-investigation.md`, plus final exact-2.4 operator-supplied acceptance in
`development/model-runs/2026-09-21-installed-0.11.3-2.4-operations-batches-19-20.md` and
`development/model-runs/2026-09-21-installed-0.11.3-2.4-openwebui-final.md`.

**Immediate evidence boundary:** exact installed 2.4 remains the historical broad non-OWUI operations baseline and source of the final OWUI defect/mitigation evidence; exact 1.7 remains the historical full whole-appliance revalidation campaign. Exact installed 0.12.1-0.4 now adds broad current-runtime evidence (Ollama 0.34.2, verifier-clean normal topology and packaged revalidation PASS) but is release-blocked by the RAG preparation and raw-status source defects. Current 0.12.1-0.6 must pass focused policy/observability acceptance before promotion.

---

# 2. Product intent and engineering priorities

The appliance is a private local office LLM appliance for one active user at a time:

```text
reliable office chat / documents / translation / RAG
safe multi-lane resource use on ~16 GiB shared memory
good interactive latency
controlled electricity saving through shutdown + WOL
repeatable package-owned configuration and recovery
```

Priority order:

1. data integrity, safe shutdown, recovery and fail-closed destructive operations;
2. availability and correct state restoration;
3. runtime/model correctness and memory safety on 16 GiB UMA;
4. real product-path correctness through Open WebUI;
5. operator UX and diagnostics;
6. maintainability/documentation;
7. optional experiments and convenience.

The project is pre-v1.0. Prefer a clean current contract over compatibility with obsolete
development interfaces unless the current source intentionally keeps compatibility.

---

# 3. Development and validation rules

Detailed workflow: `development/handovers/DEVELOPMENT-WORKFLOW.md`.

Ownership:

```text
GitHub       RPM/SRPM/package builds
workstation  Ruff/developer linting configured by the user
BC-250       hardware, services, Ollama/models, Open WebUI, power/WOL and qualification
```

Rules that must survive every new chat:

- state exactly what ran and what did not;
- never claim device qualification from a generic development environment;
- never weaken evaluators, verifier thresholds, restoration, evidence integrity or secret hygiene to
  obtain green output;
- keep model-quality defects, evaluator defects, integration defects and operator/environment state
  separate;
- work one bounded hardware evidence batch at a time and restore state before changing lanes;
- preserve verified GGUFs where practical; prefer re-registration, validated-source reuse and XFS
  dedupe over deletion/redownload;
- destructive omission never means all;
- ambiguous backend/remote state must fail closed before local destruction;
- main integration owns versioning, cross-stream policy and promotion decisions; specialist chats
  return evidence rather than silently changing production policy.

---

# 4. Durable BC-250 hardware facts

## Board / CPU / GPU

```text
CPU family          Zen 2 / Oberon-derived
normal CPU exposure 6 cores / 12 threads
GPU                 Cyan Skillfish / gfx1013
stock presentation  ~24 CUs / 12 WGPs
physical GPU        up to 40 CUs / 20 WGPs
physical memory     16 GB GDDR6 shared by CPU and GPU
```

The appliance does not depend on an 8-core CPU unlock. Treat CPU unlock as a separate hardware
experiment.

Do not describe the GPU as a normal desktop RDNA2 card when architecture precision matters. Use
Cyan Skillfish / gfx1013, console-derived GFX10-family hardware with additional RDNA2-class features.

## Unified memory

The board has one physical 16 GB GDDR6 pool. Do not add system RAM + VRAM + GTT + Vulkan heaps as if
they were independent physical capacities. Model fit is governed by the shared pool after kernel,
userspace, services, weights, runtime overhead and KV/cache allocations.

Current package memory policy on the qualified platform includes:

```text
TTM pages_limit/page_pool_size  4194304 (~16 GiB capacity view)
zram                           2 GiB, priority 100
disk swap                      16 GiB, priority 10
vm.swappiness                  60
hard MemAvailable floor        128 MiB
tight-headroom diagnostic      512 MiB
```

The 512 MiB value is diagnostic, not a hard package abort threshold. Do not raise the 128 MiB hard
floor merely to make a tight model pass.

## CU / governor / thermal policy

Real device evidence has shown a healthy **40/40 live routing table** while kernel/RADV numeric
counters may still report 24. Judge live routing from the package table and investigate `D!`/off
cells rather than demanding one universal CU number from every diagnostic layer.

Live 40-CU routing is operator-controlled. Do not automatically enable persistent 40-CU boot
activation merely because live routing is healthy.

Current production governor policy is approximately:

```text
350–1850 MHz
thermal throttle target 85 C
```

Do not import >2 GHz community settings without dedicated stability/thermal evidence.

---

# 5. Runtime and service topology

Normal appliance topology:

```text
11434  ollama.service            main / product lane
11435  ollama-task.service       task lane
11437  ollama-embedding.service  embedding lane
11436  ollama-agent.service      exclusive agent lane; intentionally inactive in normal mode

3000   Open WebUI internal
80     nginx office-facing HTTP/readiness path
Tika   private document extraction service
```

Normal mode means main/task/embedding active and agent inactive. Agent mode is exclusive: 11436
active, normal Ollama lanes inactive. `bc250-agent-mode` is the single topology classifier:

```text
normal
agent
degraded
stopped
```

Read-only status must not switch agent mode merely to inspect agent registration.

Current Ollama lane policy is one loaded model and one parallel request per lane. Main is the
interactive lane and should remain warm enough for usable office UX; task/embedding are separate so
background work can coexist without serializing all product traffic.

Runtime pins are authoritative in `config/runtime.env`. Current release uses:

```text
Ollama       0.34.2
Open WebUI   0.11.3
Tika         4.0.0-full
```

Open WebUI desired state is package-owned. A meaningful authenticated status compares providers,
task/embedding/RAG settings, persisted local/offline application policy, upload limits/extensions,
package Function source/metadata/activation, model-role mappings/filter attachments, model visibility
and built-in-tool/capability policy. Arena is package-owned OFF. During pre-v1 testing the main and task
providers are intentionally unrestricted and all models actually installed on 11434/11435 are selectable;
package-owned raw production/task overrides are visible and labelled for comparison. Curated
`bc250-office-*` roles remain the product contracts. Embedding 11437 and exclusive agent 11436 remain
outside the normal chat selector. `Desired-state drift: none` is intended to be substantive, not cosmetic;
unrelated operator-owned models/users/prompts/knowledge remain additive and untouched.

---

# 6. Current production model map

Canonical model inventory is `MODELS.md` plus the package catalogs.

| Role | Current model |
|---|---|
| standard office | `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` |
| document/RAG answer | `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` |
| DE↔FR translation | `prod-translate-gemma4-sub-e4b-17s-q4-k-xl` |
| higher-quality office | `prod-qwen35-9b-unsloth-q6-k` |
| deep reasoning / memory-edge reference | `prod-gpt-oss20b-ggml-org-mxfp4` |
| embeddings | `embed-jina-v5-small-retrieval-q4-k-m` |
| compact task | `task-lfm25-1.2b-instruct-liquidai-q6-k` |
| exclusive agent baseline | `agentic-ornith15-9b-ornith-q5-k-m` |

Translation Open WebUI roles:

```text
bc250-office-translation-de-fr -> prod-translate-gemma4-sub-e4b-17s-q4-k-xl
bc250-office-translation-fr-de -> prod-translate-gemma4-sub-e4b-17s-q4-k-xl
```

Current tool/prompt ownership during testing:

- Standard, Advanced and Deep use general model knowledge by default; package-owned metadata disables autonomous built-in Open WebUI knowledge/chat/search tools.
- Documents is the dedicated retrieval role and keeps package-owned knowledge retrieval enabled while unrelated built-ins remain disabled.
- Translation keeps built-in tools disabled; the OWUI direction wrapper owns translation direction and preserves legal/contractual modality.
- Raw main/task models are visible for comparison, not promoted as stable product roles. Raw GPT-OSS keeps `keep_alive=0` for BC-250 memory safety.

Do not revive graveyard models because old logs or handovers mention them.

## Durable role rationale

- **Gemma E2B:** lightweight/high-throughput normal office role.
- **Gemma E4B:** current production document/RAG answer model. Direct and authenticated Open WebUI
  RAG were strong; the decisive advantage over Qwen 9B was sustained-residency memory margin, not a
  claim that Qwen quality was poor.
- **Translate-Gemma E4B:** production DE↔FR translator with explicit direction roles. Broad translator
  discovery is closed unless integrated evidence demonstrates a model-level failure.
- **Qwen3.5 9B:** responsive higher-quality office option; retained despite not being the long-lived
  RAG default.
- **GPT-OSS 20B:** deep-reasoning/reference model and worst credible production memory case. It is a
  required coexistence edge for task/embedding safety.
- **LFM2.5 1.2B task:** promoted because it has materially stronger task quality than the retired
  Gemma 3 1B while successfully coexisting with warm GPT-OSS.
- **Jina v5 small retrieval:** production embedding baseline; Qwen3 embedding remains a valid future
  comparator only if a concrete RAG/licensing question requires it.
- **Ornith 9B agent:** current baseline. Product-path claims must include actual `bc250-code` behavior,
  not only the canonical 3-case benchmark.

## Durable negative model results

Keep these visible because they constrain current topology:

- `exp-qwen38-4b-distill-empero-q6-k` improved isolated task quality but simultaneous residence with
  warm GPT-OSS caused severe memory pressure and task-service OOM; do not retest it for the same
  background-task role under the same memory envelope.
- `exp-qwen3-4b-lmstudio-q6-k` had promising isolated task quality, but both exact-source staging and
  a bounded task alias caused global OOM and killed warm GPT-OSS/other services; do not repeat the
  same coexistence experiment without a material topology/resource change.
- large 27B/35B office candidates can be useful quality/reference experiments but must not be
  promoted from isolated quality or load success alone on this 16 GiB UMA platform.

Detailed model decisions and retired catalogs belong in `MODELS.md` and `development/DECISIONS.md`.

---

# 7. Current experimental / MTP state

## Main-model experiments

The current ISTA Qwen3.8 pair is intentionally role-split:

```text
exp-qwen38-27b-ista-gsq-rco-iq3-xxs  deployability/RAG-oriented, 8K, caller think=false
exp-qwen38-27b-ista-gsq-rco-iq3-s    quality-first main experiment, 8K, caller think=true
```

The XXS 8K change in 1.8 is a Modelfile/runtime-definition change only. Preserve and reuse the
existing verified GGUF.

The full active/retired experiment inventory is canonical in `MODELS.md`; do not duplicate it into
new handovers.

## MTP / speculative decoding

MTP is a **standalone opt-in external llama.cpp runtime**, not another always-on Ollama lane.
It shares catalog/provenance management but not normal appliance convergence.

Current active MTP package policy:

```text
qwen3.5-9b-mtp                 primary fast,        ctx 16384 / draft 2
qwen3.8-27b-ymq-xs-ti-mtp      primary general 27B, ctx 8192  / draft 1
qwen3.8-27b-hauhaucs-mtp       specialist alternative, ctx 8192 / draft 2
```

`qwen3.6-27b-mtp` is retired from active discovery as superseded but retains positive historical
qualification in source-only `graveyard.toml`. `qwen3.6-35b-a3b-mtp` remains retired for the stock
8K/full-GPU memory-fit failure. Use exact IDs for 27B MTP models; ambiguous 27B aliases are removed.

Current workflow:

```text
bc250-model list/status/path mtp
sudo bc250-fetch-mtp MODEL_ID        explicit preparation only
bc250-run-mtp                         direct operator use
bc250-compare-mtp                     specialist comparison/qualification
```

Installer Stage 7 may show MTP state but never assigns normal selection indexes or fetches MTP.
Generic `apply all` / `refresh all` does not acquire MTP.

Residency policy:

- direct `bc250-run-mtp`: snapshot reachable Ollama residency → drain → run exact llama.cpp child →
  restore the captured set; restoration failure must influence final success;
- `bc250-compare-mtp`: drain-only specialist isolation and intentionally leave Ollama cold afterward.

Broad MTP qualification is closed. The symmetric three-repeat YMQ depth-1 confirmation remains
optional evidence only; do not reopen the campaign without a materially new product/runtime/hardware
question.

---

# 8. Model lifecycle and storage contract

Current public model-manager grammar:

```text
bc250-model list [CATEGORY]
sudo bc250-model status [CATEGORY] [SELECTION] [--online]
bc250-model path CATEGORY ID
sudo bc250-model apply CATEGORY [SELECTION]
sudo bc250-model refresh CATEGORY [SELECTION]
sudo bc250-model unregister CATEGORY [SELECTION]
sudo bc250-model remove CATEGORY [SELECTION]
sudo bc250-model purge-retired
```

Categories:

```text
production  experiments  task  agentic  embedding  mtp  all
```

Important semantics:

- category `all` means combined catalog, not select-everything;
- `sudo bc250-model apply all all` is the explicit “apply every eligible normal model” form;
- omitted destructive selection never means all;
- `unregister` removes registration while retaining GGUF/state;
- `remove` is source-destructive and must be explicit;
- `refresh` deliberately re-fetches; do not use it in support testing when validated source reuse is
  the goal;
- verified source/provenance mismatch blocks unsafe reuse;
- backend ambiguity must not trigger local deletion;
- MTP remains outside generic Ollama convergence;
- `/etc/bc250-llm-server/models.d/` is an operator overlay. Visible regular definitions must end in
  `.Modelfile`; packaged definitions live under the installed share tree;
- operator metadata should use canonical category `experiments`; singular historical `experimental`
  remains readable where intentionally supported.

Storage policy:

- preserve verified GGUFs for offline/local rebuilds;
- Ollama may temporarily amplify storage during imports and later remove unreferenced blobs on normal
  lifecycle events; do not manually delete blobs solely because onboarding looks large;
- for byte-identical retained GGUF/live Ollama blobs on XFS, prefer package dedupe over deleting
  retained sources;
- arbitrary out-of-band same-name Ollama registration mutation is not fully proven/detected when
  source/template state is unchanged; do not claim complete live-manifest drift detection.

---

# 9. RAG / Open WebUI product contract

Production RAG role:

```text
preset/model role   bc250-office-documents
answer model        prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl
embedding model     embed-jina-v5-small-retrieval-q4-k-m
embedding lane      11437
source documents    /srv/bc250-documents
```

Durable RAG architecture:

```text
operator-owned authoritative documents
        ↓
metadata/provenance validation
        ↓
language/authority separation
        ↓
Open WebUI Knowledge sync
        ↓
package-owned RAG role + embedding lane
```

The importer fails closed on escaping/symlinked sources and hash mismatches, uploads replacements
before deleting stale remote content, and requires explicit prune for remote deletion. Token files
must be regular, readable, non-empty and not group/world accessible.

Current product conclusion: Gemma E4B is the RAG default for the 16 GiB appliance because it retained
substantially more sustained-residency headroom than Qwen 9B while both were functionally strong.
Do not restart a Gemma-vs-Qwen tournament without a new product question.

The next RAG evidence is **real-office-document acceptance**, not synthetic model selection:
actual PDFs/Tika extraction, messy documents, tables, multilingual/multi-source questions,
OCR-derived text where relevant, upload/delete/re-import behavior, a long resident session and one
deliberate unload/reload cycle.

---

# 10. Agent / coding boundary

Agent service is exclusive from normal Ollama lanes. Read-only status in normal mode may report agent
registration unavailable/UNKNOWN because the agent API is intentionally stopped; status must not
switch topology simply to inspect it.

`bc250-code` uses the chat path with separated reasoning/final content. File-producing modes reject
outer Markdown code fences rather than stripping them, reject reasoning contamination/incomplete
terminal output and write atomically. Review/document modes may use Markdown.

The current Ornith baseline has canonical agent benchmark evidence, but stronger coding-helper claims
still require bounded real-device qualification of actual generate/refactor/test/commit workflows and
normal-mode restoration afterward.

---

# 11. Maintenance, backup and power contract

The Pi is an availability/power companion first; backup export is secondary.

Stable operator interfaces include:

```text
sudo bc250-maintenance status
sudo bc250-maintenance setup
sudo bc250-maintenance run backup
sudo bc250-maintenance run prune
sudo bc250-maintenance request-shutdown
sudo bc250-maintenance companion status|enable
sudo bc250-maintenance backup-export status|enable
```

Local maintenance design:

- verified config/users backups are independent of the Pi;
- backup archives/checksums are private and verified;
- restore requires Open WebUI stopped, verifies archive/database integrity and keeps rollback material;
- pruning starts dry-run and preserves uncertain metadata rather than deleting ambiguously;
- active maintenance jobs defer safe shutdown;
- warm-up and automatic night power are optional and disabled unless explicitly configured/enabled;
- WOL may be required before poweroff if policy says so.

Safe-power in 1.8:

- inspect both final TCP endpoints for configured protected ports;
- interactive SSH therefore defers its own public `request-shutdown`;
- the dedicated forced-command Pi identity has a separate internal request path that may exempt only
  its exact authenticated SSH tuple;
- any second SSH/UI/Ollama/protected connection still defers;
- missing/failed TCP inspection fails safe by deferring;
- final system power action is requested non-blocking only after all guards pass.

Exact 2.2 has proven interactive SSH defer and the corrected healthy-live-40-CU return-code boundary.
For 2.3, repeat active-SSH defer only as a regression smoke after installing the release. Before unattended
automatic poweroff is enabled, additionally prove the configured companion path if used, idle allow,
real S5/WOL and post-wake readiness/restoration.

---

# 12. Revalidation and evidence discipline

Whole-appliance revalidation is a milestone gate, not a substitute for every focused test. Current
harness records infrastructure, quality, restoration and coverage separately. A legitimate quality
miss must not be confused with an incomplete run or restoration failure.

Evidence rules:

- record exact installed NEVRA and run ID;
- distinguish configured/allocated context from demonstrated prompt length;
- preserve failure artifacts;
- never archive secrets or unnecessary authenticated payloads;
- restoration occurs before final health verification;
- do not claim success when a restoration failure changes final appliance state;
- historical startup AMDGPU/HPD warnings are not automatically new campaign faults; compare against
  the campaign's bounded kernel/device-error window.

Exact installed 1.7 remains the newest full whole-appliance revalidation campaign. Exact installed
2.4 is the latest broad operations acceptance baseline: non-OWUI behavior is closed through Batch 20,
including operational hygiene and supported reboot reconstruction. The final exact-2.4 OWUI
investigation established two additional product defects (ordinary-user model authorization and
Deep Reasoning residency pressure) plus the already-known two-view verifier defect, and proved the
narrow mitigations before restoring temporary state.

Current 0.12.1-0.6 keeps the established runtime configuration and addresses only policy/observability gaps found after 0.5 source qualification and application-plane testing. Exact 0.4/0.5 runtime evidence remains useful; do not replay broad campaigns unless 0.6 unexpectedly changes a runtime boundary.

# 13. Current open gaps and priority order

## P0 — build and focused exact-0.12.1-0.6 policy acceptance

The current release changes only the following acceptance boundaries:

```text
1. ordinary-user Open WebUI selector matches actual 11434/11435 inventory plus curated roles; 11436/11437 remain excluded;
2. dynamic testing-record cleanup touches only bc250-managed records from successfully inventoried lanes; unrelated admin records/grants survive;
3. Advanced/Qwen3.5 effective custom_params match think=false, 0.7/0.8/20/min_p=0/presence=0/repeat=1 end to end;
4. DE↔FR recommendation/obligation and critical literal integrity checks flag unsafe drift rather than silently returning it;
5. bc250-status shows lane residency and reports missing reboot helper as not checked;
6. bc250-revalidate status/raw reports installed NEVRA separately under harness v4.5;
7. bc250-support-bundle capture timeout and internal archive/checksum self-verification work;
8. administrator-owned multi-model-chat state is reported when exposed, never force-converged;
9. Qwen embedded templates, Deep keep_alive=0, topology, TTM, live 40-CU and production RAG/task/embed choices remain unchanged;
10. build RPM/SRPM in the authoritative Fedora path, then run development/handovers/RELEASE-TESTING-HANDOVER-0.12.1-0.6.md.
```

Exact-0.4 already covers broad topology, Ollama 0.34.2 runtime, packaged revalidation, model roles, Jina, RAG product smoke and resource/kernel health. Repeat those campaigns only if a repair unexpectedly changes a corresponding implementation boundary.

Backup restore is already accepted for configuration on exact 2.2 and identity on exact 2.3. Live
pruning, Pi forced-command shutdown, idle S5/WOL and full whole-appliance revalidation remain
conditional rather than automatic release gates.

## P1 — real-office RAG acceptance

Gemma E4B model selection is closed. Qualify actual office documents and long product-path residency.

## P1/P2 — bounded general-assistant comparison

The remaining meaningful main-lane question is whether GPT-OSS 20B buys enough deep-office quality
over Qwen3.5 9B to justify its much tighter memory envelope. Use one bounded production-contract
comparison rather than broad model discovery.

## P2 — agent product-path evidence

Exercise documented `bc250-code` modes and verify exclusive-mode restoration.

## P2/P3 — optional MTP follow-up

No broad campaign. Run only a targeted check if a future runtime/model/hardware change creates a
new package decision; YMQ depth-1 repeat symmetry is optional, not a current gate.

## P3 — secondary operations

Backup export, dedupe performance and other convenience work after power/availability is qualified.

# 14. Durable anti-repeat guardrails

Do not repeat these disproven or unsafe directions without a material changed condition:

1. Do not make the main lane ephemeral merely to fit a larger task model; cold-load UX and product
   behavior matter.
2. Do not promote the rejected Qwen3.8 4B Distill/Qwen3 4B task candidates under the same memory
   topology; coexistence OOM evidence already exists.
3. Do not revert the task default to Gemma 3 1B merely because it is familiar.
4. Do not globally serialize embedding with main/task without evidence; dedicated 11437 is
   intentional.
5. Do not treat RAM/VRAM/GTT/Vulkan views as additive physical memory.
6. Do not auto-enable 40 CUs or raise the governor ceiling from community anecdotes.
7. Do not manually delete Ollama blobs or retained GGUFs when normal lifecycle/dedupe preserves local
   rebuildability.
8. Do not weaken quality, safety, completeness, restoration or secret checks to get a PASS.
9. Do not let omitted destructive selection mean all.
10. Do not allow backend ambiguity to cause local source deletion.
11. Do not enable power-affecting maintenance before WOL/defer/allow/recovery are proven on the exact
    installed release.
12. Do not claim MTP success from tok/s alone; acceptance, quality, memory and stability matter.
13. Do not reopen broad translation or RAG model tournaments that are already settled unless new
    integrated evidence creates a concrete product question.

Canonical detailed rationale belongs in `development/DECISIONS.md`.

---

# 15. Known gaps that are still current

- 0.12.1-0.6 needs the authoritative Fedora RPM/SRPM build plus focused ordinary-user model-surface, translation-integrity, request-policy and diagnostics acceptance; broad exact-0.4/0.5 runtime campaigns do not need replay unless a change crosses those boundaries;
- the new upstream patch/provenance gate still needs to run against the exact prepared source cache in
  the authoritative build environment; the current source environment has no network-populated cache;
- Pi forced-command shutdown, idle S5/WOL and live prune remain conditional acceptance work;
- no-download unregister/re-apply support smoke still needs a corrected privileged file-existence
  wrapper if that lifecycle boundary becomes relevant again;
- real-office RAG behavior is substantially accepted on exact 2.4 for the tested PDF/DOCX/XLSX/PPTX
  and lifecycle cases; further work should be driven by real office files rather than another generic
  benchmark campaign;
- actual `bc250-code` product workflows need broader bounded device evidence;
- arbitrary same-name out-of-band Ollama registration drift is not fully detected/proven;
- current XFS dedupe implementation still deserves a performance run only when storage optimization
  becomes a real product priority;
- exact 1.7 remains the newest full whole-appliance revalidation campaign; exact 2.4 is the latest
  broad operations baseline but is not relabelled as that full campaign.

# 16. Specialist-chat organization

Keep these durable coordination documents:

```text
development/handovers/DEVELOPMENT-WORKFLOW.md
development/handovers/MAIN-INTEGRATION-HANDOVER.md
development/handovers/OPERATIONS-HANDOVER.md
```

Use `SPECIALIST-TESTING-HANDOVER.md` for temporary bounded lanes. Specialists read the newest source,
current decisions/validation docs and the lane-specific docs; they do not maintain a second full
project bible.

Useful specialist lanes only when there is an active question:

```text
support / maintenance / power
RAG / real documents
benchmark operations
general/main quality
agent/coding
translation requalification
MTP targeted confirmation
```

Main integration owns final promotion, release metadata and cross-stream policy.

---

# 17. Fresh-main-chat instruction

> Continue as the BC-250 main integration chat. Treat the newest source/package and exact installed
> evidence as authoritative over handovers. Read `development/handovers/MAIN-INTEGRATION-HANDOVER.md`,
> `development/VALIDATION-MATRIX.md`, `development/TESTING-STRATEGY.md`,
> `development/DECISIONS.md`, `MODELS.md` and the relevant current docs. Current source target is
> `0.12.1-0.6`; exact installed `0.11.3-2.4` is the latest broad operations and final OWUI defect/
> mitigation evidence baseline, while exact installed `0.11.3-1.7` remains the newest full
> whole-appliance revalidation campaign. Use exact-0.4 broad runtime evidence as historical support, but do not call 0.12.1-0.6 accepted before
> its focused exact-package policy regression. GitHub/Fedora owns RPM/SRPM builds, the developer source
> environment owns deterministic/static validation, and BC-250 owns hardware/runtime qualification.
> Preserve verified GGUFs, keep destructive operations explicit, fail closed on ambiguous state, and
> use the bounded 0.12.1 OWUI regression rather than replaying closed broad campaigns.
