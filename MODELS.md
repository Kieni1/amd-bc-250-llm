# Model handling

This project is still pre-1.0 and assumes a **green-field/test appliance**. The
guided installer is allowed to reapply the reviewed project baseline instead of
acting as a non-destructive configuration migration tool. Keep important custom
host settings outside the appliance or document them before rerunning `install`.
Operator Modelfiles under `/etc/bc250-llm-server/models.d/` remain the supported
way to override packaged model definitions.

## Stores and roles

| Category | Name prefix | Ollama service | Purpose |
|---|---|---|---|
| `production` | `prod-` | `11434` | office, translation, RAG, reasoning |
| `embedding` | `embed-` | `11437` | dedicated local retrieval embeddings |
| `experiments` | `exp-` | `11434` | model/OCR comparisons |
| `task` | `task-` | `11435` | Open WebUI background tasks |
| `agentic` | `agentic-` | `11436` | coding/repository work |
| `mtp` | n/a | standalone llama.cpp runtime | download-only MTP experiments |

Main, task and embedding stores are deliberately separate. The main lane keeps its
selected chat model warm for 20 minutes, the compact task lane unloads after each
request, and the embedding lane keeps the small retrieval model warm for 10 minutes.
This preserves interactive chat latency while keeping background task residency small.
Agent/coding is **exclusive**: `bc250-agent-mode enter` stops main/task/embedding and
starts only 11436; `leave` restores normal mode.

During pre-v1 comparison testing Open WebUI exposes every model actually installed on the normal
main (`11434`) and task (`11435`) providers. Curated `bc250-office-*` roles remain the product
contracts; raw production, experimental and task identities are visible so behavior can be compared
without editing provider allowlists. The embedding and exclusive agent lanes remain outside the normal
chat selector.

MTP is different from the agent lane: it shares catalog/provenance handling with `bc250-model`, but
its runtime is a standalone opt-in external llama.cpp server rather than an Ollama service lane.
Direct `bc250-run-mtp` operation snapshots and drains any resident Ollama models first, then restores
the exact pre-run residency set when the standalone server exits. Qualification/comparison runs
intentionally leave Ollama cold so residency cannot contaminate performance/resource evidence.

The package owns all four Ollama service definitions statically. Normal mode requires main, task and embedding; model registration automatically switches into temporary agent mode when an agentic selection is included and restores normal mode afterwards.

## Inspect, apply, refresh and remove

`bc250-model` separates catalog discovery, state inspection and lifecycle actions:

```bash
bc250-model list
bc250-model list production
bc250-model list experiments
bc250-model list task
bc250-model list agentic
bc250-model list embedding
bc250-model list mtp --all
# MTP stays opt-in even though it shares the lifecycle manager:
sudo bc250-fetch-mtp qwen3.5-9b-mtp

# Generic installer / apply-all convergence never selects MTP.
sudo bc250-model status agentic MODEL
sudo bc250-model status agentic MODEL --online

sudo bc250-model apply production MODEL
sudo bc250-model apply experiments MODEL
sudo bc250-model apply embedding MODEL
sudo bc250-model apply task MODEL
sudo bc250-model apply agentic MODEL

sudo bc250-model refresh experiments MODEL
sudo bc250-model unregister experiments MODEL
sudo bc250-model remove experiments MODEL
sudo bc250-model purge-retired
```

`list` is catalog-only and does not require root. `status` is the read-only runtime
inspection command: it reports source/provenance validity, current-definition and
runtime-Modelfile drift, registration state and a recommended reconciliation action.
`--online` additionally checks moving upstream revisions without mutating local state.
In normal mode the agent Ollama API is intentionally stopped, so full read-only
`status agentic MODEL` may report registration as unavailable/UNKNOWN. That is not a reason
to switch modes merely for inspection: apply/remove operations enter agent mode when needed,
while read-only status leaves the appliance topology unchanged.

`apply` converges a selected model to the current catalog definition and reuses an
existing verified GGUF whenever possible. `refresh` deliberately fetches source bytes
again before applying the definition. `unregister` removes the Ollama registration and
runtime Modelfile while retaining manager-owned GGUF/state. `remove` additionally removes
that manager-owned GGUF/state. `purge-retired` is restricted to the explicit package
retirement catalog.

