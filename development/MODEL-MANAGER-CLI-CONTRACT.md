# BC-250 model-manager CLI contract

Current contract for the active source tree. The explicit lifecycle semantics originate from the 0.11.3 model-manager redesign and are carried forward unless a documented defect requires change.

This document records the current greenfield model-manager command surface after the
repository-wide caller/document migration. It is the lifecycle contract that current
package callers and operator documentation are expected to follow.

## State model

`bc250 model` treats one model as three related package states:

1. **Catalog definition** — packaged `model-catalog.json` intrinsic/acquisition metadata plus
   a runtime-only Modelfile template, an operator-owned self-contained Modelfile override, or an MTP
   catalog entry. `model-profiles.json` separately owns BC-250 qualification/role policy.
2. **Manager-owned source state** — local GGUF plus `.bc250.json` provenance
   sidecar when the provider is not Ollama-managed.
3. **Runtime state** — rendered runtime Modelfile and Ollama registration when
   the model is Ollama-backed.

A single read-only inspector owns the comparison of those states. `status` and
`apply` consume that same inspection result; callers must not implement their
own path/provenance guesses.

## Public commands

```text
bc250 model list [CATEGORY]
bc250 model inspect ID [--category CATEGORY] [--json]
sudo bc250 model inspect ID [--category CATEGORY] --effective [--json]
sudo bc250 model status [CATEGORY] [SELECTION] [--online] [--verbose|--compact]
bc250 model path CATEGORY ID

sudo bc250 model apply CATEGORY [SELECTION]
sudo bc250 model refresh CATEGORY [SELECTION]
sudo bc250 model unregister CATEGORY [SELECTION]
sudo bc250 model remove CATEGORY [SELECTION]
sudo bc250 model purge-retired
```

Categories remain:

```text
production experiments task agentic embedding mtp all
```

### `list`

Catalog-only discovery. It does not inspect protected GGUF/state directories or
Ollama registration and therefore does not require root. Operator definitions
that shadow packaged definitions are labelled as overrides.

### `inspect`

Consolidated single-model metadata view. Without `--effective` it is ordinary-user-safe and combines
the package catalog's source/provider/ownership/capability facts with the BC-250 qualification profile.
For Agent models the qualification profile includes `agent_validation=static-output-contract`; this is
deliberately narrower than intrinsic `tools=true` and does not assert native Ollama `tool_calls` qualification.
`--json` is the machine-readable contract; human formatting is not a frozen parser interface.

`--effective` additionally renders runtime parameters from the actual Modelfile template and inspects
protected source/state/registration state, so it requires root. Runtime sampler values are never copied
into the profile: the rendered Modelfile remains their authority.

### `status`

Read-only installed-state inspection. It reports definition origin, verified
source/provenance state, runtime Modelfile drift, registration state and an
overall `CURRENT`, `MISSING`, `DRIFT` or `UNKNOWN` result. It requires root
because manager-owned GGUF/state directories are protected.

During the pre-1.0 greenfield phase, all active package model sources use `tracking`; the `pinned`
policy remains part of the contract for the later 1.0 stabilization step.

`--online` is opt-in. For manager-owned sources whose catalog policy is `tracking`
(`latest`, `main`, or another intentionally moving ref), it compares remote file SHA metadata with the
locally verified SHA without modifying or downloading the model. `pinned` policy is reported as pinned,
not as an update candidate. Normal output explicitly points to `--online` when upstream state has not
been checked.

`--verbose` adds catalog source repository/revision, verified local SHA-256 when
available, and resolved source/state/runtime paths. `--compact` uses the same
inspector but keeps healthy interactive views short: an ordinary fully current model
renders as `[CURRENT]`, an intentionally inactive agent-lane model renders as a short
deferred state, and non-current models retain source/Modelfile/registration detail.
The installer uses this mode so `list` remains catalog-only. Local registration discovery
is bounded, and the known-inactive agent lane is skipped during normal combined inspection;
GGUF identity/SHA verification semantics are unchanged.

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
GGUF/state is valid, then performs the same reconciliation as `apply`. For package `tracking` sources, the
newly downloaded bytes are intentionally not constrained by a stale catalog digest; their calculated SHA-256
is recorded in state. `pinned` sources continue to enforce the package-owned expected digest.

### `unregister`

Removes Ollama registration and runtime Modelfile while retaining manager-owned
GGUF and `.bc250.json` state. Download-only MTP entries cannot be unregistered.

### `remove`

Removes registration/runtime Modelfile and manager-owned GGUF/state while
retaining the catalog definition. A missing selection never means implicit
`all`; destructive scope must be selected or confirmed interactively.

### MTP explicit opt-in

Packaged MTP entries may remain `enabled = false` so they are hidden from ordinary combined
status views. Combined `apply all` / `refresh all` never select the MTP category, even with
`--include-disabled`. The interactive `bc250 model install` view is the deliberate exception for
presentation and explicit opt-in: it shows MTP with the same global indexes as Ollama models, but only
an exact MTP ID/index or numeric range may select it. Broad `all`, `recommended` and `production`
installer groups exclude MTP. Such an explicit installer selection performs the same download/verify
preparation semantics as `bc250 advanced mtp prepare [SELECTION]`; it does not register Ollama or start
llama.cpp. MTP remains download-only, so it supports source `status/apply/refresh/remove/path` but not
`unregister`.

### `purge-retired`

Purges only models explicitly present in the package retired-model catalog,
retaining the existing misplaced-registration and fail-closed protections.

## Greenfield command contract

Only the current command grammar above is supported. Current package callers, tests and
documentation must use it directly; removed pre-greenfield command forms are historical evidence,
not migration API.
