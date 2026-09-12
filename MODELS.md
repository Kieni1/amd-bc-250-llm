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
| `mtp` | n/a | llama.cpp helper | download-only MTP experiments |

Main, task and embedding stores are deliberately separate. The main lane keeps its
selected chat model warm for 20 minutes, the compact task lane unloads after each
request, and the embedding lane keeps the small retrieval model warm for 10 minutes.
This preserves interactive chat latency while keeping background task residency small.
Agent/coding is **exclusive**: `bc250-agent-mode enter` stops main/task/embedding and
starts only 11436; `leave` restores normal mode.

The package owns all four Ollama service definitions statically. Normal mode requires main, task and embedding; model registration automatically switches into temporary agent mode when an agentic selection is included and restores normal mode afterwards.

## List, install, replace

```bash
sudo bc250-model list
sudo bc250-model list production
sudo bc250-model list experiments
sudo bc250-model list task
sudo bc250-model list agentic
sudo bc250-model list embedding
sudo bc250-model list mtp --all

sudo bc250-model install production MODEL
sudo bc250-model install experiments MODEL
sudo bc250-model install embedding MODEL
sudo bc250-model install task MODEL
sudo bc250-model install agentic MODEL
```

Selections accept names, displayed indexes, comma lists, ranges or `all`. Prefer
names in scripts. A moving source revision such as `latest` or `main` is allowed
on purpose: this package is a model-testing tool and easy swapping is more useful
than release-style weight pinning before 1.0. The manager records the downloaded
source identity/digest; use `--refresh` when you deliberately want new bytes from
a moving source.

To add or override a model, copy the installed template to the operator directory:

```bash
sudo install -m0644 \
  /usr/share/bc250-llm-server/model-management/MODEL-TEMPLATE.Modelfile.example \
  /etc/bc250-llm-server/models.d/exp-example-source-q4-k-m.Modelfile
sudoedit /etc/bc250-llm-server/models.d/exp-example-source-q4-k-m.Modelfile
sudo bc250-model install experiments exp-example-source-q4-k-m
```

A same-name operator Modelfile overrides the packaged definition. Keep category
prefix, source metadata, GGUF/FROM and BC-250 parameters consistent with the
template; invalid definitions are rejected before download.

## Cleanup and reindexing

```bash
sudo bc250-model cleanup production --list
sudo bc250-model cleanup production MODEL
sudo bc250-model cleanup production MODEL --keep-gguf
```

Use the package tools rather than deleting source GGUFs or Ollama blobs by hand.
Local GGUF models can occupy both source storage and imported Ollama storage;
`sudo bc250-storage status` reports verified duplication and `dedupe` can share
identical XFS extents without deleting either path. `prune-sources` is a separate,
explicit hash-verified option. Remote OCR registrations remain Ollama-managed.

Changing an embedding model, its GGUF bytes, or its query/document prefix scheme
requires an explicit RAG reindex. Since 0.9.7-0.4 the packaged Jina Q4_K_M source uses the refreshed upstream
GGUF carrying `pooling_type` metadata; refresh that model and reindex if an
earlier package copy had already been used for RAG. Keep OCR extraction in the
source language and review the Markdown before it enters the active document
library. Translation remains a separate step.

For the full Modelfile metadata/storage contract see
[`models/README.md`](models/README.md). For deployed role presets see
[`docs/openwebui-settings.md`](docs/openwebui-settings.md), and for exact command
syntax see [`docs/COMMANDS.md`](docs/COMMANDS.md).

## 2026-08-31 benchmark status

The production map is now supported by repeatable BC-250 evidence rather than
model size alone. The numbers below are same-board guidance from Ollama 0.33.2
with the package Vulkan profile; they are not cross-machine leaderboard claims.

