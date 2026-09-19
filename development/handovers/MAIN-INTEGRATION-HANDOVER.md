# AMD BC-250 LLM appliance — durable main integration handover

## Preservation rule

This is the **long durable technical handover**. Do not turn it into a tiny release
summary. A fresh integration chat must be able to recover the appliance's important
hardware facts, software topology, production role choices, resource constraints,
negative findings, testing philosophy and open work without reconstructing the project
from old chats.

However, this document no longer needs to copy every release-by-release narrative.
Preserve durable knowledge here; preserve detailed chronology in `docs/CHANGELOG.md`,
engineering rationale in `development/DECISIONS.md`, and exact consequential experiment
records under `development/model-runs/`.

When a fact becomes obsolete, update the current fact and retain the old rationale only
when it explains a current constraint or prevents repeating a disproven approach.

Authority when sources disagree:

1. user's current instruction;
2. newest supplied BC-250 source/package;
3. real-device evidence from the exact installed revision;
4. current test evidence for that revision;
5. this handover / current decision records;
6. older handovers, logs, chats and patches.

Never silently override newer source with an older handover.

---

# 1. Current project state

Project: **AMD BC-250 local-LLM office appliance**.

Current source baseline at this handover refresh:

```text
VERSION       0.11.3
RPM Release   1.6%{?dist}
NVR           bc250-llm-server-0.11.3-1.6
```

The current `0.11.3-1.6` source is a pre-v1.0 source-validated integration line on top of
the release-closed 0.11.3-0.4 MTP/model-manager baseline. It carries forward the unpublished
installer/maintenance and revalidation-diagnostic refinements, deterministic RAG/Open WebUI
qualification, and the safe MTP cleanup contract. Release 1.5 carries that RAG decision forward and fixes the embedding-only residency reload probe
exposed by exact installed 1.4; pre-benchmark model **sets** are restored using each Ollama lane's normal keep-alive policy, and resident-session swap evidence remains `swap_peak_delta_mib`. The production
RAG/document role remains Gemma E4B / `bc250-office-documents` on the current 16 GiB profile;
Qwen 9B remains a separate heavier higher-quality general-office option. Existing hard resource
thresholds, GPU/device-error handling, runtime topology, GGUF provenance/SHA policy, model bytes,
MTP settings and CU/governor policy are unchanged.

Current source validation is **SOURCE PASS**: the full deterministic `make validate` gate completes
with **403/403 tests PASS**, including 146 benchmark tests and the new lane-default keep-alive
restoration regression. Changed Python compiles, and packaged shell syntax is checked separately at
release closure. GitHub RPM/SRPM build and exact-source BC-250 runtime qualification remain external;
source validation must not be confused with hardware qualification.

Newest complete real-device appliance evidence is exact installed
`bc250-llm-server-0.11.3-0.4.fc44.x86_64` from 2026-09-19. The refined guided installer
completed with the expected concise model pass and `bc250-verify` reported 54 ok / 0 warn /
0 fail. Revalidation v4.2 completed in 13:56 with infrastructure/restoration PASS, full
coverage and quality **8 pass / 0 quality-fail / 0 skipped**. Task passed 6/6 including the
previously failing `tags-de` case; direct translation 8/8, direct RAG 4/4, production use
cases 5/5, agent 3/3, Open WebUI translation 8/8 and Open WebUI RAG 3/3 also passed.
GPT-OSS/Jina remained within policy but reached only 193.36 MiB minimum MemAvailable and
recorded non-severe 8662 -> 8320 context truncation. `office-draft-e2b` passed semantic
acceptance with an `output-budget` diagnostic. Exact evidence and bundle SHA are recorded
in `development/model-runs/2026-09-19-installed-0.11.3-0.4-revalidation.md`.

Exact installed `0.11.3-1.4.fc44` now adds newer but incomplete current-line evidence. The guided
upgrade/install completed successfully and the core verifier was 54/0/0. Revalidation reached
RAG semantic acceptance 4/4, then correctly failed infrastructure because Jina embedding residency
could not be restored: the embedding-only fallback used an empty `/api/embed` input rejected by
Ollama 0.34. The same partial run reported task 5/6 with `tags-en: relevance`. Release 1.5 fixes only
the restoration probe and installer no-op output; task quality policy is unchanged. Evidence is in
`development/model-runs/2026-09-19-installed-0.11.3-1.4-partial-revalidation.md`.

A separate final RAG finalist campaign on the same exact installed 0.11.3-0.4 generation now
settles the production document/RAG answer role for the current 16 GiB profile. Both Gemma E4B and
Qwen 9B were functionally strong in direct and short authenticated Open WebUI RAG; Gemma then
completed 42/42 continuous-residency product-path turns with roughly 2.7 GiB MemAvailable remaining,
while Qwen reached the campaign's configured 512 MiB safety floor after only a few resident subruns.
This is a sustained-memory-margin decision, not a Qwen semantic-quality failure. Exact evidence is
recorded in `development/model-runs/2026-09-19-rag-finalist-qualification.md`.

The project remains **pre-v1.0**. Do not invent migration/backward-compatibility burdens
that the current source does not impose.

The appliance's main product intent is:

```text
private local office LLM appliance
reliable office chat / documents / translation / RAG
safe multi-lane resource use on 16 GB shared memory
good interactive latency
electricity saving through controlled shutdown + WOL
repeatable package-owned configuration
```

Backup is useful but secondary to office availability and power behavior.

---

# 2. Development / validation rules

The detailed workflow is in `development/handovers/DEVELOPMENT-WORKFLOW.md`.

Core rules that must survive every future chat:

- GitHub owns RPM/package builds.
- User workstation owns Ruff/developer linting as configured.
- BC-250 owns real hardware/runtime/model/Open WebUI/WOL qualification.
- Never try to run unavailable tools merely to say they were attempted.
- State exactly what was tested and what was not.
- Never weaken quality evaluators, verifier thresholds, restoration or secret hygiene to
  obtain green output.
