# Operations and maintenance

This is the canonical operator reference for day-to-day administration. It combines the public command reference, maintenance procedures and the companion interface contract.

## Command reference

`bc250 COMMAND [ARGUMENTS...]` is the canonical appliance interface. Greenfield releases do not install per-command `bc250-*` compatibility aliases. Two deliberate CU commands remain standalone because they wrap the upstream live-routing tool.

### Public interface

| Command | Purpose |
|---|---|
| `bc250` | Canonical appliance dispatcher |
| `bc250 install` | Apply/resume appliance setup |
| `bc250 status` | Concise read-only appliance status |
| `bc250 verify` | Detailed local verification |
| `bc250 support-bundle` | Redacted support evidence archive |
| `bc250 storage` | Report/dedupe/prune package-owned storage |
| `bc250 reset` | Confirmed greenfield appliance reset |
| `bc250 model` | Model catalog and lifecycle |
| `bc250 rag` | Product RAG corpus lifecycle and ingestion |
| `bc250 ocr` | Experimental office OCR helper |
| `bc250 openwebui-setup` | Initialize/apply/check package-owned Open WebUI state |
| `bc250 ollama-profile` | Main Ollama runtime profile |
| `bc250 maintenance` | Backups, safe power/WOL and optional companion integration |
| `bc250 benchmark` | Explicit model and appliance benchmarks |
| `bc250 revalidate` | Whole-appliance qualification harness |
| `bc250 agent-mode` | Enter/leave/status exclusive Agent mode |
| `bc250 code`, `bc250 code-commit`, `bc250 gitea-review` | Optional coding-agent workflows |
| `bc250 compare-mtp`, `bc250 fetch-mtp`, `bc250 run-mtp` | Optional MTP workflows |
| `bc250-cu-live-manager` | Interactive live WGP/CU configuration |
| `bc250-40cu status` | Compact CU routing verification |
| `llm-run-diagnose` | Detailed model-run diagnostic |

Use `bc250 --help` for the grouped command list. Commands that modify host or service-owned data normally require `sudo`.

### Guided installer

Repository bootstrap:

```bash
sudo ./install [RPM-FILE-OR-DIRECTORY]
```

The bootstrap does only two things: local RPM install/update, then
`exec bc250 install`. Fedora update policy belongs to the packaged installer. The RPM itself does not run the appliance installer
from `%post`.

Packaged orchestrator:

```bash
sudo bc250 install
sudo bc250 install --models-only
sudo bc250 install --owui-token-file FILE
```

For an RPM upgrade with an existing Open WebUI database, RPM `%pre` unconditionally requests OWUI stop, proves `ActiveState=inactive`, and holds its boot drop-in before the new Quadlet can restart. `bc250 install` is the supported continuation: it verifies the stopped-state rollback snapshot before re-enabling/starting the new image. See `OPERATIONS.md` for restore steps.

Normal mode prints a setup plan covering root growth, Fedora/package/Ollama,
TTM/swap, 40-CU, storage headroom, models, Open WebUI and reboot state; it applies
only pending work where practical and
combines kernel update plus TTM configuration before the primary reboot. After
that reboot CU routing remains an explicit operator step through the live manager. The base
Open WebUI Quadlet is intentionally dormant across the primary reboot; after
all active role base models plus task/Jina defaults are reconciled, the installer adds
its small `[Install]` drop-in,
reloads systemd and starts Open WebUI. CU routing does not require a package-managed reboot; configure it separately with the live manager after the core appliance is ready.

The installer ensures every base model required by active package-owned Open WebUI
roles, plus the task and embedding defaults, without printing the full catalog. Agent models are
optional add-ons and are not downloaded by baseline reconciliation. Fully unchanged required models are summarized
by category; downloads or repairs remain verbose. Model management temporarily enters exclusive
Agent mode when explicitly managing an Agent add-on and restores normal mode afterward. It then presents
compact state for other production/experiment/task/agent/embedding extras. Fully current rows collapse to `[CURRENT]`, and the intentionally inactive agent
lane is shown as deferred without waiting on that stopped Ollama instance. Stage 7 also shows a
**read-only, non-indexed MTP inventory** so fetched/current standalone llama.cpp artifacts are visible,
but MTP is not part of the generic picker and is never fetched by installer convergence. Use
`bc250 fetch-mtp ID` explicitly when preparing one.
Use global indexes, ranges, exact names, `recommended`, `production` or `all`; Enter skips
optional extras only.
For non-TTY runs use `BC250_MODEL_SELECTION`. The original stdin mode is retained
across transcript PTY creation, so unattended runs never become interactive by
accident. `BC250_HF_ANONYMOUS=1` forces anonymous Hugging Face downloads. The model manager
asks for an optional Hugging Face token only when a download is actually needed;
a no-op update with current model sources does not ask for one.
`BC250_UPDATE_OLLAMA=1` explicitly reinstalls the package-qualified Ollama payload. The completion summary separates
core installation/verification from package-owned Open WebUI state and reports the latter as
`APPLIED + VERIFIED`, `SKIPPED`, or `RETRY REQUIRED`; a nonfatal Open WebUI setup problem is no
longer hidden behind an unconditional whole-install success message. Completion then prints a plain
`OVERVIEW` followed by an amber `NEXT STEPS` block for CU routing, model reconciliation and validation.

### Models

The model manager deliberately separates read-only discovery/state inspection from
mutating lifecycle operations:

```bash
bc250 model list [CATEGORY] [--all] [--source PATH] [--modelfile-dir PATH]
sudo bc250 model status [CATEGORY] [SELECTION] [--online] [--verbose|--compact]
bc250 model path CATEGORY ID

sudo bc250 model apply CATEGORY [SELECTION] [OPTIONS]
sudo bc250 model refresh CATEGORY [SELECTION] [OPTIONS]
sudo bc250 model unregister CATEGORY [SELECTION] [--host HOST[:PORT]] [--destination PATH] [--yes]
sudo bc250 model remove CATEGORY [SELECTION] [--host HOST[:PORT]] [--destination PATH] [--yes]
sudo bc250 model purge-retired [--yes]
```

Categories are `production`, `experiments`, `task`, `agentic`, `embedding`, `mtp`
and `all`. Legacy aliases are intentionally not accepted. Selections accept a full
model name, displayed global catalog index, comma list, range such as `0,2-4`,
`recommended`, `production`, or `all`. Prefer full names in long-lived automation.

#### Discovery and state

`list` is catalog-only and does not require `sudo`. It shows definitions and stable
global indexes without probing protected GGUF/state or Ollama registration state. A
category filters the same catalog without renumbering it, including the separate MTP
TOML catalog. `list all` includes enabled MTP entries; add `--all` to include disabled
MTP definitions.