| Role/model | Current evidence | Decision |
|---|---|---|
| Gemma E2B | ~1.52 GiB resident, ~112 tok/s, very strong long-prompt ingestion | Keep standard-office default |
| Gemma E4B | ~2.77 GiB resident, ~72 tok/s; source-grounded production prompt behaves as intended | Keep document/RAG default; validate with `rag-quality` |
| LFM2.5 8B-A1B | ~6.83 GiB, ~147 tok/s and strong long-context scaling; `think=false` did not suppress native reasoning | Keep DE<->FR role; judge promotion/retention with `translation` quality |
| Qwen3.5 9B | ~6.86 GiB, ~46 tok/s but ~0.4-0.7 s warm answer start | Keep responsive higher-quality assistant role |
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
package default. Gemma 3 1B
remains an optional fallback/control. The exhausted compact task candidates and
the unsafe Qwen3.8 4B task candidate are source-graveyard entries.

Translation evidence on the actual authenticated Open WebUI path:

- original LFM preset: **45/80**;
- stronger auto-direction prompt: **67/80**, with a regression on the formal
  German-to-French case;
- minimal auto-direction prompt: **69/80**, the best LFM prompt tested so far;
- two explicit direction roles: **69/80**, no net improvement;
- minimal prompt plus temperature 0: **60/80**, making two bad modes
  deterministic.

Prompt/sampling tuning for LFM is therefore paused. The production LFM model remains
unchanged while model-level challengers are screened. The priority
translation experiments are Hunyuan-MT 7B Q4_K_M and Translate-Gemma 4 Sub E4B
Q4_K_XL; the existing Ministral 8B experiment remains only a short comparison
control because prior testing was not strong.

Do not infer promotion from a short candidate screen. A translation challenger
must beat the LFM quality pattern, then pass the real Open WebUI integration
path, and only then receive latency/memory and broader-corpus confirmation.

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

### Exhausted comparison candidates

"Exhausted" here means that the latest comparable benchmark no longer gives the
model a plausible **promotion case for the role it was testing**. It does not
mean the GGUF is corrupt or that the model must be deleted. The active comparison
catalog may retain measured controls even when their promotion path is exhausted.
The source-only graveyard is reserved for models explicitly retired from routine
operator-facing discovery because continued comparison no longer justifies their
catalog presence. Graveyard Modelfiles are not packaged or discovered. Their canonical identities
and manager-owned paths are mirrored in the installed `retired-models.json`
catalog solely so `bc250-model list` can distinguish stale package-retired
registrations from operator-created unmanaged models and `cleanup-retired` can
remove them safely.

The source graveyard currently contains twelve retired definitions in
`models/modelfiles-graveyard/`. That directory is a source depot only and must
contain Modelfiles only; it is intentionally outside every model discovery root.

| Model | Why it is retired from routine discovery |
|---|---|
| `exp-gemma4-e4b-hauhaucs-aggressive-q6-k-p` | earlier retired legacy comparison; no current promotion path is retained in the active catalog |
| `exp-lfm25-1.2b-instruct-liquidai-q6-k` | experimental alias retired after the same Q6_K weights were promoted as `task-lfm25-1.2b-instruct-liquidai-q6-k`; its generic SYSTEM caused cross-task output contamination |
| `exp-minicpm5-2b-openbmb-q4-k-m` | 4/18 with 12 output-budget diagnostics; tag/query outputs were exhausted by reasoning under the deployed budget |
| `exp-qwen3-1.7b-ggml-q4-k-m` | 3/18 with 13 output-budget diagnostics and all tag/query cases failing |
| `exp-qwen38-2b-distill-empero-q6-k` | 8/18 with nine output-budget diagnostics; strong titles did not compensate for unreliable tag/query generation |
| `exp-qwen38-4b-distill-empero-q6-k` | promising quality, but simultaneous residency with warm GPT-OSS OOM-killed the task service, making it unsafe for the normal task role |
| `exp-granite42-8b-ibm-q5-k-m` | ~8.3 GiB resident for ~50 tok/s and weak long-prompt throughput; no demonstrated office/RAG quality win over the production set |
| `exp-ling30-tiny-bloomer-q5-k-m` | very high raw decode (~144 tok/s) but the shared reasoning cap was repeatedly consumed before a usable final answer |
| `exp-qwen35-9b-davidau-defiant-fable-q6-k` | older comparable run had much worse answer-start latency with no throughput/UX case against production Qwen3.5 or GPT-OSS |
| `exp-qwen36-14b-a3b-tvall43-fablevibes-q4-k-m` | earlier retired legacy comparison; no current promotion path is retained in the active catalog |
| `exp-qwythos9b-empero-q6-k` | earlier retired legacy comparison; no current promotion path is retained in the active catalog |
| `task-lfm25-2.6b-liquidai-q6-k` | retired task-lane experiment; superseded by the smaller promoted LFM2.5 1.2B task model |

