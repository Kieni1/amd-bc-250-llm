# Model management

`bc250-model` downloads GGUF files and registers Ollama models from five small
TOML catalogs. The complete workflow lives in the single `modelctl.py` command;
there is no internal framework or executable catalog to maintain. The
download-only MTP catalog stays with its runner under `mtp/`:

| Catalog | Purpose | Default API |
|---|---|---|
| `production` | Main office models | `127.0.0.1:11434` |
| `experiments` | Ollama comparison models | `127.0.0.1:11434` |
| `mtp` | Download-only llama.cpp MTP inputs | None |
| `task` | Chat-title model | `127.0.0.1:11435` |
| `coding` | Dedicated agentic models | `127.0.0.1:11436` |

All Ollama templates are kept in the single `modelfiles/` directory. A template
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

Selection accepts the displayed index, a range such as `0,2-4`, a stable model
id, or the full Ollama display name. Prefer ids/names in automation because
catalog ordering can change.

Catalog revisions accept a commit, tag, branch or `latest`. After a successful
download, the manager writes its SHA-256 and source identity to the adjacent
`*.bc250.json` state file. Matching source and checksum state is reused for
every revision type; use `--refresh` to test whether a moving tag, branch or
`latest` changed. `--sha256` can enforce an expected download digest. A new
download is hashed before it atomically replaces the installed GGUF, and an
Ollama entry is registered on every selected install run.

Hugging Face authentication is requested only when a download is actually
needed. `HF_TOKEN` or `--token-file PATH` is checked with `hf auth whoami` as
the `ollama` account. Missing or rejected tokens continue anonymously; use
`BC250_HF_ANONYMOUS=1` for unattended public-model downloads. The manager never
writes tokens to `.bashrc` or another operator file. Hugging Face progress bars
remain enabled. Downloads use a pseudo-terminal so live byte progress remains
visible when the installer is also writing its transcript to a file.

Low-space checks fail before downloading and point to the explicit cleanup
command. Cleanup requires a category, selection and confirmation, then removes
the Ollama registration, source GGUF, state file and rendered runtime
Modelfile. It never changes the TOML catalog. For example, first run
`sudo bc250-model cleanup task --list`, then
`sudo bc250-model cleanup task MODEL-ID`.

Optional features are grouped by purpose: `task-model/` and `coding-agent/`
manage isolated Ollama instances, `experiments/` contains comparison tools,
`mtp/` contains the llama.cpp MTP workflow, and `embedding/` contains the
Open WebUI embedding helper.

The main instance stores imported Ollama blobs under `/var/lib/bc250-llm-server/ollama/main`. Task and
agent instances use `/var/lib/bc250-llm-server/ollama/task` and
`/var/lib/bc250-llm-server/ollama/agent`. Source GGUF files remain below
`/var/lib/bc250-llm-server/gguf/`, and the disposable Hugging Face cache is
kept separately under `/var/cache/bc250-llm-server/huggingface`.

### Storage Behavior in Ollama

The package sets `OLLAMA_MODELS=/var/lib/bc250-llm-server/ollama/main`, so pulling or registering a
model such as `prod-gpt-oss20b-ggml-org-mxfp4` stores Ollama's raw model layers in
`/var/lib/bc250-llm-server/ollama/main/blobs/`. The size in `ollama list` is the model's logical size
(about **12 GB** for this example), not always its incremental filesystem use.

- **Active Model Storage**:
  - The model's **blobs** (raw weights) are stored in `/var/lib/bc250-llm-server/ollama/main/blobs/`.
  - Metadata (e.g., model name, version) is stored in `/var/lib/bc250-llm-server/ollama/main/manifests/`.
  - A standalone model normally needs roughly its listed size plus minimal metadata overhead.
  - Shared layers can reduce incremental use; check the actual store with `du -sh /var/lib/bc250-llm-server/ollama/main`.

- **Why Disk Usage Grows**:
  - Ollama **retains all pulled models** (blobs) until explicitly removed with `ollama rm`.
  - Multiple models **share blobs** if they have common layers (e.g., fine-tunes of the same base model).
  - **No auto-cleanup**: Unused models remain on disk until manually deleted.

- **How to Free Space**:
  - Remove unused models: `ollama rm prod-gpt-oss20b-ggml-org-mxfp4` (see the [Ollama CLI reference](https://docs.ollama.com/cli)).
  - Local GGUF files can be re-registered with a `FROM` path (see the [Ollama Modelfile reference](https://docs.ollama.com/modelfile)).

The package also retains source GGUF files in `/var/lib/bc250-llm-server/gguf`.
Those files are separate from Ollama's reported model size, so a registered
local GGUF can consume space in both locations. Prefer `bc250-model cleanup`
over manually deleting one side of the registration.

Former executable shell catalogs and arbitrary runtime model renaming are not
supported. See [`docs/COMMANDS.md`](../docs/COMMANDS.md) for options and
environment overrides.