`status` is the read-only runtime inspector and normally runs with `sudo` because
manager-owned GGUF/state trees are protected. It evaluates the same state contract that
`apply` consumes: source presence and checksum/provenance validity, whether the selected
definition differs from the rendered runtime Modelfile, registration state on the
category-owned Ollama lane, and the recommended next action. When upstream state has not
been checked, normal output points to `--online`. `--verbose` adds source repository,
revision, verified local SHA-256 when available, and resolved paths. `--compact` uses the
same inspection contract but keeps healthy interactive views short: ordinary fully-current
entries render as `[CURRENT]`, inactive agent entries render as deferred, and non-current
entries keep the detailed source/Modelfile/registration reason. Local registration probes are
bounded; the known-inactive agent lane is skipped during normal status-all inspection.
`--online` checks moving upstream revisions such as `latest` without downloading or modifying
the local model.
Pinned revisions are reported as pinned rather than mislabelled as needing an update.
When normal mode is active, the agent API is intentionally stopped; full
`status agentic MODEL` therefore may show registration as unavailable/UNKNOWN. Read-only status
does not switch runtime modes merely to inspect it.

`path` is the narrow machine-readable resolver used by package tooling. It prints the
resolved source path and MTP context/draft metadata for one exact model and is not a
lifecycle action.

#### Lifecycle operations

`apply` means **make the selected model match the current catalog definition**. `all` has
two different positions by design: the category `all` means the combined catalog, and the
selection `all` means every eligible entry. Therefore `sudo bc250 model apply all` displays
the combined catalog and prompts, while `sudo bc250 model apply all all` explicitly selects
every eligible non-MTP model. It reuses
a verified existing GGUF when source identity and recorded state still match, repairs
Modelfile/registration drift without an unnecessary download, and downloads only when the
source is missing or invalid. Agentic selections temporarily enter exclusive agent mode
and restore normal mode afterward.

`refresh` is the explicit source-update/reinstall operation. It deliberately refetches
source bytes and then performs the same reconciliation as `apply`. Use it when
`status --online` reports a changed moving source or when you intentionally want to
replace otherwise valid cached bytes. It is not an automatic side effect of `apply`.

`unregister` removes the Ollama registration and rendered runtime Modelfile while
retaining manager-owned GGUF plus `.bc250.json` provenance/state where those exist. It is
the correct operation when you want to free the Ollama registration/store reference but
retain verified source for a later fast `apply`. Remote OCR sources are Ollama-managed and
therefore have no separate package-local GGUF/state pair to retain.

`remove` removes the registration/runtime Modelfile and then manager-owned GGUF/state. A
failed registration removal leaves local source intact and returns failure. Destructive
commands preview their effects and require confirmation unless `--yes` is supplied; an
omitted selection never silently turns into destructive `all`. If a model was applied
with `--host` or `--destination`, pass the same override to `unregister`/`remove`.

`purge-retired` is separate from ordinary removal. It targets only models named in the
package retirement catalog, previews canonical identity/registration/source state, and
fails closed on unavailable or misplaced registration state. It never selects arbitrary
unmanaged operator models.
Retired/non-user-visible native registrations are lifecycle residue, not active Open WebUI
base-model desired state. They remain hidden from ordinary users and can be reported or removed
through the model lifecycle without making an otherwise converged Open WebUI baseline appear
misconfigured.

#### Apply / refresh options

Common options for `apply` and `refresh`:

- `--quiet`: suppress repeated catalog/topology-transition chatter for scripts;
- `--revision REVISION`: one-model source revision override;
- `--sha256 DIGEST`: require an exact downloaded-file checksum;
- `--host HOST[:PORT]`: override the target Ollama API;
- `--destination PATH`: override the manager-owned GGUF root;
- `--min-free-bytes BYTES`: require free space before downloading;
- `--token-file PATH`: read a Hugging Face token from a non-empty regular file that is not group/world accessible (normally mode `0600`);
- `--include-disabled`: allow disabled MTP entries to be selected for an explicit `mtp` category operation; combined `apply all` / `refresh all` never include MTP;
- `--modelfile-dir PATH`: add a Modelfile search directory; the installed operator overlay
  `/etc/bc250-llm-server/models.d/` rejects visible regular files without a `.Modelfile` suffix
  so typos cannot disappear silently; the error lists offending operator-owned files and tells
  the operator to move/rename/remove them before rerunning `sudo bc250 install`;
- `--source PATH`: use another MTP TOML catalog.

Remote experimental `hf.co/...` definitions do not accept local-GGUF revision/checksum/
destination overrides because Ollama owns their model/projector blobs. Hugging Face
authentication is requested only when a manager download actually needs it.

#### MTP lifecycle

MTP entries are download-only inputs for a standalone opt-in llama.cpp runtime and are intentionally
outside generic combined convergence. The installer displays their read-only operational state but
never exposes them as normal selectable indexes; `apply all` / `refresh all` never select MTP even
when `--include-disabled` is supplied. Use the explicit `mtp` category or the
opt-in helper to select one:

```bash
bc250 model list mtp --all
sudo bc250 fetch-mtp qwen3.5-9b-mtp
sudo bc250 model status mtp qwen3.5-9b-mtp --include-disabled --verbose
LLAMACPP=/opt/llama.cpp/build/bin/llama-server bc250 compare-mtp qwen3.5-9b-mtp
```

`bc250 run-mtp` drains resident Ollama models before launching standalone llama.cpp. Direct operator
runs restore the exact pre-run residency set when llama.cpp exits; `bc250 compare-mtp` uses the
qualification `drain-only` policy and intentionally leaves Ollama cold after evidence capture.

Running `sudo bc250 fetch-mtp` without a selection shows the disabled experiment entries
and prompts for one. It maps to `bc250 model apply mtp --include-disabled`; the explicit
helper is therefore safe to use without editing `/etc/bc250-llm-server/mtp-models.toml`.
`refresh mtp ... --include-disabled` deliberately re-fetches source bytes. MTP has no
Ollama registration, so `unregister mtp` is invalid; `remove mtp ID` removes only the
manager-owned source/state after confirmation.

Keep `enabled = false` for candidates that should remain hidden from ordinary combined status
views. The combined mutation path still excludes the MTP category regardless of that flag; setting
an entry true is an operator visibility policy choice, not a qualification or promotion signal.

The manager records schema-3 source/model/category identity plus SHA-256 and file stat
metadata. Unchanged stat metadata can use the validated fast path; changed or legacy state
forces a full checksum before reuse. Source repository, revision and GGUF filename must
also match. This is what lets a Modelfile-only change re-register from retained bytes
without silently accepting modified source data.

### Documents / RAG lifecycle

```bash
sudo bc250 rag init public COLLECTION
sudo bc250 rag prepare-batch public COLLECTION --dry-run
sudo bc250 rag prepare-batch public COLLECTION
sudo bc250 rag review public COLLECTION
sudo bc250 rag validate public COLLECTION --include-working
sudo bc250 rag activate public COLLECTION --all-ready
sudo bc250 rag status
sudo bc250 rag ingest --token-file FILE [--prune]
```