Still-open comparisons include the Hunyuan/Translate-Gemma translation
challengers, both embedding models, OCR candidates, the remaining general-model
experiments, and the agentic models. Granite 4.2 3B remains a measured
control despite its poor task-contract result. The latest evidence is not sufficient
to call the other open candidates exhausted.

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

## Current comparison policy

Production roles stay stable until a measured replacement wins its real use case.
The current operator comparison pool intentionally retains older Qwen/Gemma/GPT
variants alongside newer candidates so the next full BC-250 run can make the
cleanup decision from one comparable dataset. Notable additions are:

| Model | Why it exists |
|---|---|
| `exp-qwen36-35b-a3b-unsloth-ud-iq3-s` | large MoE main-lane challenger; start at 16K context and fall back to UD-Q2_K_XL if BC-250 headroom is unsafe |
| `exp-qwen38-27b-ista-gsq-rco-iq3-s` | dense 27B GSQ/RCO challenger; IQ3_S first, IQ3_XXS fallback if load/headroom fails |
| `exp-qwen38-27b-unsloth-ud-iq3-s` | dense 27B Unsloth dynamic-quant control; UD-IQ3_S first, UD-IQ3_XXS fallback |
| `exp-gemma4-26b-a4b-mradermacher-i1-iq3-s` | Gemma 4 MoE main-lane challenger; i1-IQ3_S first, i1-IQ3_XS fallback; projector omitted for initial text comparison |
| `exp-qwen38-4b-empero-q6-k` | compact Qwen3.8 4B reasoning comparison using the upstream Q6_K artifact |
| `exp-qwen38-9b-empero-q6-k` | 9B distilled native-reasoning comparison against production Qwen3.5 and GPT-OSS |
| `exp-gpt-oss20b-unsloth-ud-q4-k-xl` | Unsloth UD-Q4_K_XL control quant for GPT-OSS quality/residency comparisons at a conservative 16K context |
| `exp-tir-qwen35-9b-nonthinking-v2-q6-k` | direct/non-thinking 9B comparison for office and RAG response behavior |
| `exp-granite42-3b-ibm-q6-k` | compact multilingual/RAG/structured-output comparison |
| `exp-hunyuan-mt-7b-mungert-q4-k-m` | checksum-pinned dedicated translation challenger; screen explicit DE/FR direction first, then OWUI integration |
| `exp-translate-gemma4-sub-e4b-17s-q4-k-xl` | checksum-pinned translation-specialist Gemma E4B challenger for DE/FR office text |
| `agentic-ornith15-9b-ornith-q5-k-m` | promoted agent default; temperature 0 + 3072-token Bash/Python budget passed 3/3 in three consecutive BC-250 runs |
| `agentic-gemma4-12b-fable5-tau2-q4-k-m` | 12B Gemma 4 agent/tool-use experiment for the exclusive 11436 lane; compare against Qwen2.5-Coder and Ornith before any role change |

GLM-OCR and OvisOCR2 remain the packaged OCR comparison pair. Do not infer fit
from GGUF size alone on the BC-250: the 16 GB CPU/GPU pool must also hold KV/cache,
runtime and the OS. Draft/MTP heads are not standalone models and stay in the
dedicated MTP workflow.