- Hardware work proceeds one bounded evidence batch at a time.
- Preserve downloaded GGUFs where practical.
- Main integration owns versioning, cross-stream defaults and promotion decisions.
- Specialist chats return evidence; they do not silently change production policy.

For test ownership/current gaps see `development/VALIDATION-MATRIX.md`.
For future campaigns see `development/TESTING-STRATEGY.md`.

---

# 3. BC-250 hardware — durable facts

## 3.1 Board/APU identity

The BC-250 is a repurposed semi-custom AMD console-derived APU platform.

Useful identifiers:

```text
CPU family        Zen 2 / Oberon-derived
GPU               Cyan Skillfish
AMDGPU/LLVM       gfx1013
physical memory   16 GB GDDR6 shared by CPU and GPU
```

Do not describe the GPU simply as a normal desktop RDNA2 card. A more precise project
wording is **Cyan Skillfish / gfx1013, console-derived GFX10-family hardware with
additional RDNA2-class features**. Use `gfx1013` when architecture precision matters.

## 3.2 CPU topology

The silicon contains 8 Zen 2 cores / 16 threads, while normal stock board operation
exposes approximately:

```text
6 cores / 12 threads
```

Community SMU/firmware methods may expose the remaining two cores. The appliance does
not depend on that unlock. Treat any 8-core use as a separate hardware experiment with
its own thermal/stability qualification.

Do not state “BC-250 has 8 usable cores” without qualification.

## 3.3 GPU compute topology

Stock software/board presentation is roughly:

```text
24 CUs
12 WGPs
```

The physical GPU has up to:

```text
40 CUs
20 WGPs
```

The package contains both historical/research 40-CU tooling and a live WGP/CU manager.
The live manager can alter dispatch routing with UMR without requiring a kernel patch.

**Never automatically enable 40 CUs during installation.** Live CU routing remains an
operator-controlled feature.

Real-device evidence has shown a healthy **40/40 live routing table**. A kernel/RADV or
other diagnostic may still report 24 CUs. Do not treat one generic CU count as more
authoritative than proven live routing.

Investigate problem cells such as `D!` in the package routing table; do not demand one
hard-coded CU number from every diagnostic layer.

## 3.4 Unified memory

The board has one physical **16 GB GDDR6** pool shared by CPU and GPU.

Do not add:

```text
system RAM + VRAM + GTT + Vulkan heaps
```

to claim more than 16 GB physical capacity. These can be overlapping views/allocations
of the same memory.

For LLM planning, available capacity is approximately:

```text
16 GB total
- kernel / userspace / services
- model runtime overhead
- model weights
- KV/cache
- other allocations
```

This is why two models that load individually can still be unsafe concurrently.

## 3.5 Memory bandwidth

Useful reference figures:

- theoretical 14 Gbps × 256-bit GDDR6 ≈ **448 GB/s**;
- effective community Linux measurements are often lower, around the mid-300 GB/s range
  depending on method/configuration.

Production choices should be driven by real model throughput and resource evidence,
not nominal bandwidth alone.

## 3.6 GPU frequency / governor policy

Current appliance governor policy is deliberately conservative:

```text
350–1850 MHz
fix-freq=false
```

Community projects have demonstrated >2 GHz on some cooled boards. That is not the
package production policy. Do not raise the ceiling because another board benchmarked
higher.

Current governor lineage is `filippor/cyan-skillfish-governor`; retained real-device
reference used version `0.4.12`.

## 3.7 Thermal discipline

Cooling quality varies significantly among repurposed boards. Avoid interpreting
thermal-throttled back-to-back runs as model differences.

Where relevant:

- record temperatures;
- consider heat soak;
- compare candidates under similar thermal conditions;
- include sustained/thermal benchmark profiles only when the question needs them.

## 3.8 Linux support philosophy

Cyan Skillfish support has improved upstream. Old workarounds should not automatically
become permanent package requirements.

Evaluate workarounds against the actual installed kernel/Mesa. Retained real-device
reference (not a claim about the current install) included:

```text
kernel  7.2.4-200.fc44.x86_64
Mesa    26.1.8
```

That reference also had no known recent Vulkan device-loss or compute-ring failure
signature.

---

# 4. Base software architecture

This is an x86-64 Fedora-oriented integration package.

The RPM owns **configuration, package commands, service topology and integration**. It
does not pretend to own all third-party upstream binaries or model weights.

Current runtime pins are authoritative in `config/runtime.env`:

```text
Ollama          0.34.0
Open WebUI      0.11.3
Apache Tika     4.0.0-full
```

Ollama's installer is pinned to official installer commit:

```text
d8ab4b4f0ca24b51d3a46b3bf4f462e58ce66b1f
```

with recorded installer SHA-256:

```text
25f64b810b947145095956533e1bdf56eacea2673c55a7e586be4515fc882c9f
```

Open WebUI and Tika images are digest-pinned in `config/runtime.env`.

---

# 5. Ollama/service topology

The appliance deliberately uses four separate Ollama lanes/stores.

## Main lane

```text
service        ollama.service
port           11434
keepalive      20m
max loaded     1
parallel       1
role           normal office / larger production and experimental models
```

Keep the interactive main lane warm. Port 11434 is a shared product-role lane with one loaded
model at a time; the most recently used main-lane model remains resident according to the normal
20-minute policy. Historical GPT-OSS evidence showed roughly 24–25 s cold load versus 2–3 s warm
response, so making the whole lane ephemeral to solve memory overlap harmed normal multi-turn UX.
Maintenance warm-up defaults to Gemma E2B; GPT-OSS is the deep-reasoning and worst-case-memory
production reference, not a permanently warm universal main model.

## Task lane