The default root is `/srv/bc250-documents`. Each collection has `inbox/german`, `inbox/french`,
`inbox/bilingual`, `sources`, `working`, `active` and `superseded`. Agent-assisted batch preparation is
local-only and stops at `working/`; reviewed Markdown must be explicitly activated before ingestion. Native agent thinking is separated from final Markdown through Ollama `/api/chat`; truncated, empty, fenced or reasoning-contaminated final content is rejected. Scanned PDFs and documents above the safe single-pass limit are intentionally reported as deferred OCR/manual chapter-split work rather than generic failures or guessed.

`validate` checks provenance, review state, document identity, active revision conflicts and obvious native-reasoning marker contamination. `ingest` sends
only `active/*.md` through the existing incremental Open WebUI knowledge API. The API key is never packaged;
`--token-file` must be a non-empty private regular file. Use `--prune` only when stale remote documents should
be removed. The former compatibility interface is removed; new and existing corpora use the product lifecycle above.

### Experimental OCR

```bash
bc250 ocr list
sudo bc250 ocr install glm|ovis
bc250 ocr show glm|ovis
bc250 ocr test glm|ovis IMAGE
```

OCR models stay in the normal `experiments` category and main Ollama instance;
there is no OCR daemon or separate model store. GLM/Ovis use remote `hf.co/...`
imports so Ollama can manage the required vision projector; unlike text-only
models, their source files therefore live in the Ollama blob store rather than
`/var/lib/bc250-llm-server/gguf/`. The helper tests one image and
prints extracted text/Markdown for comparison. GLM is the measured fidelity
leader and OvisOCR2 remains the faster structured-document alternative. Test DE/FR/EN
letters, invoices, forms and table-heavy scans before using OCR output for RAG.

The RPM statically owns `ollama.service` on `11434`, `ollama-task.service` on `11435`,
`ollama-embedding.service` on `11437` and exclusive `ollama-agent.service` on
`11436`. Normal mode requires main + task + embedding. `bc250 model` switches
modes automatically for package-managed agent registration and restores normal
mode afterwards; `bc250 agent-mode enter|leave` is the explicit runtime switch.
Each lane keeps its own model store. Revision/checksum overrides still require
one selected model.

See [`../MODELS.md`](../MODELS.md) for model roles/swapping and
[`../models/README.md`](../models/README.md) for the detailed Modelfile contract.


### Storage

```bash
sudo bc250 storage status
sudo bc250 storage dedupe [--yes]
sudo bc250 storage prune-sources [--yes]
```

Detailed `status` accounting requires elevated access to the protected model
stores; an unprivileged invocation reports that accounting as unavailable rather
than returning false zeroes. Privileged status distinguishes verified pairs whose
dedupe state is recorded from legacy/unrecorded live pairs without claiming the latter
are physically undeduplicated. Unreferenced source-hash Ollama blobs are reported
separately and excluded from dedupe targets; normal Ollama startup pruning is expected
to remove those transient imports. `dedupe` requires XFS with `reflink=1`; it verifies
manager state/source hashes and uses kernel-verified 16 MiB `FIDEDUPERANGE` sharing
while retaining both paths. Successful pairs are recorded in schema-3 sidecars and
unchanged recorded pairs are skipped on later runs. Normal interactive use requires
typing `DEDUPLICATE`; `--yes` is for deliberate automation. Compare `df` before
and after because `du` may still account a shared extent to both logical files.

`prune-sources` is a separate, destructive alternative: it hashes both source and
registered Ollama blob before removing an offline manager-owned GGUF/state pair,
never MTP download-only sources.

### Runtime profiles

Memory/TTM and swap safety profiles are package-owned implementation details reconciled by `bc250 install`. Operators normally inspect their effects with:

```bash
sudo bc250 status
sudo bc250 verify
free -h
swapon --show
```

The package defaults to 2 GiB zram plus a 16 GiB disk swap safety margin. `bc250 verify`
checks the active swap set, so an initialized `/dev/zramN` that is absent from `swapon --show`
is reported as not active swap. Verification also parses the actual failed-systemd-unit rows
rather than treating the command exit code as proof that no units failed. Package-managed disk-swap
resize/removal is fail-closed: if active-swap state cannot be read or an active swap file cannot be
deactivated, the helper refuses to unlink or replace its backing file. The main Ollama runtime remains explicitly selectable:

```bash
bc250 ollama-profile status
sudo bc250 ollama-profile balanced
sudo bc250 ollama-profile max-context
sudo bc250 ollama-profile reset
```

### CU routing

Normal setup and verification deliberately use only two operator commands:

```bash
sudo bc250-cu-live-manager
sudo bc250-40cu status
```

The live manager owns board-specific WGP selection, saved masks and boot restore. The
`bc250-40cu` wrapper intentionally exposes only `status`; kernel/RADV CU counts are
diagnostic and are not the live-routing authority. The package no longer builds or
installs a replacement AMDGPU module.

See [`HARDWARE.md`](HARDWARE.md) before changing GPU routing.

### Verification and monitoring

```bash
sudo bc250 status
sudo bc250 support-bundle
sudo bc250 verify
sudo bc250 verify --summary
sudo bc250 verify --owui-token-file FILE
sudo bc250 openwebui-setup status --verbose --owui-token-file FILE
RUN_MODEL_TESTS=1 sudo bc250 verify
sudo llm-run-diagnose --no-load
MODEL=MODEL_NAME LOAD_SECONDS=120 NUM_PREDICT=2000 sudo llm-run-diagnose
sensors
bc250 benchmark generation
sudo bc250 revalidate start
sudo bc250 revalidate start --skip-owui
sudo bc250 revalidate status
sudo bc250 revalidate status --raw  # machine-readable key=value state
sudo bc250 revalidate abort
sudo bc250 revalidate cleanup
```

`bc250 status` derives `normal`, `degraded`, `stopped` and exclusive `agent` topology from the same
classifier used by `bc250 agent-mode status`; a concise `Overall` / `Runtime mode` summary appears
near the top. It does not call a machine "normal" merely because the agent unit is inactive.
Unexpected degraded normal topology also prints the supported convergence command
`sudo bc250 agent-mode normal` so the status output is directly actionable.
If the optional reboot diagnostic helper is absent, the reboot recommendation is reported as
`not checked` rather than as uncertain appliance health. `bc250 status` also distinguishes an active
Open WebUI systemd unit from HTTP application readiness, queries the active Ollama lane's
`/api/version` endpoint rather than inferring the server version from CLI output, and reports current
`/api/ps` residency per Ollama lane so memory-sensitive investigations can see what is actually loaded.

