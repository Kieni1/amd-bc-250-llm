# Model management

`bc250-model` discovers Ollama models directly from strict `.Modelfile`
templates, downloads their GGUF files and registers them. There is no second
Ollama catalog to keep synchronized.

| Category | Name prefix | Default API | GGUF directory |
|---|---|---|---|
| `production` | `prod-` | `127.0.0.1:11434` | `gguf/production` |
| `experiments` | `exp-` | `127.0.0.1:11434` | `gguf/experiments` |
| `task` | `task-` | `127.0.0.1:11435` | `gguf/task` |
| `agentic` | `agentic-` | `127.0.0.1:11436` | `gguf/agent` |

Packaged templates live in
`/usr/share/bc250-llm-server/model-management/modelfiles/`. Operator templates
live in `/etc/bc250-llm-server/models.d/`; a same-name operator file overrides
the packaged template. The `coding`, `tasker` and `experimental` category names
remain accepted aliases.

## Add or replace a model

Copy the installed example, name the file exactly as the desired Ollama display
name, and fill in its short header and `FROM` path:

```bash
sudo install -m0644 \
  /usr/share/bc250-llm-server/model-management/MODEL-TEMPLATE.Modelfile.example \
  /etc/bc250-llm-server/models.d/exp-example-source-q4-k-m.Modelfile
sudoedit /etc/bc250-llm-server/models.d/exp-example-source-q4-k-m.Modelfile
bc250-model list experiments
sudo bc250-model install experiments exp-example-source-q4-k-m
```

The required header is:

```text
# BC250 category: production|experimental|task|agentic
# Ollama model: NAME
# Source: OWNER/REPOSITORY @ REVISION
# GGUF: FILE.gguf
```

`REVISION` may be a commit, tag, branch or `latest`. `# SHA256:` is optional;
omit it for a flexible test model, or provide 64 lowercase hexadecimal
characters to enforce an exact GGUF. `FROM` must be the category's absolute
GGUF path shown in the table. The filename, Ollama name, category prefix, GGUF
metadata and `FROM` basename must agree. Every chat template must contain
exactly one `PARAMETER num_gpu 99` and `PARAMETER num_keep 256`.

A bad template fails during listing or installation instead of being partially
registered. Adding, replacing or removing the file is all that is needed to
change discovery. RPM upgrades can update packaged templates but do not replace
operator files under `/etc`.

MTP is the deliberate exception. Its download-only llama.cpp entries have no
Ollama name or Modelfile and retain `/etc/bc250-llm-server/mtp-models.toml` for
context and draft-token runtime values.

## Install, refresh and remove

```bash
bc250-model list production
sudo bc250-model install production MODEL-NAME
sudo bc250-model install production MODEL-NAME --refresh
sudo bc250-model cleanup production --list
sudo bc250-model cleanup production MODEL-NAME
```

Selection accepts `all`, the displayed zero-based index, a range such as
`0,2-4`, or the full model name. With no selection, an interactive terminal
prompts and Enter cancels. Production and experiment downloads therefore remain
off until explicitly selected. The task and agentic setup helpers pass `all`
after creating their isolated services:

```bash
sudo bc250-setup-task-model
sudo bc250-setup-coding-agent
```

After a successful download, the manager records the source identity and
calculated SHA-256 in the adjacent `*.bc250.json` state file. Matching state is
reused for commits, tags, branches and `latest`; `--refresh` forces a new
download and Ollama registration. A new GGUF is hashed before it atomically
replaces the installed file.

Hugging Face authentication is requested only when a download is needed.
`HF_TOKEN` or `--token-file PATH` is validated with `hf auth whoami` as the
`ollama` account. Missing or rejected tokens continue anonymously. Set
`BC250_HF_ANONYMOUS=1` for unattended public downloads. The manager does not
persist tokens. Download progress uses a pseudo-terminal and remains visible in
the guided installer transcript; Fedora package `util-linux-script` supplies
that terminal helper.

Cleanup removes the Ollama registration, source GGUF, adjacent state and
rendered runtime Modelfile. It retains the source template so the model remains
available for later installation.

Optional features are grouped by purpose: `task-model/` and `coding-agent/`
manage isolated Ollama instances, `experiments/` contains comparison tools,
`mtp/` contains the llama.cpp MTP workflow, and `embedding/` contains the Open
WebUI embedding helper.

The main instance stores imported Ollama blobs under
`/var/lib/bc250-llm-server/ollama/main`. Task and agent instances use
`/var/lib/bc250-llm-server/ollama/task` and
`/var/lib/bc250-llm-server/ollama/agent`. Source GGUF files remain below
`/var/lib/bc250-llm-server/gguf/`, and the disposable Hugging Face cache is
under `/var/cache/bc250-llm-server/huggingface`.

### Storage Behavior in Ollama

The package sets `OLLAMA_MODELS=/var/lib/bc250-llm-server/ollama/main`, so
pulling or registering a model such as `prod-gpt-oss20b-ggml-org-mxfp4` stores
Ollama's raw model layers in
`/var/lib/bc250-llm-server/ollama/main/blobs/`. The size in `ollama list` is the
model's logical size (about **12 GB** for this example), not always its
incremental filesystem use.

- **Active Model Storage**:
  - Raw model layers are stored in the instance's `blobs/` directory.
  - Metadata is stored in the instance's `manifests/` directory.
  - A standalone model normally needs roughly its listed size plus minimal
    metadata overhead.
  - Shared layers can reduce incremental use; inspect the main store with
    `du -sh /var/lib/bc250-llm-server/ollama/main`.

- **Why Disk Usage Grows**:
  - Ollama retains all pulled models until explicitly removed with `ollama rm`.
  - Models can share common layers.
  - Unused models are not automatically removed.

- **How to Free Space**:
  - Remove an unused registration with
    `ollama rm prod-gpt-oss20b-ggml-org-mxfp4` (see the
    [Ollama CLI reference](https://docs.ollama.com/cli)).
  - Local GGUF files can be re-registered with a `FROM` path (see the
    [Ollama Modelfile reference](https://docs.ollama.com/modelfile)).

The package also retains source GGUF files in `/var/lib/bc250-llm-server/gguf`.
Those files are separate from Ollama's reported model size, so a registered
local GGUF can consume space in both locations. Prefer `bc250-model cleanup`
over manually deleting one side of the registration.

See [`../docs/COMMANDS.md`](../docs/COMMANDS.md) for all options and environment
overrides.