```text
service        ollama-task.service
port           11435
keepalive      0
max loaded     1
parallel       1
role           Open WebUI title/tag/background tasks
```

This lane must remain small enough to coexist safely with a warm main model.

## Embedding lane

```text
service        ollama-embedding.service
port           11437
keepalive      10m
max loaded     1
parallel       1
role           dedicated local retrieval embeddings
```

Do not globally serialize embedding with main/task without evidence requiring it.

## Agent lane

```text
service        ollama-agent.service
port           11436
keepalive      5m
max loaded     1
parallel       1
role           coding/agentic helper
normal mode    inactive
```

Agent mode is exclusive by design. Entering agent mode must stop main/task/embedding.
Leaving must restore the complete normal topology. Never call an agent transition
successful because only one endpoint answered.

## User-facing service path

Open WebUI is exposed through nginx on the office-facing HTTP endpoint:

```text
http://<BC250_HOST>/    TCP 80
```

Open WebUI's internal `3000` and Ollama `11434–11437` are not Pi health/readiness
interfaces and should not be opened merely for companion monitoring.

Administrative/restricted maintenance SSH is TCP 22.

Tika stays private to the appliance/container network and serves document extraction.

---

# 6. Current production model map

Canonical current model state is `MODELS.md` plus the package catalogs.

Current production roles:

| Role | Model |
|---|---|
| standard office | `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` |
| document/RAG answer | `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` |
| DE↔FR translation | `prod-translate-gemma4-sub-e4b-17s-q4-k-xl` via explicit direction roles |
| higher-quality office | `prod-qwen35-9b-unsloth-q6-k` |
| deep reasoning / warm main | `prod-gpt-oss20b-ggml-org-mxfp4` |
| embeddings | `embed-jina-v5-small-retrieval-q4-k-m` |
| task default | `task-lfm25-1.2b-instruct-liquidai-q6-k` |
| task retired control | `task-gemma3-1b-unsloth-ud-q4-k-xl` (graveyard) |
| exclusive agent default | `agentic-ornith15-9b-ornith-q5-k-m` |

Do not revive retired/graveyard models because an older handover names them.

---

# 7. Durable model evidence / role rationale

## Standard office — Gemma E2B

Retained same-board evidence records roughly 1.52 GiB residency, ~112 tok/s and very
strong long-prompt ingestion. It remains the lightweight standard-office role.

## RAG answer — Gemma E4B

Retained evidence is roughly 2.77 GiB resident, ~72 tok/s, with the source-grounded RAG
prompt behaving as intended. Its ongoing acceptance should be judged by actual
`rag-quality`/Open WebUI RAG behavior rather than generic generation ranking.

## Translation — LFM2.5 8B-A1B

Retained performance evidence is roughly 6.83 GiB, ~147 tok/s with strong long-context
scaling. `think=false` did not simply remove all native reasoning behavior.

Real authenticated Open WebUI translation history:

```text
original LFM preset                 45/80
strong auto-direction prompt       67/80
minimal auto-direction prompt      69/80  <- best LFM result retained
explicit direction roles           69/80
temperature 0                      60/80
```

Prompt/sampling micro-tuning is considered exhausted. The 2026-09-17 repaired eight-case
direct screen is now saturated and must be treated as a gate rather than a ranking loop.
Fresh production LFM evidence was 6/8, reproducing known semantic/preservation weakness.
Translate-Gemma E4B and Ministral both produced 24/24 canonical confirmation; TIR Qwen3.5
9B reached 8/8 under an explicit non-thinking request contract. Hunyuan remains viable
but has a reproducible CHF-preservation defect. Large Qwen 27B/35B results are quality
upper bounds only because resident memory headroom fell to roughly 116-228 MiB.

Stage-2E settled the model/configuration question by selecting Translate-Gemma E4B with
exact explicit-direction v1, thinking omitted and `max_tokens=2048`; TIR is closed as the
normal deployment choice. By maintainer decision, `prod-translate-gemma4-sub-e4b-17s-q4-k-xl` is now the package production translation base. Installed `0.11.2-0.3.fc44` first verified the live package-owned DE→FR and FR→DE roles through authenticated Open WebUI with correct direction, preserved identifiers/dates and no desired-state drift. Historical `0.11.2-0.4` testing exposed the installed fixture-path defect before translation quality evaluation. Installed `0.11.2-0.5.fc44` then completed v4.1 and passed the canonical `owui-translation` stage, confirming that resource fix on the RPM layout. `0.11.3-0.3` carried that translation model/evaluator contract forward, and current `0.11.3-1.6` leaves it unchanged. Do not reopen broad model discovery
or preservation-prompt micro-tuning unless the integrated failure is proven model-level.

## Higher-quality office — Qwen3.5 9B

Retained evidence is roughly 6.86 GiB and ~46 tok/s with ~0.4–0.7 s warm answer start.
It stays as the responsive higher-quality office role until a real use-case challenger
wins rather than merely benchmarking faster.

## Deep reasoning / memory-edge reference — GPT-OSS 20B

Retained baseline:

```text
resident       ~10.8 GiB
decode         ~79–80 tok/s
prefill        ~620 tok/s
cold load      ~24–25 s
warm answer    ~2–3 s
```

The durable decision is to keep the interactive main lane warm. The 16 GB UMA means task and
embedding coexistence must still be safe beside GPT-OSS because it is the worst credible production
memory case, even though another main-lane model may be resident during ordinary office use.

## Task default — LFM2.5 1.2B

Current promoted default evidence:

```text
15/18 direct task quality
15/18 real Open WebUI with package-owned task prompts
9/9 deliberate true-overlap trials beside warm GPT-OSS
no additional swap growth in those overlap trials
no serious OOM/GPU warning in those trials
```

This replaced Gemma 3 1B as default.

Gemma 3 1B is retired from active task discovery; its historical baseline was only 6/18 with systematic language/relevance misses.

Important task-role rejections:

- `exp-qwen38-4b-distill-empero-q6-k` improved focused quality, but deliberate simultaneous
  residency with warm GPT-OSS caused severe memory pressure and the task service was
  OOM-killed.
- `exp-qwen3-4b-lmstudio-q6-k` scored 5/6 twice in the current cheap screen, but both
  exact-source task staging and a bounded 4096-context task alias caused global OOM and
  killed warm GPT-OSS/other user services.

Do not retest either model for the concurrent background-task role under the same memory
envelope merely because isolated quality looked better. See `development/DECISIONS.md`.

## Embeddings

Current production embedding is Jina v5 small retrieval. Retained harder multilingual
near-duplicate evidence gave Jina and Qwen3 embedding both 11/13 Recall@1 and 13/13
Recall@3. Jina stays baseline; Qwen remains a valid comparison if licensing/behavior or
new RAG evidence makes the question worthwhile.

## OCR

Retained three-page baseline showed approximately:

```text
GLM-OCR mean word F1   ~0.996
OvisOCR2 mean word F1  ~0.735
both                    full field recall on that small baseline
```

GLM leads fidelity; Ovis remains a speed/structure comparison. OCR remains secondary
unless scanned-document workflows become a stronger product requirement.

## Agent

Current default `agentic-ornith15-9b-ornith-q5-k-m` remains the baseline. Installed
`0.11.2-0.5.fc44` passed the canonical agent benchmark 3/3 during full revalidation.
Separate coding-helper evidence showed that the old `/api/generate` product route could
write native reasoning before a useful final answer and could also exhaust its 3072-token
budget before a complete answer. Those are product-path completion/integrity defects, not
reasons to weaken the benchmark or retire Ornith.

The `0.11.2-0.6` source moved `bc250-code` to `/api/chat` with separated thinking/final; current `0.11.3-1.6` carries that product route forward unchanged: separated thinking/final
content, terminal-completion checks, explicit truncation refusal and reasoning-marker
rejection. The 3072 default remains until a bounded real-device A/B justifies a larger
package default. The active comparison funnel is Ornith baseline → Qwable 9B → Qwen3.5
4B Q6_K → Gemma 4 E4B Q4_K_M → Ornith baseline. Gemma 4 12B is retained only if an
E4B result leaves a final 12B comparison useful. Do not graveyard Qwen2.5-Coder from the
summary alone; the raw campaign archive was not supplied to this integration pass.

---

# 8. Active experimental landscape

The canonical complete list is validated in `MODELS.md`. At this handover refresh the
active `exp-*` catalog includes:

```text
exp-gemma4-12b-google-qat-q4-0
exp-gemma4-12b-hauhaucs-uncensored-q4-k-m
exp-gemma4-26b-a4b-mradermacher-i1-iq3-s
exp-glm-ocr-ggml-q8-0
exp-gpt-oss20b-davidau-neo-mxfp4-moe4
exp-gpt-oss20b-unsloth-ud-q4-k-xl
exp-granite42-3b-ibm-q6-k
exp-lfm25-8b-a1b-liquidai-q6-k
exp-ovisocr2-abiray-q8-0
exp-qwen3-4b-lmstudio-q6-k
exp-qwen35-4b-unsloth-q6-k
exp-qwen35-9b-hauhaucs-uncensored-q6-k
exp-qwen36-35b-a3b-unsloth-ud-iq3-s
exp-qwen38-27b-ista-gsq-rco-iq3-s
exp-qwen38-27b-ista-gsq-rco-iq3-xxs
exp-qwen38-27b-unsloth-ud-iq3-s
exp-qwen38-4b-empero-q6-k
exp-qwen38-9b-empero-q6-k
exp-tir-qwen35-9b-nonthinking-v2-q6-k
```

Do not confuse active `exp-qwen38-4b-empero-q6-k` with the retired
`exp-qwen38-4b-distill-empero-q6-k` task candidate.

Large main-lane candidates needing proper resource/fit qualification include:

```text
exp-qwen36-35b-a3b-unsloth-ud-iq3-s
exp-qwen38-27b-ista-gsq-rco-iq3-s
exp-qwen38-27b-ista-gsq-rco-iq3-xxs
exp-qwen38-27b-unsloth-ud-iq3-s
exp-gemma4-26b-a4b-mradermacher-i1-iq3-s
```

The packaged matrix `quality-checks/main/10-main-model-candidate-matrix.sh` is a
performance/resource-fit test against production GPT-OSS. It is **not semantic
acceptance**.

The ISTA Qwen3.8 pair is intentionally role-split: IQ3_XXS is the first deployability/RAG-oriented
text experiment (16K, caller `think=false`), while IQ3_S is the quality-first main-model experiment
(8K, caller `think=true`). Neither changes the production Gemma RAG role or main-lane defaults.

Current main-candidate qualification policy is deliberately evidence-first. Require
backend-aware completion integrity, exact runtime/build/flags, KV-type reporting and a
highest-precision feasible KV reference. After load/resource integrity, run the compact
`usecase` semantic sanity gate before optional 4K/16K context work. Reserve sustained
thermal/CU work for finalists and capture GPU-journal errors. On affected gfx1013
hybrid/direct-llama paths, runtime-default vs `n_ubatch=384` is a qualification A/B, not
a global workaround. MTP evidence must include draft acceptance rate.

Do **not** globally change KV defaults, force F16/32K, set ubatch 384, change governor/CU
policy, upgrade Ollama or promote a new main model from upstream observations alone.
See `development/DECISIONS.md` DEC-006.

The source graveyard contains retired definitions that should not return to routine
discovery absent a justified retest condition. `MODELS.md` is canonical for the current
retired list and rationale.

---

# 9. Model lifecycle / storage contract

Model sources are package-managed with provenance/state sidecars. The intended behavior
is:

- unchanged validated source can be reused without redownload;
- Modelfile-only changes can re-register from retained GGUF;
- explicit refresh refetches when requested;
- `unregister` removes registration/runtime Modelfile while retaining verified GGUF/state;
- normal model reconciliation should not reacquire unchanged sources.

A real-device reconciliation across 29 set-up normal models previously found 27 already
current and re-registered two from existing GGUF with **zero unnecessary GGUF
refetches**.

Known conceptual gap: arbitrary out-of-band mutation of an existing same-name Ollama
registration may escape detection when source/template state is unchanged. Do not claim
complete arbitrary live-manifest drift protection until implemented/tested.

## Ollama conversion/import amplification

Four large converted candidates revealed apparent ~2.8–3× onboarding amplification.
Audit proved the Hugging Face cache was not responsible.

For each new model Ollama temporarily had:

```text
retained package GGUF
+ source-hash/import blob
+ converted/live Ollama blob
```

The manifest referenced only the converted/live layer. Four unreferenced import blobs
were roughly 46.3 GiB total. With `OLLAMA_NOPRUNE` effectively false, a controlled
restart of `ollama.service` reported:

```text
total unused blobs removed: 4
```

and free space rose roughly 428 GiB → 475 GiB while the appliance remained healthy.

Durable conclusion:

- ~3× can be a **temporary onboarding spike** for converted models;
- after normal startup pruning, retaining source GGUF + converted live layer gives
  roughly ~2× logical storage;
- do not manually delete blobs merely to fix the temporary state;
- preserve source GGUFs unless the user explicitly accepts redownload risk.

## XFS dedupe

Byte-identical retained source GGUF / live Ollama blobs can share XFS extents.

Historical bad implementation used 16 MiB ranges with one `xfs_io` process per range,
causing ~7,000 process launches and a ~43m36s run for ~113 GiB.

Current implementation keeps the conservative 16 MiB range but batches all commands for
one source/blob pair into one `xfs_io` process. Do not regress to process-per-range.

A state bug in older code also erased dedupe bookkeeping during model reconciliation
even when physical shared extents remained. Current state schema 3 preserves the dedupe
map. Protect this behavior.

Dedupe performance on the current implementation still deserves bounded real-device
qualification, but it is now lower priority than office power/availability work.

---

# 10. Open WebUI desired state

Current desired state lives in `config/openwebui/desired-state.json`.

## Main/task endpoints exposed to Open WebUI

Main connection publishes these production IDs:

```text
prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl
prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl
prod-gpt-oss20b-ggml-org-mxfp4
prod-translate-gemma4-sub-e4b-17s-q4-k-xl
prod-qwen35-9b-unsloth-q6-k
```

Task connection publishes:

```text
task-lfm25-1.2b-instruct-liquidai-q6-k
```

Current task desired state:

```text
TASK_MODEL                        task-lfm25-1.2b-instruct-liquidai-q6-k
TASK_MODEL_PARAMS                 {}
title generation                  enabled
tag generation                    enabled
follow-up generation              disabled
autocomplete generation           disabled
search-query generation           disabled
retrieval-query generation        disabled
```

The package owns explicit title/tag/query prompt templates. Historical live task testing
showed upstream/default Open WebUI prompts could turn a 15/18 direct LFM result into only
6/18 live, so package-owned prompt state matters.

## Embedding desired state

```text
engine                            ollama
model                             embed-jina-v5-small-retrieval-q4-k-m
batch size                        1
async embedding                   false
concurrent embedding requests     1
endpoint                          internal 11437 lane
```

## RAG desired state

```text
TOP_K                             8
hybrid search                     false
relevance threshold               0
content extraction                Tika
Tika API version                  4
text splitter                     token
Markdown header splitter          enabled
chunk size                        1500
chunk minimum                     0
chunk overlap                     200
```

The RAG template requires source-grounded answers and explicit insufficient-evidence
behavior. It must not silently fill absent document facts from general knowledge unless
the user asks for external/general knowledge.

Open WebUI data under `/var/lib/open-webui` is confidential. Normal package configuration
uses supported Open WebUI APIs rather than direct database edits.

A temporary benchmark that mutates Open WebUI must save exact prior state, apply one
candidate setting, verify it, run the test, restore exact prior state, verify restoration,
and exclude credentials from evidence.

---

# 11. RAG / document workflow

RAG quality must be separated into retrieval and answer generation. Direct qualification must also
restore the starting Ollama residency set after isolation and surface chronological resident-session
MemAvailable/swap behavior; restoration failure is infrastructure failure, not a warning. Important future
cases include:

- answer absent / correct abstention;
- multiple required evidence sources;
- conflicting documents;
- multiple relevant passages;
- invoices/tables;
- scanned/OCR-derived office text;
- multilingual German/French documents;
- preservation of names, dates, numbers and terminology;
- citation correctness among competing files;
- privacy-restricted questions.

Use:

```text
answer_absent: true
```

for fixture cases where the documents do not establish the answer.

Use an explicit source list for multisource requirements rather than overloading a
single old target field.

Do not tune chunking, embedding batch, system context, thinking policy and hybrid search
all at once. Change one axis at a time and use restoring experiment commands.

Hallucination resistance / faithful insufficient-evidence behavior is more important than
squeezing another point from a retrieval leaderboard.

---

# 12. Benchmarking architecture

The package deliberately separates:

```text
bc250-verify       current health
bc250-benchmark    measurements / A-B / role quality
bc250-revalidate   whole-package qualification on the BC-250
```

Every benchmark invocation owns an isolated result directory containing the canonical
artifacts:

```text
meta.json
results.jsonl
summary.json
summary.txt
fixtures/
optional results.csv
```

The shared result contract separates:

```text
result_type   measurement | qualification
outcome       pass | quality-fail | infra-fail | skipped
failure_kinds actual qualification failures
diagnostics   useful observations that are not automatically failures
checks        case-specific booleans/scores
metrics       timing/resource/quality measurements
```