Selections accept names, displayed indexes, comma lists, ranges or `all`. Prefer names
in scripts. The category `all` means the combined catalog; it does not itself select every
model. Use `sudo bc250-model apply all all` only when you deliberately mean every eligible
non-MTP model. A moving source revision such as `latest` or `main` is allowed on purpose:
this package is a model-testing tool. The recorded digest identifies the exact artifact currently
installed; it is not a permanent product pin for moving `latest`/`main` sources. `status --online` can
identify an upstream change and `refresh` is the explicit decision to resolve/download the newer artifact,
after which the manager records its new digest/provenance.

To add or override a model, copy the installed template to the operator directory:

```bash
sudo install -m0644 \
  /usr/share/bc250-llm-server/model-management/MODEL-TEMPLATE.Modelfile.example \
  /etc/bc250-llm-server/models.d/exp-example-source-q4-k-m.Modelfile
sudoedit /etc/bc250-llm-server/models.d/exp-example-source-q4-k-m.Modelfile
sudo bc250-model status experiments exp-example-source-q4-k-m
sudo bc250-model apply experiments exp-example-source-q4-k-m
```

A same-name operator Modelfile overrides the packaged definition. The operator directory is
expected to be empty on a stock install; packaged definitions live under
`/usr/share/bc250-llm-server/model-management/modelfiles/`. Keep category prefix, source
metadata, GGUF/FROM and BC-250 parameters consistent with the template; invalid definitions are
rejected before download. Operator definitions must retain the `.Modelfile` suffix; visible
regular files in `models.d` with another suffix are rejected instead of being silently ignored.
Use the canonical category metadata `experiments` for new experimental overrides; historical
singular `experimental` metadata remains readable for compatibility. `status` makes an override
or Modelfile drift visible before an action is taken.

## Source retention and reindexing

Use the package lifecycle commands rather than deleting source GGUFs or Ollama blobs by
hand. To remove only the registration while keeping a verified source for quick reuse:

```bash
sudo bc250-model unregister production MODEL
sudo bc250-model apply production MODEL
```

To remove registration plus manager-owned source/state:

```bash
sudo bc250-model remove production MODEL
```

Local GGUF models can occupy both source storage and imported Ollama storage;
`sudo bc250-storage status` reports verified duplication and `dedupe` can share identical
XFS extents without deleting either path. `prune-sources` remains a separate, explicit
hash-verified storage action. Remote OCR registrations remain Ollama-managed.

Changing an embedding model, its GGUF bytes, or its query/document prefix scheme requires
an explicit RAG reindex. Since 0.9.7-0.4 the packaged Jina Q4_K_M source uses the refreshed
upstream GGUF carrying `pooling_type` metadata; refresh that model and reindex if an earlier
package copy had already been used for RAG. Keep OCR extraction in the source language and
review Markdown before it enters the active document library. Translation remains a
separate step.

For the full Modelfile metadata/storage contract see [`models/README.md`](models/README.md).
For deployed role presets see [`docs/openwebui-settings.md`](docs/openwebui-settings.md),
and for exact command syntax see [`docs/COMMANDS.md`](docs/COMMANDS.md).

## 2026-08-31 benchmark status

> **Historical decision evidence — superseded where later sections say otherwise.**
> Keep the measured results, but use the current catalog/decision sections below for today's lifecycle state.

The production map is now supported by repeatable BC-250 evidence rather than
model size alone. The numbers below are same-board guidance from Ollama 0.33.2
with the package Vulkan profile; they are not cross-machine leaderboard claims.

