# Model management

The guided installer asks for production, task, agentic and embedding models in
separate phases. Use the commands below later to add, refresh or remove models.

## Commands

```bash
bc250-model list
bc250-model list production
bc250-model list experiments
bc250-model list task
bc250-model list agentic
bc250-model list embedding

sudo bc250-model install production MODEL-NAME
sudo bc250-model install production MODEL-NAME --refresh
sudo bc250-model cleanup production --list
sudo bc250-model cleanup production MODEL-NAME
```

The category-free list shows all Ollama-backed models with one global index,
download state and registration state. Category filters keep those global
indexes, so a number means the same model in list, install and cleanup. MTP has
its own local indexes. Selections accept a full name, displayed index, comma
list, range such as `0,2-4`, or `all`. With no selection, a terminal prompts and
Enter cancels. Prefer full names in scripts.

`download unknown` means an unregistered model's protected source path is not
readable by the current user. Run `sudo bc250-model list` when an exact
downloaded-but-not-registered check is needed. A registration without a current
Modelfile is shown as unmanaged.

| Category | Prefix | Ollama API | Source GGUF directory |
|---|---|---|---|
| `production` | `prod-` | `127.0.0.1:11434` | `gguf/production` |
| `experiments` | `exp-` | `127.0.0.1:11434` | `gguf/experiments` |
| `task` | `task-` | `127.0.0.1:11435` | `gguf/task` |
| `agentic` | `agentic-` | `127.0.0.1:11436` | `gguf/agent` |
| `embedding` | `embed-` | `127.0.0.1:11434` | `gguf/embedding` |

`experimental`, `tasker`, `coding`, `embed` and `embedded` are accepted aliases.
MTP is the only exception: download-only entries remain in a TOML runtime
catalog because they have no Ollama model or Modelfile.

## Add or override a model

Copy the installed template, name it after the intended Ollama display name and
edit it:

```bash
sudo install -m0644 \
  /usr/share/bc250-llm-server/model-management/MODEL-TEMPLATE.Modelfile.example \
  /etc/bc250-llm-server/models.d/exp-example-source-q4-k-m.Modelfile
sudoedit /etc/bc250-llm-server/models.d/exp-example-source-q4-k-m.Modelfile
bc250-model list experiments
sudo bc250-model install experiments exp-example-source-q4-k-m
```

Required header:

```text
# BC250 category: production|experimental|task|agentic|embedding
# Ollama model: NAME
# Source: OWNER/REPOSITORY @ REVISION
# GGUF: FILE.gguf
```

`REVISION` can be a commit, tag, branch or `latest`. An optional `# SHA256:`
line pins the exact GGUF. `FROM` must use the absolute category GGUF path and
agree with the metadata filename. Every template requires exactly one
`PARAMETER num_gpu 99`; chat templates also require exactly one
`PARAMETER num_keep 256`.

Invalid metadata, names, prefixes, paths or duplicate required parameters fail
before download. Operator files live in `/etc/bc250-llm-server/models.d/`; a
same-name operator file overrides the packaged template and survives upgrades.

## Download state and authentication

After a successful download, an adjacent `*.bc250.json` file records source
identity and calculated SHA-256. Matching state is reused even for a moving
revision such as `latest`; use `--refresh` for a deliberate network refresh.

Hugging Face authentication is requested only when needed. `HF_TOKEN` or
`--token-file PATH` is validated as the `ollama` account. Missing or rejected
tokens continue anonymously and are not persisted. Use
`BC250_HF_ANONYMOUS=1` for unattended public downloads.

## Storage and cleanup

Source GGUFs remain below `/var/lib/bc250-llm-server/gguf/`. Ollama imports
model layers into one of these separate stores:

```text
/var/lib/bc250-llm-server/ollama/main
/var/lib/bc250-llm-server/ollama/task
/var/lib/bc250-llm-server/ollama/agent
```

A local model can therefore consume space as both source GGUF and Ollama blob.
Shared layers may reduce incremental Ollama use, while `ollama list` reports
logical model size rather than total appliance use.

Prefer `bc250-model cleanup` over deleting one side manually. It removes the
selected Ollama registration, source GGUF, state and rendered Modelfile but
keeps the source template discoverable for later installation.

See [`../docs/COMMANDS.md`](../docs/COMMANDS.md) for every option and
[`../docs/openwebui-settings.md`](../docs/openwebui-settings.md) for current
model roles.
