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
| `embedding` | `embed-` | `11434` | local retrieval embeddings |
| `experiments` | `exp-` | `11434` | model/OCR comparisons |
| `task` | `task-` | `11435` | Open WebUI background tasks |
| `agentic` | `agentic-` | `11436` | coding/repository work |
| `mtp` | n/a | llama.cpp helper | download-only MTP experiments |

Task and agent stores are deliberately separate. The task model unloads after
requests. Use the agent service **exclusively**; do not combine a coding run with
a large main-model workload on the BC-250 unified-memory pool.

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