| Role/model | Current evidence | Decision |
|---|---|---|
| Gemma E2B | ~1.52 GiB resident, ~112 tok/s, very strong long-prompt ingestion | Keep standard-office default |
| Gemma E4B | ~2.77 GiB resident, ~72 tok/s; final RAG campaign: 36/36 short OWUI turns and 42/42 continuous-residency turns with ~2.7 GiB MemAvailable remaining | Keep document/RAG default on the 16 GiB profile |
| LFM2.5 8B-A1B | ~6.83 GiB, ~147 tok/s and strong long-context scaling; `think=false` did not suppress native reasoning | Keep DE<->FR role; judge promotion/retention with `translation` quality |
| Qwen3.5 9B | ~6.86 GiB, ~46 tok/s, strong short-path RAG quality; long-residency OWUI RAG reached the campaign's 512 MiB safety floor after a few subruns | Keep responsive higher-quality assistant role; not the long-lived RAG default on 16 GiB |
| GPT-OSS 20B | ~10.8 GiB, ~80 tok/s and usable medium-reasoning latency in the reviewed run | Keep deep-reasoning role; re-test memory headroom with the new resident embedding lane |
| Jina v5 / Qwen3 Embedding | both 11/13 Recall@1, 13/13 Recall@3 on the harder multilingual near-duplicate fixture | Jina stays baseline; Qwen remains a real licensing/behavior alternative |
| GLM-OCR / OvisOCR2 | GLM ~0.996 mean word F1 vs Ovis ~0.735, both full field recall on the three-page baseline | GLM leads fidelity; Ovis remains speed/structure comparison |
| LFM2.5 1.2B task | 15/18 direct and 15/18 through real Open WebUI with package-owned prompts; 9/9 true-overlap trials beside warm GPT-OSS | Promote as default task model; retain Gemma 3 1B as fallback/control |
| Gemma 3 1B task | 6/18 baseline with systematic language/relevance misses | Retain as the previous low-memory fallback/control, not the default |

## 2026-09-10 quality follow-up

The pre-v1.0 quality pass now separates model-candidate work from the six-phase
whole-appliance revalidation harness. The standalone checks under
`quality-checks/` collect candidate evidence without changing production
defaults or claiming release qualification.

Task-model evidence on the real BC-250:

- packaged Gemma 3 1B: **6/18** across three runs (roughly 2/6 each run);
  failures were mainly genuine language/relevance misses;
- Granite 4.2 3B Q6_K: **2/18** under the packaged contract, with 16
  output-budget diagnostics and frequent reasoning-budget exhaustion before a
  usable final answer;
- Qwen3.8 4B Distill Q6_K: **9/18** under the unchanged 128-token non-title
  contract; eight of nine failures hit the output budget. Earlier clarified
  prompting plus a 256-token non-title budget reached 6/6, but deliberate
  simultaneous residency with warm GPT-OSS OOM-killed the task service.

The 2026-09-12 compact-task follow-up changed that decision. LFM2.5 1.2B first
scored 11/18 with its generic experimental SYSTEM, then 15/18 after removing that
SYSTEM. The no-SYSTEM candidate repeated 15/18 through the real Open WebUI route
only after Open WebUI was given the same package-owned task prompts used by the
direct benchmark; with upstream/default OWUI prompts the live result was only
6/18. Finally, nine deliberate simultaneous GPT-OSS/LFM generations completed
with both models observed resident, no additional swap growth, and no serious
OOM/GPU warnings. `task-lfm25-1.2b-instruct-liquidai-q6-k` is therefore the
package default. At that historical point Gemma 3 1B remained an optional
fallback/control; the current decision below retires it to the source graveyard. The exhausted compact task candidates and
the unsafe Qwen3.8 4B task candidate are source-graveyard entries.

Translation evidence on the actual authenticated Open WebUI path:

- original LFM preset: **45/80**;
- stronger auto-direction prompt: **67/80**, with a regression on the formal
  German-to-French case;
- minimal auto-direction prompt: **69/80**, the best LFM prompt tested so far;
- two explicit direction roles: **69/80**, no net improvement;
- minimal prompt plus temperature 0: **60/80**, making two bad modes
  deterministic.

Those LFM results are historical pre-Stage-2 evidence. Subsequent Stage-2E testing
selected Translate-Gemma and closed the broad translation tournament; see the current
decision section below and `development/model-runs/2026-09-17-translation-stage2e.md`.
The old LFM identity is no longer the production default in this source.

## 2026-09-17 task and translation decisions

Detailed campaign evidence lives under `development/model-runs/`; runtime Modelfiles
remain concise so evidence-note edits do not trigger needless Ollama reconciliation.

### Task role