`sudo bc250 support-bundle` creates a mode-0600 timestamped archive under
`/var/lib/bc250-llm-server/support/` by default. It reuses existing status, verifier,
maintenance, topology and CU commands, adds bounded resource/failure evidence, and writes
`manifest.json` plus `SHA256SUMS.txt`. Individual command captures are bounded by
`BC250_SUPPORT_CAPTURE_TIMEOUT` (20 seconds by default) and record `TIMEOUT` distinctly. Before
reporting success the command validates the checksum set, creates the archive, reopens it and validates
the archived checksum set again. It intentionally excludes OWUI credentials, prompts, chat content,
uploaded document contents, database rows, identity SQL and backup contents. Use `--output-dir DIR`
when the archive should be written elsewhere.

`bc250 revalidate` harness v4.8 is the root-only systemd-backed package
qualification workflow. A full
`sudo bc250 revalidate start --owui-token-file FILE` follows a compact six-phase
dashboard. Use `--skip-owui` only for an explicitly partial Open WebUI coverage
run. The token file must be a protected readable regular file and is authenticated
before run state is created. The worker remains systemd-owned; Ctrl-C detaches and
`--detach` returns immediately. The dashboard reports stage elapsed time, worker
state and the age of the last real progress event rather than treating a periodic
heartbeat as progress. Run completion is independent from coverage: if all required
phases finish normally, the run is `completed` even when the optional Agent is not
installed and coverage is PARTIAL.
Harness v4.8 also surfaces non-failing observations under a separate `Diagnostics`
section. This includes non-severe context truncation, a MemAvailable minimum below the
512 MiB tight-headroom diagnostic threshold while still above the unchanged 128 MiB hard
floor, and accepted use cases that reach their generation output budget. These diagnostics
do not weaken or replace the existing infrastructure/quality gates. Intermediate successful phases use lighter
checkpoints while high-value topology/restoration boundaries retain full snapshots.

Revalidation tests only promoted package defaults. Configuration-decision work
(`num_batch`, embedding batch, chunk-min, `RAG_SYSTEM_CONTEXT`, thinking-policy,
keepalive, kernel/governor and experimental-model A/B) belongs to explicit
benchmark/diagnostic commands. The preflight also requires a parseable live SPI/WGP
routing table with no unexpected `D!` cells. If a saved `BC250_WGP_MASKS` profile is
configured, the four live SPI row masks must match it exactly; no saved profile is a valid
optional state. Intentionally unselected `--` cells are not faults, and health does not
hard-code `40/40`.

Benchmark quality exit `3` is recorded and nonfatal. Other benchmark/helper errors
are infrastructure failures and enter the single top-level restoration/finalization
path. Authenticated packaged Open WebUI qualification accepts
`--owui-token-file FILE` and now exercises both the production DE↔FR role/filter path
and the packaged RAG path. The direct translation stage pins the promoted 2048-token
budget; the Open WebUI stage sends source text through the real production role IDs rather
than rebuilding the Filter contract in the harness. Final bundles remain under
`/var/lib/bc250-llm-server/revalidation/results/`; each bundle now includes a small
`manifest.json` and `SHA256SUMS.txt` covering its evidence files. Expected nonzero raw
`systemctl status` results are annotated when the agent lane is intentionally inactive in
normal mode. Completed work remains inspectable until `cleanup` or a later `start`.

`bc250 revalidate status` is human-readable by default and reports the exact installed package NEVRA
separately from the target source version and harness identity. It separates the installed
harness/worker state from the recorded last-run result; `--raw` preserves the
key/value form for scripts. `abort` requests termination of the current systemd-owned
run through the harness recovery/finalization path; `cleanup` removes completed work
state after its result bundle is no longer needed. Neither command is a substitute
for ordinary service stop/start management. `bc250 status` is a short overview including CPU
topology/power-state exposure, RAM, memory pressure, zram, disk swap, swappiness
and appliance storage. `bc250 verify` is the detailed pass/fail check and accepts
`--owui-token-file FILE` for the authenticated package-owned Open WebUI drift check.
Verifier totals report `ok / warn / fail / skipped`; optional/unavailable checks are never counted
as passes or failures, and their individual `[SKIP]` line explains why they did not run.
The detailed verifier also checks that every active package-owned Open WebUI role has its
base model registered on the main Ollama lane. `watch -n 1 sensors` can refresh
second by default; use `--once` only when a single sample is useful. Verification includes kernel/module alignment, CU state, Ollama version,
internal Ollama listener/firewall policy, service health and recent Vulkan/AMDGPU failure patterns. a remote `curl -f http://SERVER_IP/` check
runs on a client; `HTTP_PORT` changes its expected web port.

Every benchmark invocation writes one isolated result directory containing canonical
`results.jsonl`, `summary.json`, `summary.txt`, `meta.json` and copied deterministic
fixtures. Categories with a useful table also write `results.csv`. Existing non-empty
output directories are rejected; use `--output-dir DIR` to select a path.

Canonical public benchmark commands are explicit; there is no commandless generation
default and no legacy alias layer:

```bash
bc250 benchmark generation --profile compare MODEL...
bc250 benchmark generation --profile edge --mode production MODEL...
bc250 benchmark generation --profile thermal MODEL...
bc250 benchmark generation --deep-context MODEL...
bc250 benchmark generation --profile thermal --sustained-seconds 180 MODEL...
bc250 benchmark embeddings [MODEL ...]
bc250 benchmark ocr [MODEL ...]
bc250 benchmark task [MODEL ...]
bc250 benchmark usecase [MODEL ...]
bc250 benchmark translation [--think auto|true|false] [MODEL ...]
bc250 benchmark rag-cycle EMBED_MODEL ANSWER_MODEL
bc250 benchmark rag-quality --think true [EMBED_MODEL ANSWER_MODEL]
bc250 benchmark rag-quality --think false [EMBED_MODEL ANSWER_MODEL]

sudo bc250 agent-mode enter
bc250 benchmark agent MODEL --ollama-url http://127.0.0.1:11436
sudo bc250 agent-mode leave
# explicit idempotent normal-topology convergence/recovery alias:
sudo bc250 agent-mode normal

bc250 benchmark concurrency MAIN_MODEL EMBED_MODEL
bc250 benchmark num-batch MODEL [MODEL ...]
bc250 benchmark owui-translation --token-file FILE
bc250 benchmark owui-rag MODEL --token-file FILE
bc250 benchmark owui-embedding-batch --token-file FILE
bc250 benchmark owui-chunk-min MODEL --token-file FILE
sudo bc250 benchmark owui-system-context MODEL --token-file FILE
```

Open WebUI benchmark `--token-file` inputs must be non-empty regular files with no
group/world access (normally mode `0600`), matching the package credential-file boundary.

The Open WebUI tuning commands are explicit experiments: they save the observed
package-owned setting, change only the named benchmark setting, use temporary
knowledge/file state, and restore the original value. Restoration failure is an
infrastructure failure. Routine revalidation does not run these A/B sweeps.

For `owui-rag`, `MODEL` can be either an exact active Open WebUI preset ID or a raw Ollama
base model that maps to exactly one active preset. Resolution happens through authenticated
Open WebUI metadata before temporary benchmark knowledge/upload state is created. Ambiguous
or unknown base-model selections fail early and report matching/valid preset IDs rather than
falling through to a generic Open WebUI `Model not found` response.

