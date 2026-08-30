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
bc250-model list
bc250-model list production
bc250-model list experiments
bc250-model list task
bc250-model list agentic
bc250-model list embedding
bc250-model list mtp --all

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
requires an explicit RAG reindex. Since 0.9.7-0.4 the packaged Jina Q4_K_M source
uses the refreshed upstream GGUF to the upstream GGUF carrying `pooling_type` metadata; refresh that
model and reindex if an earlier package copy had already been used for RAG.
Keep OCR extraction in the source language and review the Markdown before it enters the active document library. Translation remains a
separate step.

For the full Modelfile metadata/storage contract see
[`models/README.md`](models/README.md). For deployed role presets see
[`docs/openwebui-settings.md`](docs/openwebui-settings.md), and for exact command
syntax see [`docs/COMMANDS.md`](docs/COMMANDS.md).