Do not turn a diagnostic such as swap pressure or budget exhaustion into a hard failure
unless the qualification contract says it is one.

Public categories include:

```text
generation
embeddings
ocr
task
agent
usecase
translation
rag-cycle
rag-quality
concurrency
num-batch
owui-rag
owui-embedding-batch
owui-chunk-min
owui-system-context
```

Stateful Open WebUI tuning benchmarks must restore original state; restoration failure
is infrastructure failure.

## Revalidation harness v4.2

The current source targets package version 0.11.3. v4.2 keeps the dedicated GPT-OSS/Jina
coexistence stage as the authoritative deep GPT-OSS resource check, surfaces non-severe
context truncation as an informational diagnostic, and uses lightweight checkpoints at
successful intermediate phase boundaries while retaining full snapshots for preflight,
agent-mode transitions, final restoration and failures. Acceptance thresholds are unchanged.

Whole-appliance revalidation uses six conceptual phases:

1. preflight;
2. production roles;
3. resource edge;
4. exclusive agent mode;
5. packaged Open WebUI RAG;
6. restore/report.

Case quality `rc=3` records a quality failure and continues. Other helper/benchmark
nonzero return codes are infrastructure failures. Final reporting keeps infrastructure,
quality, restoration and coverage separate.

`Quality MIXED` can be a valid completed run. Never weaken a real evaluator to force an
all-green summary.

Use full revalidation for meaningful release/milestone qualification or material
runtime/topology changes—not after every documentation-only patch.

---

# 13. Agent/coding product boundary

Current coding helper model is Ornith in the exclusive agent lane.

`bc250-code` supports bounded local coding assistance such as generation, refactor,
review, documentation, tests and commit-message work. It is **not** a fully autonomous
repository agent and generated output is not automatically applied/executed. Current
source uses `/api/chat` with `think:true`, writes only terminal non-empty final content,
refuses `done_reason=length` and reasoning-marker contamination, and preserves an existing
destination on those failures. The default request budget stays 3072 pending real-device
A/B evidence.

Keep two test layers:

1. safe `bc250-benchmark agent` static format/syntax/structure contract;
2. representative `bc250-code` workflows on disposable/small inputs with human review
   and deliberate real tests when output is intentionally staged.

Do not automatically execute arbitrary generated shell/Python as root.

---

# 14. MTP / speculative decoding

MTP remains optional/experimental and separate from Ollama role models. Packaged definitions stay
disabled from generic convergence; `bc250-fetch-mtp ID` is the explicit preparation path.

Current active catalog IDs:

```text
qwen3.5-9b-mtp
qwen3.6-27b-mtp
qwen3.8-27b-hauhaucs-mtp
qwen3.8-27b-ymq-xs-ti-mtp
```

Broad MTP qualification is now complete enough for current package use under the reviewed external
llama.cpp Vulkan runtime (`b10964`, commit `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`). Real BC-250
evidence supports:

- `qwen3.5-9b-mtp`: PASS; highest absolute speed and strongest short-generation gains; long-form gain
  declines with acceptance but remains positive. Packaged depth stays 3; corrected Phase-2 depth 2 is
  the strongest exploratory candidate and materially beats depth 3, but optional confirmation-grade
  repeats are preferred before changing the default.
- `qwen3.6-27b-mtp`: PASS; strongest sustained long-generation gain of the original set but tightest
  successful memory margin. Corrected Phase 2 supports keeping depth 2.
- `qwen3.8-27b-hauhaucs-mtp`: PASS; more memory headroom and excellent deterministic/parity behavior.
  Corrected Phase 2 supports keeping depth 2; depth-1 balanced gain was only ~0.2% and is noise-scale.
- `qwen3.8-27b-ymq-xs-ti-mtp`: PASS at depth 2; faster baseline decode and stronger absolute MTP
  throughput at longer generations than the earlier HauhauCS evidence, but weaker short-token MTP
  behavior and lower observed memory headroom. It is qualified, not preferred/promoted.
- retired `qwen3.6-35b-a3b-mtp`: stock 8K/full-GPU baseline crossed the 128 MiB hard floor before MTP
  inference. It is a memory-fit failure and remains source-graveyard-only.

The first long Phase-2 depth sweep accidentally repeated defaults and is invalid for depth selection,
but it established a useful low noise floor (~0.01–0.19% throughput CV). Require roughly >=1% balanced
improvement before considering a package-default change. The corrected canary and corrected sweep
proved requested draft depth reaches the emitted llama-server configuration.

Further MTP work is optional and decision-driven only:

1. confirm Qwen3.5 depth 2 at 256/1024 with 3 performance / 2 quality repeats only if changing the
   package default matters;
2. run a same-current-package HauhauCS comparator only if rigorous YMQ/HauhauCS memory comparison is
   required;
3. optimize YMQ depth only if YMQ is being considered for preferred status.

Do not run another broad candidate/depth campaign and do not expand the MTP framework without a
concrete new product question. Exact current evidence is consolidated in
`development/model-runs/2026-09-19-mtp-final-qualification.md`; source-only specialist reproduction guidance is preserved in `development/references/mtp/BC250_MTP_EXECUTION_GUIDE_v3.md`.

# 15. Maintenance, WOL and electricity saving

This became a major product priority after much of the older support testing.

The stable BC-250 ↔ external companion contract is documented in
`docs/MAINTENANCE-CONTRACT.md` (contract version 1).

Responsibility boundary:

```text
BC-250  owns office service, safe-shutdown decision, after-hours policy, local backups
Pi      owns morning WOL schedule, readiness observation, optional safe-shutdown request,
        optional read-only off-device backup
```

The Pi must not infer the machine is idle and issue unconditional poweroff.

Stable external safe request:

```bash
sudo bc250-maintenance request-shutdown
```