Generation and coexistence reporting emphasizes resident size, minimum
`MemAvailable`, swap start/peak/end/delta, temperature and request outcomes. Generation
also records completion-integrity state, effective local Ollama runtime/KV evidence when
available, current CU status and best-effort kernel GPU-error evidence. `--deep-context`
adds approximate 4K/16K targets with actual `prompt_eval_count` as the authority;
`--sustained-seconds` makes the thermal lane continue to a minimum elapsed time. VRAM/GTT
remain diagnostic Vulkan counters and must not be interpreted as independent additive
memory pools on the BC-250. See [`../docs/BENCHMARKING.md`](../docs/BENCHMARKING.md)
for result schema, category contracts and the package-pinned Ollama request policy. The installed copy is
`/usr/share/doc/bc250-llm-server/docs/BENCHMARKING.md`.

### Open WebUI setup

```bash
sudo bc250 openwebui-setup init
sudo bc250 openwebui-setup init --token-file FILE
sudo bc250 openwebui-setup init --owui-token-file FILE  # alias
OWUI_API_KEY=TEMPORARY_ADMIN_KEY sudo -E bc250 openwebui-setup apply
bc250 openwebui-setup status
sudo bc250 openwebui-setup status --token-file FILE
OWUI_API_KEY=TEMPORARY_ADMIN_KEY sudo -E bc250 openwebui-setup status
sudo bc250 openwebui-setup save-key --token-file FILE
```

`init` can create the first administrator, sign in an existing administrator or
use a protected administrator API-key file. The guided installer exposes the same
choice and automatically uses the verified package credential at
`/var/lib/bc250-llm-server/secrets/openwebui-admin.key` when available. An explicit protected token file overrides it. It applies the package-owned main/task provider, dedicated embedding, task/RAG, reviewed
package-owned Open WebUI Functions and additive model-preset baseline. The package also owns the
persisted local/offline application policy that matters to the appliance contract: Arena is disabled,
external OpenAI/direct/code-execution/interpreter/memory/community-sharing features remain disabled,
and upload count/size/extension limits are converged through supported Open WebUI APIs. During the
pre-v1 testing phase both normal Ollama providers are unrestricted and the raw production/task model
overrides are visible, so installed main/task models can be selected directly for comparison. Curated
Office roles remain the supported product paths. `status` verifies those persisted values, testing
visibility/tool-policy metadata, package Function source/state and package-owned preset fields needed
by the selected production translation contract. The optional maintenance API key is persisted only when the operator requests it, at the root-only package credential path; token contents are never printed. The persisted credential is a real Open WebUI `sk-...` API key, not the temporary JWT returned by sign-in/signup. Existing API keys are reused instead of rotated; an absent key is created through the supported API-key endpoint after enabling API-key support. Other temporary credentials/tokens are not persisted by the package. Unrelated operator models, users, prompts and knowledge are not
synchronized away. RPM upgrades that cross an Open WebUI version with existing state hold OWUI
startup until the guided installer has produced and verified the stopped-state migration rollback
archive. See [`OPERATIONS.md`](OPERATIONS.md) for archive semantics and restoration.

Agent mode is separate from Open WebUI:

```bash
bc250 agent-mode status
sudo bc250 agent-mode enter
sudo bc250 agent-mode leave
sudo bc250 agent-mode normal
```

Entering agent mode stops main/task/embedding and starts only the 11436 coding
backend; `leave` restores normal mode. Open WebUI remains reachable, but its persisted catalogue may
still list normal office roles while their backends are intentionally unavailable. `normal` is an
idempotent convergence alias for the same restoration path and is useful when repairing an unexpected
partial-normal topology.

The Open WebUI `/api/chat/completions` OpenAI-style adapter is not an advertised
external BC-250 compatibility contract. Device attribution found that root `max_tokens` is not a
reliable Ollama cap and that reasoning-token / length-finish metadata can be misleading. Package-owned
callers use native nested `options.num_predict` when a hard generation cap is required; see
[`OPENWEBUI.md`](OPENWEBUI.md) for the precise compatibility boundary.

### Maintenance

```bash
sudo bc250 maintenance setup [--defaults]
sudo bc250 maintenance status
sudo bc250 maintenance contract
sudo bc250 maintenance companion {status|enable}
sudo bc250 maintenance backup-export {status|enable}
sudo bc250 maintenance request-shutdown
sudo bc250 maintenance run {backup|prune|all}
sudo bc250 maintenance clean-cache
sudo bc250 maintenance disable
```

`request-shutdown` is the public operator command. When it is invoked over an
interactive SSH session, that session is protected activity and the request should
defer; normal output identifies a local protected SSH connection without printing peer
address details. `companion enable` prints a restricted key whose internal forced command
exempts only its own authenticated SSH connection; the internal command is not a
general operator interface.

The full installer presents local maintenance and Raspberry Pi/companion integration as
separate optional decisions after core verification. Local maintenance can be configured
independently. Both top-level choices remain optional/default-No, and Pi/companion setup remains
separate. Selected setup receives
post-configuration checks. `setup --defaults` enables verified local
backups only. Manual maintenance runs show
only the current systemd invocation instead of a historical journal tail. Timer status uses
`last_scheduled=` so a successful manual run is not confused with timer history. Upload
pruning preflights the protected Open WebUI credential before starting its unit; a
missing/placeholder key fails with the active age/ceiling/dry-run policy and never
prints the credential. `clean-cache` requires confirmation and removes only rebuildable
Hugging Face cache, dangling Podman images and old **system-wide** journal archives;
model and Open WebUI data are retained. Interactive setup can also configure dry-run
upload pruning, model warm-up and an after-hours power action. `companion enable`
prepares restricted SSH :22 access for the stable safe-shutdown request and keeps
HTTP :80 as the office-readiness endpoint; it does not expose internal Ollama/UI
ports. `backup-export enable` is optional and requires `/usr/bin/rrsync` from the
Fedora `rsync-rrsync` package. Configuration is stored in root-readable
`/etc/bc250-llm-server/maintenance.env`. See [`OPERATIONS.md`](OPERATIONS.md)
and [`OPERATIONS.md`](OPERATIONS.md).

### Coding and experiments

```bash
bc250 code MODE INPUT [OUTPUT] [TASK...]
bc250 code-commit [--yes]
bc250 gitea-review OWNER/REPOSITORY PR_NUMBER [--output FILE] [--post]
LLAMACPP=/opt/llama.cpp/build/bin/llama-server bc250 compare-mtp MTP_ID
LLAMACPP=/opt/llama.cpp/build/bin/llama-server bc250 run-mtp MTP_ID
```

`MODE` is `generate`, `refactor`, `review`, `document`, `test` or `commit`.
For file-producing `generate`, `refactor` and `test` modes, and for the structured `commit` mode,
`bc250 code` fails closed when the final answer is wrapped in an outer Markdown code fence. It does
not silently strip the fence because that would hide a model output-contract failure. `review` and
`document` continue to allow Markdown.

