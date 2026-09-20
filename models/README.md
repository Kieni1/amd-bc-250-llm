# Model management

The guided installer establishes the required production/task/embedding baseline, then offers one
unified optional selection across ordinary Ollama-backed production, experiments, agentic, embedding
and task entries. MTP is deliberately absent from that picker and from combined `apply all` /
`refresh all`; use `bc250-fetch-mtp` for explicit speculative-decoding preparation. The model manager
keeps lane routing and exclusive agent-mode transitions internal. Use the commands below later to add,
refresh or remove models.

## Commands

```bash
bc250-model list
bc250-model list production
bc250-model list experiments
bc250-model list task
bc250-model list agentic
bc250-model list embedding
bc250-model list mtp --all
sudo bc250-fetch-mtp qwen3.5-9b-mtp  # explicit opt-in for disabled MTP experiments
LLAMACPP=/opt/llama.cpp/build/bin/llama-server bc250-compare-mtp qwen3.5-9b-mtp

sudo bc250-model status agentic MODEL
sudo bc250-model status agentic MODEL --online
sudo bc250-model status all --compact  # compact ordinary-model view used by the installer
sudo bc250-model status mtp --include-disabled --compact  # explicit MTP state view

sudo bc250-model apply production MODEL-NAME
sudo bc250-model refresh production MODEL-NAME
sudo bc250-model unregister production MODEL-NAME
sudo bc250-model remove production MODEL-NAME
sudo bc250-model purge-retired
```

`list` reports catalog definitions only and therefore does not need root. `status` is the
read-only runtime/state view and normally needs `sudo` for the protected GGUF/state tree.
It reports source/provenance validity, Modelfile drift, registration state and a recommended
action. `--online` checks moving upstream revisions without mutating local state; normal
status output points to that option when upstream state was not checked. `--verbose` adds
source repository/revision/SHA and resolved paths. `--compact` uses the same inspector for one-line
state output. Fully current ordinary entries collapse to `[CURRENT]`; inactive agent entries show a
short deferred state, while drift/missing entries retain the detailed reason needed for action.

Selections accept a full name, displayed index, comma list, range such as `0,2-4`, or
`all`; global indexes remain stable across category-filtered list/status/action views.
Prefer full names in scripts. `apply` reuses a verified source whenever possible;
`refresh` deliberately refetches source bytes. `unregister` keeps manager-owned GGUF/state,
while `remove` deletes them after registration removal succeeds.

Registrations without a current active Modelfile are shown as unmanaged unless they are
named in the package retirement catalog. Retired package-managed registrations are handled
only by `purge-retired`; a known active model on the wrong Ollama instance is shown as
misplaced.

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
a TOML runtime catalog because they have no Ollama model or Modelfile. The active MTP
catalog also owns its small package-facing `role` and `recommendation` metadata so list output,
runtime context/draft defaults and operator documentation do not need separate selection tables.
This metadata never enables a model or promotes it into normal convergence. Packaged MTP entries
remain excluded from combined mutation convergence regardless of enabled state; use
`sudo bc250-fetch-mtp ID` when deliberately preparing one for standalone llama.cpp use.
`bc250-run-mtp` drains normal Ollama residency for memory isolation and restores the pre-run set on
normal direct use, while `bc250-compare-mtp` intentionally leaves Ollama cold after qualification.

## Add or override a model

Copy the installed template, name it after the intended Ollama display name and
edit it:

```bash
sudo install -m0644 \
  /usr/share/bc250-llm-server/model-management/MODEL-TEMPLATE.Modelfile.example \
  /etc/bc250-llm-server/models.d/exp-example-source-q4-k-m.Modelfile
sudoedit /etc/bc250-llm-server/models.d/exp-example-source-q4-k-m.Modelfile
bc250-model list experiments
sudo bc250-model status experiments exp-example-source-q4-k-m
sudo bc250-model apply experiments exp-example-source-q4-k-m
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
before download. Operator files live in `/etc/bc250-llm-server/models.d/`; that directory is
expected to be empty on a stock install because packaged definitions live under
`/usr/share/bc250-llm-server/model-management/modelfiles/`. A same-name operator file overrides
the packaged template and survives upgrades. Every visible regular definition there must end in
`.Modelfile`; otherwise model discovery fails with the offending filename instead of silently
ignoring it. Use canonical category `experiments` for new overrides; singular `experimental` is
accepted only for older files.

## Download state and authentication

After a successful manager-downloaded GGUF, an adjacent schema-3
`*.bc250.json` file records source/model/category identity, calculated SHA-256
and file stat metadata. Schema 1/2 sidecars remain readable. Unchanged
size/mtime/ctime use a fast reuse path. Legacy state or changed stat metadata
forces a full SHA-256 check before the existing GGUF can be reused, so modified
or corrupted bytes are not accepted merely because the sidecar still exists.
Repository, revision and GGUF filename must also match. Modelfile-only changes
therefore regenerate the Ollama registration without downloading again. Reconciliation prints the reason (source, Modelfile or missing registration); `--quiet`
suppresses repeated catalog/mode chatter for scripted actions. Use the explicit `refresh`
command to deliberately fetch new source bytes, including a moving revision such as
`latest`.

For experimental OCR definitions with remote `hf.co/...` FROM, Ollama owns the
main model blob and required vision projector in its normal model store.
`bc250-model` therefore labels the source `Ollama-managed (main+projector)` rather than pretending
there is a manager-owned source GGUF under `/var/lib/bc250-llm-server/gguf/`.
This is intentionally different from text-only local-GGUF models: preserving
only the main OCR GGUF would not provide a reliable restore path for the paired
projector on the current package runtime.

Hugging Face authentication is requested only when a manager download needs it. `HF_TOKEN` or
`--token-file PATH` is validated as the `ollama` account. Missing or rejected
tokens continue anonymously and are not persisted. Use
`BC250_HF_ANONYMOUS=1` for unattended public downloads.

## Storage and lifecycle removal

Source GGUFs remain below `/var/lib/bc250-llm-server/gguf/`. `unregister` removes the
Ollama registration/runtime Modelfile but retains manager-owned GGUF/state. `remove` also
deletes that local source/state, but only after an Ollama-backed registration is confirmed
removed; a failed `ollama rm` leaves the local source intact and returns failure.

Ollama imports model layers into one of these separate stores:

```text
/var/lib/bc250-llm-server/ollama/main
/var/lib/bc250-llm-server/ollama/task
/var/lib/bc250-llm-server/ollama/embedding
/var/lib/bc250-llm-server/ollama/agent
```

A local model can therefore consume space as both source GGUF and Ollama blob. Some newly
imported GGUF architectures also create a temporary source-hash blob plus a converted live
model layer. Normal Ollama startup pruning removes the unreferenced temporary blob;
`bc250-storage status` reports such blobs separately and `bc250-storage dedupe` ignores
them. Retaining the source GGUF makes later registration repair possible without a
redownload.

For live source/blob pairs whose bytes are identical, `bc250-storage dedupe` uses the
conservative 16 MiB XFS range while batching ranges per pair into one `xfs_io` process.
Dedupe state is stored in the schema-3 sidecar and survives normal model reconciliation.

Package-retired definitions remain source-only under `models/modelfiles-graveyard/`;
installed `retired-models.json` contains the canonical identity/paths needed for safe
cleanup. `sudo bc250-model purge-retired` previews and removes only those explicit
package-retired models, refuses uncertain or misplaced registration state, and never
targets arbitrary unmanaged operator models.

For a model you may need again, prefer:

```bash
sudo bc250-model unregister CATEGORY MODEL --yes
# later:
sudo bc250-model apply CATEGORY MODEL
```

For deliberate source deletion use:

```bash
sudo bc250-model remove CATEGORY MODEL --yes
```

Never manually purge Ollama's shared blob directory for one model. Remote OCR definitions
have Ollama-managed model/projector blobs rather than a separate manager-owned source
GGUF/state pair; lifecycle output states that distinction explicitly.

See [`../docs/COMMANDS.md`](../docs/COMMANDS.md) for every option and
[`../docs/openwebui-settings.md`](../docs/openwebui-settings.md) for current model roles.

## Runtime lane ownership

Normal mode uses main 11434, task 11435 and embedding 11437. Apply embedding
models with `sudo bc250-model apply embedding` so registration targets the dedicated
store/service. Agent 11436 is disabled at boot and runs only through exclusive
`bc250-agent-mode enter|leave`; do not register production/embedding models there.