`task-lfm25-1.2b-instruct-liquidai-q6-k` is the sole active task-lane model. Its
promotion evidence remains 15/18 direct, 15/18 through authenticated Open WebUI with
package-owned prompts, and 9/9 true-overlap trials beside warm GPT-OSS. Installed
0.11.3-0.2 still produced one `tags-de` format miss by emitting two JSON objects; 0.11.3-0.3
clarifies the package-owned tag prompt so broad and specific tags share one array and only
one raw JSON object is allowed. The model, strict evaluator and 128-token tag budget are
unchanged pending focused device retest. The previous Gemma 3 1B fallback/control is
retired to the source graveyard after its weak ~2/6 current-task behavior.
`exp-qwen3-4b-lmstudio-q6-k` remains an experiment but is explicitly rejected for
concurrent background-task deployment because both task staging attempts caused global
OOM and warm-main loss.

### German/French translation role

Stage-2E closed the broad translation tournament.
`prod-translate-gemma4-sub-e4b-17s-q4-k-xl` is now the production translation base.
The two Open WebUI production roles are:

- `bc250-office-translation-de-fr`;
- `bc250-office-translation-fr-de`.

Both use the exact Stage-2E system prompt, the package-owned non-global direction
filter, thinking omitted, and `max_tokens=2048`. The selected configuration produced
10/16 hard passes, 16/16 target-language checks and 72/78 advisory semantic dimensions
with 6.91 s mean wall time, 23.01 s p95 and 8362 MiB minimum MemAvailable. The 2048
budget is required because the long FR→DE case truncated at 1024 and completed at 1376
output tokens under the selected configuration.

Known caveats remain evidence, not hidden product claims: DE→FR may localize financial
typography, one targeted bullet case omitted a trailing ordinary-language sentence, and
the focused `Avoir AV-19` case did not produce the preferred explicit `Gutschrift` word.
The numeric evaluator correctly treats locale-equivalent values such as `8.1` and `8,1`
as equal without claiming byte-for-byte formatting preservation.

The former `prod-lfm25-8b-a1b-liquidai-q6-k` identity is retired; the same LFM family is
retained as `exp-lfm25-8b-a1b-liquidai-q6-k` only for deliberate rollback/reference
comparisons. Hunyuan-MT and Ministral translation-only challengers are retired to the
source graveyard. TIR Qwen3.5 9B remains active only as a broader office/RAG experiment;
its translation deployment path is closed under current evidence. The old experimental
Translate-Gemma identity is also retired after promotion to the production name.

The Stage-2E evidence archive is
`bc250-translation-stage2e-config-bundle-20260917-232916.tar.gz`, SHA-256
`63fa90ea1187b7c878da0067d3f0be91e5a9e9faadbb4c919c7ed2a374f80c1c`.
Installed `0.11.2-0.3.fc44` first verified the integrated authenticated direction roles,
and installed `0.11.2-0.5.fc44` subsequently completed revalidation v4.1 with the
canonical `owui-translation` stage passing. The Stage-2E hard corpus remains separate
historical selection evidence; the real-device package path is now verified through the
0.5 release.

### Production residency follow-up

The 2026-08-31 production run predates the dedicated 11437 embedding service.
Jina is small and all three normal services remain active. GPT-OSS 20B is the
memory-edge production case, so re-run production/use-case and long-context
measurements with the embedding model warm after changes that can affect runtime
residency. Later real-device testing showed that GPT-OSS remained healthy after an
ephemeral Qwen3.8 task request, but deliberate simultaneous GPT-OSS + Qwen3.8
residency OOM-killed the task service. Making every main request ephemeral avoided
that overlap but imposed roughly large-model cold-load latency on subsequent chat,
so the package keeps the proven warm main lane. The later LFM2.5 1.2B Q6_K task
model passed true overlap without additional swap growth and replaced Gemma as the
default; the unsafe Qwen3.8 4B task candidate moved to the source graveyard. Agentic/coding
results are separate because agent mode is exclusive by design.

### Retired / exhausted catalog

The source-only graveyard is for models with no current routine promotion path. Graveyard
Modelfiles are not packaged or discovered. Their canonical manager-owned identities are
mirrored in `models/retired-models.json` so stale installed registrations remain
distinguishable from operator-created unmanaged models and can be removed safely with
`bc250-model purge-retired`.

The graveyard currently contains 17 definitions. Important recent role changes are:

