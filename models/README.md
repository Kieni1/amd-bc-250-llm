# Model management

`modelctl.py` downloads GGUF files and registers Ollama models from five small
TOML catalogs. Normal Ollama catalogs live under `sources/`; the download-only
MTP catalog stays with its runner under `mtp/`:

| Catalog | Purpose | Default API |
|---|---|---|
| `production` | Main office models | `127.0.0.1:11434` |
| `experiments` | Ollama comparison models | `127.0.0.1:11434` |
| `mtp` | Download-only llama.cpp MTP inputs | None |
| `task` | Chat-title model | `127.0.0.1:11435` |
| `coding` | Dedicated agentic models | `127.0.0.1:11436` |

Each Ollama entry has one template under `modelfiles/<category>/`. The template
filename exactly matches the registered Ollama name and includes model family,
source and quantization. Download-only MTP entries intentionally have no
Modelfile and are managed separately from Ollama experiments.

Production and Ollama experiment entries are disabled by default. Enable only
the entries wanted on the appliance, then list or install them:

```bash
bc250-model list production --all
sudoedit /etc/bc250-llm-server/production-models.toml
sudo bc250-fetch-models
```

The task and coding catalogs are installed by their setup commands, which first
create isolated Ollama services:

```bash
sudo bc250-setup-task-model
sudo bc250-setup-coding-agent
```

Catalog revisions accept a commit, tag, branch or `latest`. A runtime
`--revision` override renders a temporary Modelfile without changing the
packaged template. `--sha256` can enforce the downloaded GGUF checksum.

Optional features are grouped by purpose: `task-model/` and `coding-agent/`
manage isolated Ollama instances, `experiments/` contains comparison tools,
`mtp/` contains the llama.cpp MTP workflow, and `embedding/` contains the
Open WebUI embedding helper.

The main instance stores imported Ollama blobs under `/var/llm/ollama`. Task and
agent instances use `/var/llm/ollama-task/models` and
`/var/llm/ollama-agent/models`. Source GGUF files remain in the catalog's
destination until removed explicitly.

### Storage Behavior in Ollama

The package sets `OLLAMA_MODELS=/var/llm/ollama`, so pulling or registering a
model such as `gpt-oss20b-ggml-org-mxfp4` stores Ollama's raw model layers in
`/var/llm/ollama/blobs/`. The size in `ollama list` is the model's logical size
(about **12 GB** for this example), not always its incremental filesystem use.

- **Active Model Storage**:
  - The model's **blobs** (raw weights) are stored in `/var/llm/ollama/blobs/`.
  - Metadata (e.g., model name, version) is stored in `/var/llm/ollama/manifests/`.
  - A standalone model normally needs roughly its listed size plus minimal metadata overhead.
  - Shared layers can reduce incremental use; check the actual store with `du -sh /var/llm/ollama`.

- **Why Disk Usage Grows**:
  - Ollama **retains all pulled models** (blobs) until explicitly removed with `ollama rm`.
  - Multiple models **share blobs** if they have common layers (e.g., fine-tunes of the same base model).
  - **No auto-cleanup**: Unused models remain on disk until manually deleted.

- **How to Free Space**:
  - Remove unused models: `ollama rm gpt-oss20b-ggml-org-mxfp4` (see the [Ollama CLI reference](https://docs.ollama.com/cli)).
  - Local GGUF files can be re-registered with a `FROM` path (see the [Ollama Modelfile reference](https://docs.ollama.com/modelfile)).

The package also retains source GGUF files in `/var/llm/gguf*`. Those files are
separate from Ollama's reported model size. Remove a source GGUF only after its
Ollama registration has succeeded and it is no longer needed for
re-registration.

Former executable shell catalogs and arbitrary runtime model renaming are not
supported. See [`docs/COMMANDS.md`](../docs/COMMANDS.md) for options and
environment overrides.