`CODING_AGENT_MODEL` selects an installed agentic model; `OLLAMA_HOST`/`OLLAMA_URL`
override its endpoint, and `CODING_AGENT_NUM_PREDICT` overrides the positive output
token budget (default 3072). `bc250 code` uses `/api/chat` with `think:true` and writes
only terminal non-empty `message.content`. It returns `3` and leaves an existing output
file unchanged if completion is nonterminal, stops at `done_reason=length`, or final
content contains literal reasoning markers. Coding helpers do not stage, push, approve
or merge without the command's explicit local action.

Prepare a candidate first with `sudo bc250 fetch-mtp ID`; the explicit helper exposes
the packaged disabled experiments without making them part of normal convergence.

`bc250 compare-mtp` is a controlled same-target qualification helper: it starts the
same GGUF through the same external llama.cpp build and runtime settings first with
MTP disabled, then with `draft-mtp` enabled. `NUM_PREDICT` and `PROMPT` may override
the bounded completion probe. The result bundle records throughput, terminal
completion integrity, draft accepted/proposed counts and acceptance percentage,
minimum available memory, swap growth, model/source identity, llama.cpp identity and
relevant kernel/GPU faults. Missing MTP draft-acceptance telemetry is insufficient
qualification evidence rather than inference corruption. Use `bc250 benchmark` for
category quality/correctness comparisons. MTP requires a compatible external
llama.cpp server binary through `LLAMACPP`; `PORT`, `CTX`, `DRAFT_N_MAX` and optional
`UBATCH` override runtime values. When supported, the runner passes `--cache-ram 0`
and `--no-cache-idle-slots` to avoid shared serialized prompt-cache state and its RAM
reservation.

### Reset / package removal

```bash
sudo bc250 reset [--yes]
```

The greenfield reset removes BC-250-owned runtime state, profiles, official Ollama
and verified CU changes after dedicated confirmation while preserving
`/srv/bc250-documents`. It does not reconstruct historical host ownership, roll
back Fedora upgrades or shrink filesystems. Ordinary
`dnf remove bc250-llm-server.x86_64` retains persistent data. Read
[`UNINSTALL.md`](UNINSTALL.md) first.

### Installed documentation and important paths

The RPM installs operator documentation under:

```text
/usr/share/doc/bc250-llm-server/
```

Start with `README.md`, `TLDR.md`, `docs/OPERATIONS.md`, `MODELS.md` and
`docs/FILESTRUCTURE.md`. Important live paths are `/etc/bc250-llm-server/` for package
configuration, `/var/lib/bc250-llm-server/` for manager/runtime state,
`/var/lib/bc250-llm-server/revalidation/results/` for final revalidation bundles, and
`/var/log/bc250-llm-install.log` for the guided-installer transcript.

## Office maintenance

Maintenance is optional and disabled by the RPM. It is designed to preserve
local privacy, bound storage growth and avoid unnecessary power use on a small
office appliance.

### Fast safe setup

```bash
sudo bc250 maintenance setup --defaults
sudo bc250 maintenance run backup
sudo bc250 maintenance status
```

This enables verified local configuration and identity backups only. It does
not delete uploads, warm a model, configure Wake-on-LAN or schedule a power
action.

For those optional choices, use the guided setup:

```bash
sudo bc250 maintenance setup
```

A full interactive `sudo bc250 install` presents local BC-250 maintenance and Raspberry
Pi/companion integration as separate optional decisions after core verification. Local
maintenance can be configured independently; Both top-level choices remain optional/default-No, and Pi/companion setup remains separate. Existing
local maintenance can be left unchanged explicitly. Selected setup is verified before the
installer finishes. The companion path deliberately uses only office HTTP :80 and
restricted SSH :22; Wake-on-LAN itself does not require a host firewall port.

Re-running setup updates the existing private configuration. Disable all
maintenance and power timers without deleting data with:

```bash
sudo bc250 maintenance disable
```

### Backups and privacy

`backup-config` uses SQLite's online backup API, verifies integrity and writes a
SHA-256 sidecar. It includes Open WebUI accounts, settings and chats but excludes
bulky uploads, vector data and caches. It is therefore **not a complete RAG
backup** and cannot restore an ingested document library by itself. `backup-users` is a selective identity
export and contains password hashes, API keys and access-control data. The package maintenance credential
`/var/lib/bc250-llm-server/secrets/openwebui-admin.key` is separate root-only appliance state: it is not
placed in config/users backups or support/revalidation evidence and must be re-established separately if needed.

Backups under `/var/backups/bc250-llm-server` remain local by default. Treat
them as confidential recovery points, not protection against theft or disk
failure. Optional Pi export can be prepared later without changing the backup
format or using an Open WebUI API key:

```bash
sudo bc250 maintenance backup-export status
sudo dnf install rsync-rrsync       # only if export is actually wanted
sudo bc250 maintenance backup-export enable
```

The export uses read-only `/usr/bin/rrsync` over the same restricted SSH :22
path. It exposes only the normal config/users backup directories, never rollback
data or `/etc/bc250-llm-server/maintenance.env`. Private SSH keys stay on the Pi.
The package reserves the export group for stable directory permissions, and the
backup producers preserve those directory modes on every run. Until the export
account is explicitly enabled, the reserved group has no members and newly published
artifacts remain private `0600`; after enablement they are published `0640`.

Before upgrading Open WebUI or moving the complete instance, take a stopped
filesystem snapshot. On a package upgrade with an existing Open WebUI database, RPM `%pre`
unconditionally requests `open-webui.service` stop, proves `ActiveState=inactive`, and removes its
boot-enablement drop-in before the new Quadlet payload or a later daemon-reload can make the new image restart-eligible. The automatic
RPM-migration snapshot uses the same ownership, ACL and xattr-preserving tar semantics before
the new image is allowed to start:

```bash
sudo systemctl stop open-webui.service
sudo tar --xattrs --acls --numeric-owner -C /var/lib \
  -czf /ENCRYPTED-BACKUP/open-webui-full-$(date +%F).tar.gz open-webui
sudo systemctl start open-webui.service
```

For RPM migrations the verified automatic archive and `.sha256` sidecar are written
under `/var/backups/bc250-llm-server/rollback/openwebui/`. To restore one after a
failed migration, keep Open WebUI stopped, verify the sidecar, move the failed tree
out of the way, extract the archive as root with ACL/xattr/ownership preservation,
restore the current SELinux labels, verify SQLite integrity and only then start the
service:

