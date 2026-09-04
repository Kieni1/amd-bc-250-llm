# Model management

The guided installer establishes the required task and embedding baseline, then
offers one unified optional model selection across production, experiments,
agentic, embedding, task and MTP entries. The model manager keeps lane routing
and exclusive agent-mode transitions internal. Use the commands below later to
add, refresh or remove models.

## Commands

```bash
sudo bc250-model list
sudo bc250-model list production
sudo bc250-model list experiments
sudo bc250-model list task
sudo bc250-model list agentic
sudo bc250-model list embedding
sudo bc250-model list mtp --all

sudo bc250-model install production MODEL-NAME
sudo bc250-model install production MODEL-NAME --refresh
sudo bc250-model cleanup production --list
sudo bc250-model cleanup production MODEL-NAME
```

The category-free list shows all Ollama-backed models with one global index,
download state and registration state. Category filters keep those global
indexes, so a number means the same model in list, install and cleanup. `all`
adds MTP to the combined operations with globally unique displayed indexes. Selections accept a full name, displayed index, comma
list, range such as `0,2-4`, or `all`. With no selection, a terminal prompts and
Enter cancels. Prefer full names in scripts.

Model listing requires `sudo` because the local GGUF/state trees are intentionally
protected. This avoids misleading `download unknown` results after
`cleanup --keep-gguf`; a retained local source is visible as `downloaded` while
its registration is shown as `not set up`. A registration without a current
Modelfile is shown as unmanaged; a known model on the wrong Ollama instance is
shown as misplaced.

| Category | Prefix | Ollama API | Source GGUF directory |
|---|---|---|---|
| `production` | `prod-` | `127.0.0.1:11434` | `gguf/production` |
| `experiments` | `exp-` | `127.0.0.1:11434` | `gguf/experiments` |
| `task` | `task-` | `127.0.0.1:11435` | `gguf/task` |
| `agentic` | `agentic-` | `127.0.0.1:11436` | `gguf/agent` |
| `embedding` | `embed-` | `127.0.0.1:11437` | `gguf/embedding` |

The public categories are `production`, `experiments`, `task`, `agentic`,
`embedding`, `mtp` and `all`; legacy aliases are intentionally not accepted. MTP
is the only exception to Modelfile discovery: its download-only entries remain in
a TOML runtime catalog because they have no Ollama model or Modelfile.

## Add or override a model

Copy the installed template, name it after the intended Ollama display name and
edit it:

```bash
sudo install -m0644 \
  /usr/share/bc250-llm-server/model-management/MODEL-TEMPLATE.Modelfile.example \
  /etc/bc250-llm-server/models.d/exp-example-source-q4-k-m.Modelfile
sudoedit /etc/bc250-llm-server/models.d/exp-example-source-q4-k-m.Modelfile
sudo bc250-model list experiments
sudo bc250-model install experiments exp-example-source-q4-k-m
```

Required header:

```text
# BC250 category: production|experiments|task|agentic|embedding
# Ollama model: NAME
# Source: OWNER/REPOSITORY @ REVISION
# GGUF: FILE.gguf
```

`REVISION` can be a commit, tag, branch or `latest`. An optional `# SHA256:`
line pins the exact GGUF. Normally `FROM` must use the absolute category GGUF
path and agree with the metadata filename. Experimental vision/OCR definitions have one narrow exception: `FROM hf.co/OWNER/REPOSITORY:TAG` lets
Ollama manage a vision model and its paired projector directly. Remote FROM is
rejected outside `experiments`. Every template requires exactly one
`PARAMETER num_gpu 99`; chat/vision templates also require exactly one
`PARAMETER num_keep 256`.

Invalid metadata, names, prefixes, paths or duplicate required parameters fail
before download. Operator files live in `/etc/bc250-llm-server/models.d/`; a
same-name operator file overrides the packaged template and survives upgrades.

## Download state and authentication

After a successful manager-downloaded GGUF, an adjacent `*.bc250.json` file
records source identity, calculated SHA-256 and file stat metadata. Unchanged
size/mtime/ctime use a fast reuse path. Legacy state or changed stat metadata
forces a full SHA-256 check before the existing GGUF can be reused, so modified
or corrupted bytes are not accepted merely because the sidecar still exists.
Repository, revision and GGUF filename must also match. Modelfile-only changes
therefore regenerate the Ollama registration without downloading again. Use
`--refresh` to deliberately fetch new source bytes, including a moving revision
such as `latest`.

For experimental OCR definitions with remote `hf.co/...` FROM, Ollama owns the
main model blob and required vision projector in its normal model store.
`bc250-model` therefore labels the source `Ollama-managed (main+projector)` rather than pretending
there is a manager-owned source GGUF under `/var/lib/bc250-llm-server/gguf/`.
This is intentionally different from text-only local-GGUF models: preserving
only the main OCR GGUF would not provide a reliable restore path for the paired
projector on Ollama 0.33.2.

Hugging Face authentication is requested only when a manager download needs it. `HF_TOKEN` or
`--token-file PATH` is validated as the `ollama` account. Missing or rejected
tokens continue anonymously and are not persisted. Use
`BC250_HF_ANONYMOUS=1` for unattended public downloads.

## Storage and cleanup

Source GGUFs remain below `/var/lib/bc250-llm-server/gguf/`. `bc250-model cleanup`
removes local source/state only after an Ollama-backed registration is confirmed
removed; a failed `ollama rm` leaves the local source intact and returns failure.
Ollama imports model layers into one of these separate stores:

```text
/var/lib/bc250-llm-server/ollama/main
/var/lib/bc250-llm-server/ollama/task
/var/lib/bc250-llm-server/ollama/embedding
/var/lib/bc250-llm-server/ollama/agent
```

A local model can therefore consume space as both source GGUF and Ollama blob.
Shared layers may reduce incremental Ollama use, while `ollama list` reports
logical model size rather than total appliance use.

Prefer `bc250-model cleanup` over deleting one side manually. For ordinary
local-GGUF definitions it removes the selected Ollama registration, source GGUF,
state and rendered Modelfile while retaining the source template. For remote OCR definitions it removes the registration/rendered Modelfile;
there is no separate manager-owned GGUF/state pair to retain or delete. With
`--keep-gguf`, the command says so explicitly instead of implying that an OCR
source file was preserved.

See [`../docs/COMMANDS.md`](../docs/COMMANDS.md) for every option and
[`../docs/openwebui-settings.md`](../docs/openwebui-settings.md) for current
model roles.

## Cleanup without re-downloading later

`sudo bc250-model cleanup CATEGORY SELECTION --keep-gguf --yes` removes the Ollama
registration (allowing Ollama to prune unreferenced manifest/blob data) and the
runtime Modelfile while retaining the local GGUF plus its `.bc250.json`
state sidecar. A later install can therefore reuse the checked source file.
Without `--keep-gguf`, cleanup also removes the local GGUF/state as before.
`sudo bc250-model cleanup all --keep-gguf` applies the retained-source cleanup to
every category. Never manually purge Ollama's shared blob directory for one model.


## Runtime lane ownership

Normal mode uses main 11434, task 11435 and embedding 11437. Install embedding
models with `bc250-model install embedding` so registration targets the dedicated
store/service. Agent 11436 is disabled at boot and runs only through exclusive
`bc250-agent-mode enter|leave`; do not register production/embedding models there.
