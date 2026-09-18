# BC-250 model-manager CLI contract

Current implementation target: `0.11.3-0.3`.

This document records the current greenfield model-manager command surface after the
repository-wide caller/document migration. It is the lifecycle contract that current
package callers and operator documentation are expected to follow.

## State model

`bc250-model` treats one model as three related package states:

1. **Catalog definition** — packaged or operator Modelfile / MTP catalog entry.
2. **Manager-owned source state** — local GGUF plus `.bc250.json` provenance
   sidecar when the provider is not Ollama-managed.
3. **Runtime state** — rendered runtime Modelfile and Ollama registration when
   the model is Ollama-backed.

A single read-only inspector owns the comparison of those states. `status` and
`apply` consume that same inspection result; callers must not implement their
own path/provenance guesses.

## Public commands

```text
bc250-model list [CATEGORY]
sudo bc250-model status [CATEGORY] [SELECTION] [--online] [--verbose|--compact]
bc250-model path CATEGORY ID

sudo bc250-model apply CATEGORY [SELECTION]
sudo bc250-model refresh CATEGORY [SELECTION]
sudo bc250-model unregister CATEGORY [SELECTION]
sudo bc250-model remove CATEGORY [SELECTION]
sudo bc250-model purge-retired
```

Categories remain:

```text
production experiments task agentic embedding mtp all
```

### `list`

Catalog-only discovery. It does not inspect protected GGUF/state directories or
Ollama registration and therefore does not require root. Operator definitions
that shadow packaged definitions are labelled as overrides.

### `status`

Read-only installed-state inspection. It reports definition origin, verified
source/provenance state, runtime Modelfile drift, registration state and an
overall `CURRENT`, `MISSING`, `DRIFT` or `UNKNOWN` result. It requires root
because manager-owned GGUF/state directories are protected.

`--online` is opt-in. For `@ latest` manager-owned Hugging Face sources it
compares remote file SHA metadata with the locally verified SHA without
modifying or downloading the model. Pinned revisions are reported as pinned,
not as update candidates. Normal output explicitly points to `--online` when
upstream state has not been checked.

`--verbose` adds catalog source repository/revision, verified local SHA-256 when
available, and resolved source/state/runtime paths. `--compact` uses the same
inspector but emits one state-rich line per model; the installer uses this mode
for selection so `list` remains a catalog-only operation.

### `path`

Technical read-only resolver for package scripts. It replaces the old
`resolve` verb and preserves the tab-separated path/context/draft output needed
by MTP/candidate tooling. MTP indexes remain global even when the separate TOML catalog
is viewed by itself.

### `apply`

Converges the selected model to the current catalog definition. It reuses a
verified current GGUF, repairs/replaces a drifted runtime Modelfile and creates
or repairs the Ollama registration as required. It downloads only when source
state is missing, invalid or no longer matches the catalog definition. Source
revision/checksum overrides are valid only when the complete selection contains exactly
one model, including selections from category `all`.

### `refresh`

Explicit source refresh. It re-fetches the selected source even when the local
GGUF/state is valid, then performs the same reconciliation as `apply`.

### `unregister`

Removes Ollama registration and runtime Modelfile while retaining manager-owned
GGUF and `.bc250.json` state. Download-only MTP entries cannot be unregistered.

### `remove`

Removes registration/runtime Modelfile and manager-owned GGUF/state while
retaining the catalog definition. A missing selection never means implicit
`all`; destructive scope must be selected or confirmed interactively.

### MTP explicit opt-in

Packaged MTP entries may remain `enabled = false` so they are excluded from generic
combined-catalog convergence. `bc250-fetch-mtp [SELECTION]` is the explicit operator
opt-in and dispatches to `apply mtp --include-disabled`; no catalog edit is required just
to download a candidate for a bounded llama.cpp experiment. MTP remains download-only,
so it supports source `status/apply/refresh/remove/path` but not `unregister`.

### `purge-retired`

Purges only models explicitly present in the package retired-model catalog,
retaining the existing misplaced-registration and fail-closed protections.

## Deliberate compatibility break

The old grammar is not retained as an alternate API:

```text
install             -> apply
install --refresh   -> refresh
cleanup --keep-gguf -> unregister
cleanup             -> remove
cleanup-retired     -> purge-retired
resolve              -> path
```

Common legacy/mistyped forms receive a targeted migration hint instead of raw
`argparse` output. Current package callers and public documentation are migrated to the
new grammar; old command forms remain only in explicit migration tests/hints or
historical evidence.
