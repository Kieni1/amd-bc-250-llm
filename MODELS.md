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

Main, task and embedding stores are deliberately separate. The task model unloads
after requests; the embedding lane keeps the small retrieval model for 10 minutes
to avoid unnecessary chat-model eviction during document work. Agent/coding is
**exclusive**: `bc250-agent-mode enter` stops main/task/embedding and starts only
11436; `leave` restores normal mode.

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
sudo bc250-setup-embedding-model MODEL
sudo bc250-setup-task-model MODEL
sudo bc250-setup-coding-agent MODEL
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
```

Use the manager rather than deleting source GGUFs or Ollama blobs by hand. Local
GGUF models can occupy both source storage and imported Ollama storage; remote
OCR registrations are Ollama-managed and therefore have different cleanup
semantics.

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
| Gemma 3 1B task | 6/6 structurally usable OWUI JSON, but requested language matched only 2/6 | Keep task default; multilingual adherence is the next quality target |

### 0.10.0 residency follow-up

The 2026-08-31 production run predates the dedicated 11437 embedding service.
Jina is small and normal main+task+embedding concurrency is the intended 0.10.0
layout, but GPT-OSS 20B is the likely memory-edge case. After deploying 0.10.0,
rerun the production/use-case and long-context measurements with the embedding
model warm. Do not infer a regression or change the keepalive until that same-board
measurement exists. Agentic/coding results are separate because agent mode is
exclusive by design.

### Exhausted comparison candidates

"Exhausted" here means that the latest comparable benchmark no longer gives the
model a plausible **promotion case for the role it was testing**. It does not
mean the GGUF is corrupt or that the model must be deleted. Definitions remain in
the experiment catalog until an explicit catalog-pruning release, which keeps the
package useful for reproducibility and operator comparisons.

| Model | Why the current promotion path is exhausted |
|---|---|
| `exp-granite42-8b-ibm-q5-k-m` | ~8.3 GiB resident for ~50 tok/s and weak long-prompt throughput; no demonstrated office/RAG quality win over the production set |
| `exp-ling30-tiny-bloomer-q5-k-m` | very high raw decode (~144 tok/s) but the shared reasoning cap was repeatedly consumed before a usable final answer |
| `exp-qwen35-9b-davidau-defiant-fable-q6-k` | older comparable run had much worse answer-start latency with no throughput/UX case against production Qwen3.5 or GPT-OSS |
| `task-lfm25-2.6b-liquidai-q6-k` | only the two title cases produced useful final output in the reviewed 6-case task run; not a Gemma 3 1B replacement under the current task contract |

Still-open comparisons include Qwen3.8 4B Distill (compact reasoner), Granite
4.2 3B (compact architecture baseline), Qwen3.6 14B-A3B (needs one larger shared
reasoning-budget quality run if retained), both embedding models, OvisOCR2, and
the agentic models. The latest evidence is not sufficient to call those exhausted.

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
| `exp-qwen38-4b-distill-empero-q6-k` | compact native-reasoning Qwen comparison |
| `exp-granite42-3b-ibm-q6-k` | compact multilingual/RAG/structured-output comparison |
| `exp-granite42-8b-ibm-q5-k-m` | larger Granite office/RAG challenger |
| `exp-ling30-tiny-bloomer-q5-k-m` | low-active-parameter architecture experiment |
| `task-lfm25-2.6b-liquidai-q6-k` | multilingual task-model challenger to Gemma 3 1B |
| `agentic-qwen25-coder7b-unsloth-q5-k-m` | Qwen2.5-Coder coding starting point; rerun the tightened static-semantic agent fixture before promotion |

GLM-OCR and OvisOCR2 remain the packaged OCR comparison pair. Do not infer fit
from GGUF size alone on the BC-250: the 16 GB CPU/GPU pool must also hold KV/cache,
runtime and the OS. Draft/MTP heads are not standalone models and stay in the
dedicated MTP workflow.