```bash
sudo systemctl stop open-webui.service
cd /var/backups/bc250-llm-server/rollback/openwebui
sudo sha256sum -c openwebui-FROM-to-TO-TIMESTAMP.tar.gz.sha256
sudo mv /var/lib/open-webui /var/lib/open-webui.failed-$(date +%F_%H%M%S)
sudo tar --xattrs --acls --numeric-owner -C /var/lib \
  -xzf openwebui-FROM-to-TO-TIMESTAMP.tar.gz
sudo restorecon -RF /var/lib/open-webui
sudo sqlite3 /var/lib/open-webui/webui.db 'PRAGMA integrity_check;'
sudo systemctl start open-webui.service
```

The integrity command must print `ok`. Keep the moved failed tree until the restored
instance has been verified; it is diagnostic evidence, not the authoritative rollback
copy.

Restore helpers require confirmation, verify checksum sidecars and create
rollback data before replacement. Configuration restore remains strict about the
restored database integrity. Identity restore also requires `PRAGMA integrity_check`
to succeed, but compares the post-restore `foreign_key_check` set with the captured
pre-restore baseline: unrelated pre-existing violations do not block the identity
subset restore, while any newly introduced foreign-key violation fails closed and
triggers the existing automatic rollback.
Successful identity restore output reports the strict integrity result, the captured baseline
foreign-key violation count and `New FK violations: 0`. A failed validation reports only newly
introduced violations needed for diagnosis and explicitly confirms successful automatic rollback;
it does not dump the unrelated baseline set.

### Open WebUI package baseline

Open WebUI package-owned provider/task/RAG/model-preset state is now managed by
`bc250 openwebui-setup`, not the maintenance scheduler:

```bash
sudo bc250 openwebui-setup init
OWUI_API_KEY=TEMPORARY_ADMIN_KEY sudo -E bc250 openwebui-setup status
```

The Qwen3.5 workspace preset is imported additively with request-level
`custom_params.think=true` for the current Advanced product policy; unrelated operator models and settings are not synchronized away.
The temporary administrator credential is not stored by this helper.

### Storage and retention

```bash
sudo bc250 status
sudo bc250 storage status
sudo bc250 model status production
sudo bc250 maintenance clean-cache
sudo bc250 maintenance run prune
sudo journalctl -u owui-maintenance@prune-uploads.service -n 100 --no-pager
```

With `DRY_RUN=1`, prune output starts by stating that no files will be deleted and
separates actual deletion/freed counters from planned candidate/simulated values.

`bc250 status` is the shared storage view for GGUFs, the main/task/embedding/agent Ollama stores,
Hugging Face cache, Open WebUI, Podman and journal usage. `clean-cache` requires
confirmation and removes rebuildable Hugging Face cache, dangling container
images and old system-wide journal archives; it does not delete GGUFs, Ollama
models or Open WebUI data. The journal vacuum affects archived logs for the
whole host, not only BC-250 services.

Model weights are never deleted automatically. Use `sudo bc250 model unregister` when source should be retained, or
`sudo bc250 model remove` when manager-owned source/state should also be deleted. `bc250 storage dedupe` requires the affected model/UI
services to quiesce successfully and reports any restoration failure. It retains both a validated
source GGUF and its Ollama blob while sharing identical XFS extents; `df` shows
reclaimed physical capacity even if `du` counts both logical files. Upload pruning is a separate
maintenance workflow: it enumerates Open WebUI pages until the API returns zero records, an advertised
total is reached, or pagination stops discovering new file IDs. It does not assume a fixed Open WebUI
page size; uncertain metadata remains preserved rather than selected for deletion.

`bc250 storage prune-sources` removes only hash-verified offline source copies after matching an
Ollama blob and requires explicit confirmation.

Upload pruning calls Open WebUI's authenticated delete API so database, file
and vector state stay aligned. A manual `run prune`/`run all` preflights the protected
API key before starting the prune unit and reports the current age/ceiling/dry-run
policy without exposing the credential. It starts with `DRY_RUN=1`; review the current
run output before setting `DRY_RUN=0` in root-readable
`/etc/bc250-llm-server/maintenance.env`.

- `MAX_AGE_DAYS=0` disables the age rule.
- `MAX_TOTAL_GB=0` disables the known-size ceiling.
- Both rules cannot be disabled together.
- Unknown timestamps or sizes are preserved and reported.
- `MIN_FREE_GB` is the warning threshold shown by `sudo bc250 status`; it never
  deletes data.

Use generous retention and agree the policy with office users before enabling
deletion.

### Raspberry Pi maintenance companion

The Pi is primarily an availability/power companion, not a second appliance
controller. The BC-250 owns the decision whether shutdown is safe. Prepare the
server side with:

```bash
sudo bc250 maintenance companion enable
sudo bc250 maintenance companion status
sudo bc250 maintenance contract
```

`companion enable` enables the existing SSH server/firewall service, keeps HTTP
`:80` available as the office-readiness endpoint, and prepares a dedicated
`bc250-power-control` account whose authorized key must use the forced command
printed by the helper. It does **not** open `3000` or Ollama ports
`11434`-`11437`.

The stable operator request is:

```bash
sudo bc250 maintenance request-shutdown
```

When invoked interactively over SSH, that SSH session is protected activity and the request
should defer. The restricted Pi key printed by `companion enable` instead uses the package
internal forced-command path, which exempts **only that authenticated control SSH connection**
from the same safe-power decision. The internal path still applies the configured protected ports,
power action and Wake-on-LAN requirement from `maintenance.env`; it does not use a weaker default
policy. If the authenticated tuple cannot be found exactly once in the live TCP table, the power
request fails closed. Any second SSH session still blocks shutdown.

The request runs the same package safe-power policy as the night timer. The TCP guard is
deliberately conservative: if either endpoint of an established connection matches a protected
port (SSH/UI/Ollama plus configured web ports), automatic poweroff is deferred. This includes
selected outbound activity such as HTTPS downloads; the log therefore reports **protected TCP
activity**, not only inbound UI sessions. Active
maintenance, SSH, UI or Ollama traffic can therefore defer shutdown. A Pi should
never replace this with an unconditional remote `systemctl poweroff`.

The external machine owns its weekday morning WOL schedule and readiness retry
policy. Verify a real poweroff-to-WOL boot before relying on unattended nightly
poweroff. The complete shared interface is in
[`OPERATIONS.md`](OPERATIONS.md).

### Electricity use

Model warm-up is off by default because it runs inference and keeps a model
resident. When enabled, the default warm-up uses the standard office model with
a 15-minute keep-alive.

After-hours `poweroff` or `suspend` is also opt-in. The helper defers while
backup, prune, warm-up, SSH, web or Ollama activity is detected and retries up
to five times. `poweroff` normally saves more energy; `suspend` must first be
tested on the board. Requiring Wake-on-LAN makes the power action refuse to run
when WOL setup is not verified.

An automatic power action needs a deliberate morning restart path: tested WOL,
firmware scheduling, a managed smart plug or someone on site. When guided power
saving is enabled, configuring WOL is now the default recommendation and sets
`REQUIRE_WOL=1`; the power action then refuses to run if WOL setup cannot be
verified.

### Timers