The BC-250 may defer shutdown for maintenance, SSH, UI or Ollama activity. Defer is a
normal safe outcome.

Companion setup/status:

```bash
sudo bc250-maintenance companion enable
sudo bc250-maintenance companion status
```

WOL should report NIC `Wake-on: g`, but that is not enough: a **real powered-off/S5
Wake-on-LAN cycle must succeed** before relying on automatic after-hours shutdown.

Current after-hours shutdown attempts are intended around:

```text
18:30
18:45
19:00
19:15
19:30
```

The Pi owns morning wake timing. Cross-machine schedule convention is Europe/Zurich
local wall clock unless deliberately configured otherwise.

Installer ordering deliberately performs core appliance verification before optional
maintenance/Pi setup so an enabled power timer cannot race final installation
qualification.

---

# 16. Backup / export — secondary feature

Routine local backups exist but are not a complete RAG/model/disk image.

Config:

```text
/var/backups/bc250-llm-server/config/
owui-config-YYYY-MM-DD_HHMMSS.tar.gz
+ .sha256
```

Identity/users:

```text
/var/backups/bc250-llm-server/users/
owui-users-YYYY-MM-DD_HHMMSS.sql.gz
+ .sha256
```

Only artifact + matching SHA-256 sidecar is a complete export pair.

Routine backups intentionally exclude bulky uploads/vector/cache/model stores.

Optional read-only export uses `bc250-backup-export` and `/usr/bin/rrsync` from Fedora's
`rsync-rrsync` package, with separate config/users key scopes. Rollback backups and
maintenance secrets remain inaccessible.

The Pi does not need the Open WebUI API key for WOL, readiness, safe shutdown or backup
transport.

Backup is currently **nice-to-have**, not the product's highest-value hardware test.

---

# 17. Packaging / installer / documentation principles

The source manifest is `packaging/install-manifest.tsv`. Current documentation install
layout preserves source-relative paths under the package docdir so links work both in
source and installed representation.

Important package-development principles:

- newest source is authority;
- docs/commands should reflect current implementation;
- `docs/COMMANDS.md` is canonical public CLI reference;
- `MODELS.md` is canonical current model status/catalog;
- `development/` is Git/source-only engineering memory and not installed by binary RPM;
- source-subtree READMEs explain their subtree rather than duplicate full operator docs;
- runnable privileged examples use explicit `sudo`;
- source and staged-installed Markdown links are regression-tested.

The installer should remain idempotent, show a clear plan, keep optional integrations
opt-in and finish core verification before optional power-affecting maintenance setup.

Known upstream installer observations, not automatically defects:

- official Ollama installer may print that it creates/enables `ollama.service` even
  though package topology is restored afterward;
- upstream may download AMD/ROCm payload despite this appliance using Vulkan/RADV/gfx1013;
- HF authentication may print account identity though not token value.

Do not change these without proving a safe improvement.

---

# 18. Current testing strategy / priorities

The detailed plan is `development/TESTING-STRATEGY.md`.

Do **change-impact qualification**, not a giant full matrix after every patch.

Shared promotion funnel:

```text
source/static
→ cheap/direct role screen
→ real product integration path
→ resource/coexistence
→ repeatability
→ durable decision record
```

Current recommended order:

## P0 — operations / office availability / electricity saving

First establish the current installed baseline read-only. Then prove real S5 WOL.
Only after WOL succeeds, test safe shutdown defer while busy and allow while idle.

## P1 — benchmark operations substrate

Run a small known production control set and confirm canonical result artifacts,
measurement semantics and state restoration before a large new quality campaign.

## P1 — translation

Broad DE/FR comparison is closed. Translate-Gemma is the package production base; requalify only the integrated DE→FR / FR→DE roles on the installed release. The former LFM translator is experimental rollback/reference only.

## P1 — RAG / office documents

Answer-model selection is closed for the current 16 GiB profile: Gemma E4B /
`bc250-office-documents` is the production RAG role. The next RAG gate is **real-document product
acceptance**, not another answer-model tournament: actual PDFs/Tika extraction, OCR-derived text
where relevant, tables, multilingual/multi-source questions, collection update/delete/re-upload,
continued residency and one deliberate unload/reload cycle.

## P1/P2 — general assistant / main lane

The main unresolved product question is whether GPT-OSS 20B buys enough deep-office reasoning quality
over Qwen3.5 9B to justify its roughly 4 GiB additional memory cost. Use one bounded 12–16 case
`usecase` fixture under each model's real production contract; preserve full outputs and use manual
pairwise review only where deterministic checks cannot safely express quality. Do not start with
27B/35B challengers unless that comparison gives a concrete reason.

## P2 — agentic/coding

Reconfirm exclusive-mode restoration and broaden actual documented `bc250-code` modes.

## P2/P3 — optional MTP follow-up

Broad MTP qualification is closed. Do not spend hardware time on another sweep unless a release
choice requires Qwen3.5 depth-2 confirmation, a rigorous current-package YMQ/HauhauCS comparator, or
YMQ promotion-specific tuning. Support/maintenance is now the higher-priority hardware lane.

## P3 — optional backup export / dedupe performance

Still useful operational work, but no longer ahead of office availability/power.

---

# 19. Specialist-chat organization

Do not keep seven independent full project bibles permanently synchronized.

Maintain these durable coordination documents:

```text
development/handovers/DEVELOPMENT-WORKFLOW.md
development/handovers/MAIN-INTEGRATION-HANDOVER.md
development/handovers/OPERATIONS-HANDOVER.md
```

Open temporary specialist chats for active lanes using
`SPECIALIST-TESTING-HANDOVER.md`. They should read current source and current lane docs
instead of inheriting copied old catalogs.

Useful specialist lanes:

```text
benchmark operations
translation
RAG/document quality
general/main-lane quality
agent/coding quality
MTP/speculative decoding
```