| Model | Why it is retired from routine discovery |
|---|---|
| `task-gemma3-1b-unsloth-ud-q4-k-xl` | superseded by the proven LFM 1.2B task model; current task quality remained about 2/6 |
| `prod-lfm25-8b-a1b-liquidai-q6-k` | former production translation identity; superseded by production Translate-Gemma, with LFM retained only as `exp-lfm25-8b-a1b-liquidai-q6-k` |
| `exp-translate-gemma4-sub-e4b-17s-q4-k-xl` | experimental identity retired after the same selected weights were promoted under the production name |
| `exp-hunyuan-mt-7b-mungert-q4-k-m` | translation-only challenger behind Translate-Gemma with reproducible CHF preservation weakness |
| `exp-ministral3-8b-unsloth-ud-q5-k-xl` | translation-only finalist superseded when Stage-2E selected Translate-Gemma |
| `exp-qwen38-4b-distill-empero-q6-k` | task quality was promising but simultaneous warm-main residency OOM-killed the task service |
| `task-lfm25-2.6b-liquidai-q6-k` | superseded by the smaller promoted LFM2.5 1.2B task model |

Other older graveyard entries remain documented by their Modelfiles, decision history and
retired catalog. Do not resurrect them because of an isolated benchmark score; require a
new role, changed hardware/runtime envelope or other explicit retest condition.

Active experiments must retain a current comparison purpose. The former production LFM
translation model is an explicit rollback/reference; TIR remains a broader office/RAG
comparison; general-main, OCR, embedding and agent experiments keep their separate lanes.

Use the role-specific lanes before changing defaults:

```bash
bc250-benchmark usecase
bc250-benchmark translation
bc250-benchmark rag-quality
bc250-benchmark embeddings
bc250-benchmark ocr
bc250-benchmark task
bc250-benchmark agent
```

## Active experiment catalog

This is the canonical operator-facing list of packaged `exp-*` registrations. It is
validated against `models/modelfiles/`; retired/source-graveyard models are listed
separately below.

<!-- ACTIVE_EXPERIMENTS:BEGIN -->
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
<!-- ACTIVE_EXPERIMENTS:END -->

## Agent/coding lifecycle

`agentic-ornith15-9b-ornith-q5-k-m` remains the package default and baseline. Installed
`0.11.2-0.5.fc44` passed the canonical agent benchmark 3/3 during full revalidation.
Separate product-path evidence then showed why static benchmark success is not sufficient:
a coding helper that writes reasoning or a truncated final answer into a file is a product
contract failure even when the cleaned body is useful. Source `0.11.2-0.6` therefore
separates native thinking from final content through `/api/chat` and fails closed on
nonterminal/truncated/reasoning-contaminated output.

The next comparison funnel keeps Ornith as baseline, Qwable 9B as a serious challenger,
and adds Qwen3.5 4B Q6_K plus Gemma 4 E4B Q4_K_M as compact challengers. Gemma 4 12B
remains available for one final comparison only if the E4B result leaves that useful.
Qwen2.5-Coder 7B is not moved to the graveyard in this source because the raw campaign
archive was not supplied to this integration pass. No weights are deleted by catalog
status changes.

## Current comparison policy

Production roles stay stable until a measured replacement wins its real use case.
The current operator comparison pool intentionally retains older Qwen/Gemma/GPT
variants alongside newer candidates so the next full BC-250 run can make the
cleanup decision from one comparable dataset. Notable additions are:

| Model | Why it exists |
|---|---|
| `exp-qwen36-35b-a3b-unsloth-ud-iq3-s` | large MoE main-lane challenger; start at 16K context and fall back to UD-Q2_K_XL if BC-250 headroom is unsafe |
| `exp-qwen38-27b-ista-gsq-rco-iq3-s` | ISTA GSQ/RCO IQ3_S quality-first dense 27B experiment; 8K context, think=true, upstream thinking-mode sampling; 11.8 GB weights require strict BC-250 headroom qualification |
| `exp-qwen38-27b-ista-gsq-rco-iq3-xxs` | ISTA GSQ/RCO IQ3_XXS deployability/RAG experiment; the 16K test answered 5/5 early RAG cases correctly but fell to ~0.28 GiB MemAvailable before safety abort, so the same verified model/GGUF is now bounded to 8K; think=false, upstream non-thinking sampling; no Open WebUI role/default changes |
| `exp-qwen38-27b-unsloth-ud-iq3-s` | dense 27B Unsloth dynamic-quant control; UD-IQ3_S first, UD-IQ3_XXS fallback |
| `exp-gemma4-26b-a4b-mradermacher-i1-iq3-s` | Gemma 4 MoE main-lane challenger; i1-IQ3_S first, i1-IQ3_XS fallback; projector omitted for initial text comparison |
| `exp-qwen38-4b-empero-q6-k` | compact Qwen3.8 4B reasoning comparison using the upstream Q6_K artifact |
| `exp-qwen38-9b-empero-q6-k` | 9B distilled native-reasoning comparison against production Qwen3.5 and GPT-OSS |
| `exp-gpt-oss20b-unsloth-ud-q4-k-xl` | Unsloth UD-Q4_K_XL control quant for GPT-OSS quality/residency comparisons at a conservative 16K context |
| `exp-tir-qwen35-9b-nonthinking-v2-q6-k` | direct/non-thinking 9B comparison for office and RAG response behavior |
| `exp-granite42-3b-ibm-q6-k` | compact multilingual/RAG/structured-output comparison |
| `exp-lfm25-8b-a1b-liquidai-q6-k` | former production DE/FR translator retained as rollback/reference while the promoted Translate-Gemma product path is verified |
| `agentic-ornith15-9b-ornith-q5-k-m` | promoted agent default; retain as the baseline while product-path completion/extraction is qualified |
| `agentic-qwable9b-empero-q6-k` | active 9B coding/agent challenger; retain for the next comparative funnel |
| `agentic-qwen35-4b-khazarai-q6-k` | new compact Qwen3.5 agentic-coding challenger; Q6_K with the Qwen precise-coding sampling profile; qualification pending |
| `agentic-gemma4-e4b-sol-fable-q4-k-m` | new compact Gemma 4 E4B agentic/coding challenger; conservative 16K deterministic BC-250 test profile; qualification pending |
| `agentic-gemma4-12b-fable5-tau2-q4-k-m` | 12B Gemma 4 agent/tool-use comparison; retain until the E4B challenger establishes whether a final 12B comparison is useful |
| `agentic-qwen25-coder7b-unsloth-q5-k-m` | legacy coding comparison; lifecycle decision remains pending canonical campaign-evidence reconciliation |

GLM-OCR and OvisOCR2 remain the packaged OCR comparison pair. Do not infer fit
from GGUF size alone on the BC-250: the 16 GB CPU/GPU pool must also hold KV/cache,
runtime and the OS. Draft/MTP heads are not standalone Ollama role models and stay in the dedicated MTP
workflow. Packaged MTP entries have no Ollama Modelfiles and are excluded from combined
`apply all` / `refresh all` convergence regardless of their enabled flag; explicit
`bc250-fetch-mtp` / `apply mtp` remains the preparation boundary.

The completed MTP campaign now has a small package-facing policy in the existing MTP catalog:

| Active MTP ID | Package policy | Context | Draft |
|---|---|---:|---:|
| `qwen3.5-9b-mtp` | primary fast model | 16384 | 2 |
| `qwen3.8-27b-ymq-xs-ti-mtp` | primary general 27B | 8192 | 1 |
| `qwen3.8-27b-hauhaucs-mtp` | specialist alternative | 8192 | 2 |

`qwen3.6-27b-mtp` is retired from the active/recommended lane because the optimized Qwen3.8
choices provide better absolute throughput, memory headroom and practical completion efficiency.
Its historical passing result is preserved in the source-only MTP graveyard. The stock
`qwen3.6-35b-a3b-mtp` 8K/full-GPU configuration remains retired for memory fit.

The MTP `role` / `recommendation` fields are presentation/policy metadata only: all active entries
remain disabled/download-only and excluded from installer or `apply all` convergence.
`bc250-fetch-mtp [SELECTION]` remains the explicit preparation boundary. `bc250-compare-mtp ID`
remains the same-target qualification path and `bc250-run-mtp ID` the manual runtime/debug path.
Use exact IDs for 27B models; the ambiguous 27B convenience aliases were removed rather than
silently retargeted after the package preference changed.