```bash
systemctl list-timers 'owui-*' 'bc250-night-shutdown.timer'
sudo bc250 maintenance run backup
sudo bc250 maintenance run all
sudo bc250 maintenance status
```

| Task | Default schedule | State after `setup --defaults` |
|---|---|---|
| Configuration backup | Daily 17:45 | Enabled |
| Identity backup | Daily 18:00 | Enabled |
| Upload prune | Daily 18:10 | Disabled, dry-run |
| Model warm-up | Weekdays 07:35 | Disabled |
| Idle power action | Weekdays from 18:30 | Disabled |

Backup timers are persistent and run after the next boot if missed. Prune,
warm-up and power timers are non-persistent. Manual `run` output is scoped to the
just-completed systemd invocation, so older journal history does not bury the result.
All storage jobs share one lock and use idle I/O scheduling.

## Maintenance companion contract

<!-- BEGIN BC250_MAINTENANCE_CONTRACT -->

Contract version: **1**

This document defines the stable BC-250-facing interface for a small external
maintenance companion such as a Raspberry Pi. The BC-250 remains responsible
for office-service behavior and deciding whether shutdown is safe. The Pi may
wake and observe the appliance, request a safe shutdown, and optionally pull
published backup artifacts.

### Responsibility boundary

| Responsibility | Owner |
|---|---|
| Office LLM service | BC-250 |
| Decide whether shutdown is safe | BC-250 |
| Automatic after-hours shutdown | BC-250 |
| Morning Wake-on-LAN | External companion |
| Verify office readiness after wake | External companion |
| Produce local backups | BC-250 |
| Optional off-device backup copy/retention | External companion |

The external companion must not use raw `systemctl poweroff` as its normal
remote-control interface. Use the package safe-power request instead.

### Network/readiness contract

The office-facing readiness endpoint is:

```text
HTTP http://<BC250_HOST>/
TCP 80
```

Administrative/restricted maintenance SSH is TCP 22. The following are internal
appliance ports and are not part of the companion readiness contract:

```text
3000
11434
11435
11436
11437
```

Enabling the companion therefore needs only the existing office HTTP service and
SSH. Wake-on-LAN is an Ethernet magic packet and does not require opening a host
firewall UDP port.

### Wake-on-LAN contract

The BC-250 package owns NIC WOL configuration. A configured interface should
report:

```text
Wake-on: g
```

The external companion owns its wake schedule, retry policy and broadcast
address. Before automatic BC-250 poweroff is relied upon, perform a real
powered-off/S5 Wake-on-LAN test on the installed hardware.

### Safe shutdown contract

The stable external request is:

```bash
sudo bc250 maintenance request-shutdown
```

That request delegates to the package safe-power policy. The BC-250 may defer
shutdown while maintenance, SSH, UI or Ollama activity is present. A defer is a
normal safe outcome, not a reason for the external companion to force poweroff.

Prepare the restricted SSH side with:

```bash
sudo bc250 maintenance companion enable
sudo bc250 maintenance companion status
```

The package prints the exact forced-command `authorized_keys` template. The
power-control key is scoped to the package-internal
`restrict,command="/usr/bin/sudo /usr/bin/bc250 maintenance request-shutdown-companion"`
path. That path preserves the OpenSSH `SSH_CONNECTION` tuple and exempts only that
one authenticated control connection from the protected-TCP test; the tuple must be found exactly
once or the request fails closed. The companion path still uses the configured safe-power ports,
power action and WOL requirement, and any second SSH session still defers shutdown. Operators continue to use the public
`sudo bc250 maintenance request-shutdown` command. Do not use the internal companion
command as a general bypass.

Private keys remain on the external companion. If the Pi has a stable address,
the operator may additionally add an OpenSSH `from="PI_IP"` restriction. Pi-side
SSH should pin the BC-250 host key and use `IdentitiesOnly=yes`; those Pi-local
settings are not stored by this package.

### Local backup producer contract

Configuration backups are published under:

```text
/var/backups/bc250-llm-server/config/
  owui-config-YYYY-MM-DD_HHMMSS.tar.gz
  owui-config-YYYY-MM-DD_HHMMSS.tar.gz.sha256
```

Identity backups are published under:

```text
/var/backups/bc250-llm-server/users/
  owui-users-YYYY-MM-DD_HHMMSS.sql.gz
  owui-users-YYYY-MM-DD_HHMMSS.sql.gz.sha256
```

Only an artifact with its matching SHA-256 sidecar is a complete exportable
pair. Routine backups are intentionally not a full RAG/document/model image;
they exclude bulky uploads/vector/cache data and model stores.

Optional read-only export is prepared with:

```bash
sudo bc250 maintenance backup-export enable
sudo bc250 maintenance backup-export status
```

Fedora 44 supplies `/usr/bin/rrsync` in the `rsync-rrsync` package. The package
is not silently installed; when needed use:

```bash
sudo dnf install rsync-rrsync
```

The export account/group is `bc250-backup-export`. Export is read-only through
SSH/rrsync, uses separate config/users key scopes, does not expose rollback
backups or maintenance secrets, and does not require another firewall port. The
forced-command scopes are:

```text
restrict,command="/usr/bin/rrsync -ro /var/backups/bc250-llm-server/config"
restrict,command="/usr/bin/rrsync -ro /var/backups/bc250-llm-server/users"
```

Use independent Ed25519 keys for power control, config backup and users backup.
One compromised key should not silently expand into another maintenance scope.

### Backup permissions when export is enabled

| Path/artifact | Group | Mode |
|---|---|---:|
| `/var/backups/bc250-llm-server` | `bc250-backup-export` | `0710` |
| `config/` | `bc250-backup-export` | `0750` |
| `users/` | `bc250-backup-export` | `0750` |
| published config/users artifacts | `bc250-backup-export` | `0640` |

`rollback/` remains private. If backup export is not enabled, the reserved group has
no user members and config/users artifacts remain private `0600`; the `0750`
directories still retain the dormant group so later export enablement does not require
permission repair after every backup run.

### Open WebUI credentials

The external companion does not need an Open WebUI API key for WOL, readiness,
safe shutdown or backup transport. `OWUI_API_KEY` remains a BC-250-local
protected maintenance credential.

### Schedule and retention convention

Cross-machine schedules use local `Europe/Zurich` wall-clock time unless a site
deliberately configures otherwise. The BC-250 owns after-hours shutdown timing;
the external companion owns morning wake timing. Do not duplicate shutdown
policy on the companion.

Current BC-250 local backup defaults are configuration at 17:45 and identity at
18:00, with local retention counts of 7 and 14 respectively. These are producer
policy defaults, not proof that a new backup exists. A Pi should discover complete
artifact/sidecar pairs and may keep a different, longer off-device retention.

### Compatibility

Breaking this interface requires increasing the contract version. Deployment
values such as IP address, MAC address, public-key fingerprint, wake time and Pi
retention policy do not by themselves change the contract version.

<!-- END BC250_MAINTENANCE_CONTRACT -->