Task-model, embedding or OCR specialists should be opened only when evidence gives that
lane an active question.

Specialists return exact evidence and a recommendation to main integration. Main owns
promotion, package integration and release metadata.

---

# 20. Durable negative-result / anti-repeat guardrails

These decisions are easy to accidentally rediscover and should remain visible even as
other history is shortened:

1. **Do not make main ephemeral merely to fit a larger task model.** GPT-OSS cold-load
   latency damages normal chat UX; current task model must coexist with warm main.
2. **Do not promote Qwen3.8 4B Distill to normal task under the same topology.** Quality
   improvement did not outweigh OOM coexistence failure.
3. **Do not revert task default to Gemma 3 1B because it is familiar.** LFM2.5 1.2B has
   materially stronger direct/live quality plus successful overlap evidence.
4. **Do not globally serialize embedding with main/task without evidence.** Dedicated
   11437 exists intentionally.
5. **Do not treat diagnostic VRAM/GTT/system memory as additive physical capacity.**
6. **Do not auto-enable 40 CUs.** Live routing is operator-controlled.
7. **Do not raise governor ceiling because community boards run >2 GHz.** 350–1850 is
   package policy.
8. **Do not manually delete Ollama blobs when normal startup pruning/package lifecycle
   explains the state.**
9. **Do not delete retained GGUFs merely to save space when offline/local rebuild is
   desired.**
10. **Do not weaken quality scoring or restoration to make candidate runs green.**
11. **Do not enable power-affecting optional maintenance before core installer
    verification.**
12. **Do not claim MTP success from tok/s alone.** Acceptance rate, quality, resource
    behavior and runtime stability matter.
13. **Do not retest Qwen3 4B for the concurrent task role under the same memory envelope.**
    Two staging variants caused global OOM despite strong cheap-screen quality.
14. **Do not rank translation finalists by repeating the saturated eight-case screen.**
    Advance known 8/8 survivors to Stage-2 harder-corpus discrimination instead.

Canonical reasoning lives in `development/DECISIONS.md`; add new entries when an easy-
to-reverse decision becomes important.

---

# 21. Known open gaps

Keep these explicit until solved or superseded:

- current source/Pi maintenance contract still needs real BC-250 power/WOL qualification;
- current 0.11.3-1.6 source passes the deterministic source gate, but GitHub RPM/SRPM build and exact installed 1.6 device qualification remain pending; exact installed 0.11.3-0.4 is still the newest complete whole-appliance evidence and must not be relabelled as 1.6; support/power hardware qualification remains pending;
- large main-model candidate matrix is not yet full semantic/resource promotion evidence;
- Translate-Gemma production direction roles passed a live authenticated 0.11.2-0.3 smoke and the canonical `owui-translation` stage passed on installed 0.11.2-0.5.fc44; the external Stage-2E hard corpus remains separate model-selection evidence;
- exact Stage-2E hard-corpus payloads live in the recorded evidence archive, not the source tree; do not invent replacement cases if that archive is unavailable;
- RAG finalist selection is complete for synthetic/direct and authenticated Open WebUI fixtures, but real office documents/Tika/OCR breadth still needs qualification across messy PDFs, tables, collection update/delete/re-import, multilingual synthesis and OCR-derived content;
- Ornith passed canonical agent qualification 3/3 on installed 0.11.2-0.5.fc44, but the inherited `bc250-code` `/api/chat` product route and output budget still require bounded real-device qualification before stronger coding-helper claims;
- broad MTP qualification is complete enough for the package; only optional targeted confirmation remains;
- current batched XFS dedupe deserves a performance run when storage work becomes a
  priority;
- arbitrary out-of-band same-name Ollama live-registration drift remains incompletely
  proven/detected;
- broader daily-use general-assistant/human acceptance is still needed before v1.0.

---

# 22. Immediate next action for main integration

Do not start six hardware campaigns simultaneously.

The next real-device sequence should be:

1. GitHub-build the exact 0.11.3-1.6 RPM/SRPM, install it on the BC-250 and capture exact NEVRA
   plus RPM/source artifact SHA before making a current-release hardware claim.
2. Run one bounded exact-source appliance verification/revalidation pass, including installer optional-
   setup behavior and the non-failing tight-resource/output-budget diagnostics.
3. Run the final Gemma-only real-office-document RAG acceptance campaign: actual PDFs/Tika extraction,
   multilingual/multi-source/table cases, upload/delete/re-upload, one unload/reload cycle and one long
   resident session. This is production acceptance, not another answer-model tournament.
4. Restore/confirm normal appliance health, then run the support/maintenance hardware batch: local
   maintenance status/backups/timers, S5 WOL, busy shutdown/defer, idle shutdown/allow + wake, Pi
   restricted access/export only where configured, then bounded recovery/lifecycle UX.
5. Treat MTP as optional follow-up only if one of the remaining targeted decisions materially affects
   a release; do not reopen broad qualification.

That sequencing protects the product's current top priorities without losing the deeper
quality program.

---

# 23. Fresh-main-chat instruction

> Continue as the BC-250 main integration chat. Treat the newest supplied source and
> exact installed real-device evidence as authoritative over handovers. Read
> `development/handovers/MAIN-INTEGRATION-HANDOVER.md`,
> `development/VALIDATION-MATRIX.md`, `development/TESTING-STRATEGY.md`,
> `development/DECISIONS.md`, `MODELS.md` and relevant current docs. Preserve the durable
> hardware/software constraints in this handover. GitHub owns RPM builds, workstation
> owns Ruff, BC-250 owns real runtime/hardware qualification. Use one bounded hardware
> batch at a time. Main integration owns production promotion, cross-stream decisions and
> release metadata. Current highest hardware priority is support/maintenance and office availability/power/WOL;
> after that, use product evidence to decide whether any remaining model/benchmark work is worth doing,
> RAG, general quality, agentic and MTP specialist campaigns.
