# Command reference

`bc250 COMMAND [ARGUMENTS...]` is the canonical interface. Each command also
has a `bc250-COMMAND` compatibility name, so `bc250 verify` and
`bc250-verify` are equivalent.

## Complete public interface

| Command | Purpose |
|---|---|
| `bc250` | Canonical multicall dispatcher |
| `bc250-40cu` | Replacement-module and live CU controls |
| `bc250-agent-mode` | Enter/leave/status exclusive coding-agent mode |
| `bc250-benchmark` | Explicit model, quality, coexistence and tuning benchmarks |
| `bc250-revalidate` | Opt-in whole-appliance revalidation harness |
| `bc250-check-temp` | Continuously refreshed sensors (`--once` for one sample) |
| `bc250-code` | Local generate/refactor/review/document/test helper |
| `bc250-code-commit` | Propose and optionally create a local Git commit |
| `bc250-compare-mtp` | Run a same-GGUF llama.cpp baseline-vs-MTP evidence comparison |
| `bc250-cu-status` | Kernel/RADV diagnostics plus the full live-routing dashboard |
| `bc250-cu-live-manager` | Pinned interactive live WGP manager |
| `bc250-fetch-mtp` | Explicitly download/reconcile a selected MTP experiment, including disabled catalog entries |
| `bc250-gitea-review` | Generate an optional Gitea pull-request review |
| `bc250-install` | Apply/resume the packaged appliance setup |
| `bc250-install-ollama` | Install or normalize official Ollama |
| `bc250-maintenance` | Backups, safe power/WOL policy and optional Pi companion access |
| `bc250-memory-profile` | Inspect or change TTM boot arguments |
| `bc250-model` | Model catalog, state inspection and lifecycle reconciliation |
| `bc250-ocr` | Experimental office OCR model list/install/test helper |
| `bc250-rag-import` | Validate and incrementally sync the operator document tree |
| `bc250-ollama-profile` | Switch the main Ollama runtime profile |
| `bc250-openwebui-setup` | Initialize/apply/check package-owned Open WebUI state |
| `bc250-run-mtp` | Start a downloaded MTP model with llama.cpp |
| `bc250-model apply agentic` | Reconcile agent model(s), switching temporarily to exclusive agent mode |
| `bc250-model apply embedding` | Reconcile embedding model(s) on the required dedicated lane |
| `bc250-model apply task` | Reconcile task model(s) on the required dedicated lane |
| `bc250-status` | Concise read-only appliance status |
| `bc250-storage` | Report/dedupe/prune package-owned storage |
| `bc250-swap-profile` | Inspect or change zram/disk-swap policy |
| `bc250-reset` | Reset the dedicated pre-1.0 appliance configuration |
| `bc250-reset-info` | Print the reset contract |
| `bc250-uninstall` | Compatibility alias for `bc250-reset` |
| `bc250-uninstall-info` | Compatibility alias for `bc250-reset-info` |
| `bc250-verify` | Detailed local installation verification |
| `bc250-verify-lan` | Test the web endpoint from another machine |
| `llm-run-diagnose` | Capture a model-run diagnostic |

Use `bc250 --help` for the grouped dispatcher list. Commands that modify the
host or service-owned data normally require `sudo`.

## Guided installer

Repository bootstrap:

```bash
sudo ./install [RPM-FILE-OR-DIRECTORY]
```

The bootstrap does only two things: local RPM install/update, then
`exec bc250-install`. Fedora update policy belongs to the packaged installer. The RPM itself does not run the appliance installer
from `%post`.

Packaged orchestrator:

```bash
sudo bc250-install
sudo bc250-install --models-only
sudo bc250-install --owui-token-file /root/owui-test.key
```

Normal mode prints a setup plan covering root growth, Fedora/package/Ollama,
TTM/swap, 40-CU, storage headroom, models, Open WebUI and reboot state; it applies
only pending work where practical and
combines kernel update plus TTM configuration before the primary reboot. After
that reboot it prepares 40-CU support for the exact running kernel. The base
Open WebUI Quadlet is intentionally dormant across the primary reboot; after
all active role base models plus task/Jina defaults are registered, the installer adds
its small `[Install]` drop-in,
reloads systemd and starts Open WebUI. A second reboot is requested only when
persistent 40-CU mode is already configured and the prepared replacement module
is not yet running.

The installer ensures every base model required by active package-owned Open WebUI
roles, plus the task and embedding defaults, without printing the full catalog. Fully
unchanged required models are summarized by category; downloads or repairs remain verbose.
It then presents compact state for ordinary production/experiment/task/agent/embedding
extras. Fully current rows collapse to `[CURRENT]`, and the intentionally inactive agent
lane is shown as deferred without waiting on that stopped Ollama instance. MTP is not part
of this generic picker; use `bc250-model list mtp --all` plus `bc250-fetch-mtp ID` explicitly.
Use global indexes, ranges, exact names, `recommended`, `production` or `all`; Enter skips
optional extras only.
For non-TTY runs use `BC250_MODEL_SELECTION`. The original stdin mode is retained
across transcript PTY creation, so unattended runs never become interactive by
accident. `BC250_HF_ANONYMOUS=1` forces anonymous Hugging Face downloads. The model manager
asks for an optional Hugging Face token only when a download is actually needed;
a no-op update with current model sources does not ask for one.
`BC250_UPDATE_OLLAMA=1` explicitly refreshes official Ollama.

## Models

The model manager deliberately separates read-only discovery/state inspection from
mutating lifecycle operations:

```bash
bc250-model list [CATEGORY] [--all] [--source PATH] [--modelfile-dir PATH]
sudo bc250-model status [CATEGORY] [SELECTION] [--online] [--verbose|--compact]
bc250-model path CATEGORY ID

sudo bc250-model apply CATEGORY [SELECTION] [OPTIONS]
sudo bc250-model refresh CATEGORY [SELECTION] [OPTIONS]
sudo bc250-model unregister CATEGORY [SELECTION] [--host HOST[:PORT]] [--destination PATH] [--yes]
sudo bc250-model remove CATEGORY [SELECTION] [--host HOST[:PORT]] [--destination PATH] [--yes]
sudo bc250-model purge-retired [--yes]
```

Categories are `production`, `experiments`, `task`, `agentic`, `embedding`, `mtp`
and `all`. Legacy aliases are intentionally not accepted. Selections accept a full
model name, displayed global catalog index, comma list, range such as `0,2-4`,
`recommended`, `production`, or `all`. Prefer full names in long-lived automation.

### Discovery and state

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

`path` is the narrow machine-readable resolver used by package tooling. It prints the
resolved source path and MTP context/draft metadata for one exact model; it replaces the
old technical `resolve` verb and is not a lifecycle action.

### Lifecycle operations

`apply` means **make the selected model match the current catalog definition**. It reuses
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

### Apply / refresh options

Common options for `apply` and `refresh`:

- `--quiet`: suppress repeated catalog/topology-transition chatter for scripts;
- `--revision REVISION`: one-model source revision override;
- `--sha256 DIGEST`: require an exact downloaded-file checksum;
- `--host HOST[:PORT]`: override the target Ollama API;
- `--destination PATH`: override the manager-owned GGUF root;
- `--min-free-bytes BYTES`: require free space before downloading;
- `--token-file PATH`: read a Hugging Face token from a protected file;
- `--include-disabled`: allow disabled MTP entries to be selected for an explicit `mtp` category operation; combined `apply all` / `refresh all` never include MTP;
- `--modelfile-dir PATH`: add a Modelfile search directory;
- `--source PATH`: use another MTP TOML catalog.

Remote experimental `hf.co/...` definitions do not accept local-GGUF revision/checksum/
destination overrides because Ollama owns their model/projector blobs. Hugging Face
authentication is requested only when a manager download actually needs it.

### MTP lifecycle

MTP entries are download-only llama.cpp experiments and are intentionally outside generic
combined convergence. The installer picker excludes them, and `apply all` / `refresh all` never
select MTP even when `--include-disabled` is supplied. Use the explicit `mtp` category or the
opt-in helper to select one:

```bash
bc250-model list mtp --all
sudo bc250-fetch-mtp qwen3.5-9b-mtp
sudo bc250-model status mtp qwen3.5-9b-mtp --include-disabled --verbose
LLAMACPP=/opt/llama.cpp/build/bin/llama-server bc250-compare-mtp qwen3.5-9b-mtp
```

Running `sudo bc250-fetch-mtp` without a selection shows the disabled experiment entries
and prompts for one. It maps to `bc250-model apply mtp --include-disabled`; the explicit
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

## Documents / RAG import

```bash
sudo bc250-rag-import plan [ROOT]
sudo bc250-rag-import sync [ROOT] --token-file FILE [--prune]
```

The default root is `/srv/bc250-documents`. The supported layout is
`public|confidential/COLLECTION/{active,sources}`. Only Markdown files directly
inside `active/` are sent to Open WebUI; PDFs in `sources/` remain the local
authoritative evidence and their SHA-256 is checked against each Markdown
header before sync. `source_file` is a filename, not a path; the importer rejects
`../`/absolute references and symlinked active/source files or directories that
could leave the collection boundary. Front matter is a strict small YAML subset
documented in `RAG.md`; malformed indentation, duplicate keys and unknown fields
fail the plan before network access.

German originals are routed to `[SCOPE] COLLECTION — Originals`; French
translation pairs are routed to `[SCOPE] COLLECTION — Français`. `plan` makes no
network request. `sync` uses Open WebUI's v0.11 incremental knowledge API,
skips unchanged files and replaces changed files only after the new upload
succeeds. Files removed locally remain in Open WebUI unless `--prune` is
explicitly supplied. The API key is never packaged; read it from a protected
file or `OPEN_WEBUI_API_KEY`.

## Experimental OCR

```bash
bc250-ocr list
sudo bc250-ocr install glm|ovis
bc250-ocr show glm|ovis
bc250-ocr test glm|ovis IMAGE
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
`11436`. Normal mode requires main + task + embedding. `bc250-model` switches
modes automatically for package-managed agent registration and restores normal
mode afterwards; `bc250-agent-mode enter|leave` is the explicit runtime switch.
Each lane keeps its own model store. Revision/checksum overrides still require
one selected model.

See [`../MODELS.md`](../MODELS.md) for model roles/swapping and
[`../models/README.md`](../models/README.md) for the detailed Modelfile contract.


## Storage

```bash
sudo bc250-storage status
sudo bc250-storage dedupe [--yes]
sudo bc250-storage prune-sources [--yes]
sudo bc250-storage prune-40cu [--yes]
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
never MTP download-only sources. `prune-40cu` removes only cache directories whose
kernel no longer exists under `/usr/lib/modules`. No storage cleanup is automatic.

## Runtime profiles

```bash
bc250-memory-profile status
bc250-memory-profile recommend
sudo bc250-memory-profile ensure
sudo bc250-memory-profile apply-full
sudo bc250-memory-profile remove

bc250-swap-profile status
sudo bc250-swap-profile ensure
sudo bc250-swap-profile apply
sudo bc250-swap-profile remove

bc250-ollama-profile status
sudo bc250-ollama-profile balanced
sudo bc250-ollama-profile max-context
sudo bc250-ollama-profile reset
```

- `ensure` is the idempotent installer path. The memory helper owns the two TTM
  limits and removal of `amdgpu.gttsize` / full `amdgpu.ppfeaturemask` overrides;
  the swap helper owns its complete zram/fstab/swap-file state. Neither reboots.
- The swap profile defaults to 2 GiB zram and a 16 GiB disk swap file.
  `ZRAM_MIB`, `SWAP_GIB` and optional `SWAPPINESS=0..200` override it.
- The balanced Ollama profile uses 32K context and q8_0 KV cache. Max-context
  uses 64K and q4_0; both keep one parallel request and one loaded model.

## CU tools

```bash
bc250-cu-status
bc250-cu-status --summary
sudo bc250-40cu status
sudo bc250-40cu verify
sudo bc250-40cu prepare
sudo bc250-40cu enable
sudo bc250-40cu disable
sudo bc250-40cu restore
sudo bc250-40cu {live-status|live-full|live-stock}
sudo bc250-40cu {mask|unmask} WGP_ID [WGP_ID ...]
sudo bc250-40cu health-test [OLLAMA_MODEL]
sudo bc250-cu-live-manager {menu|status}
```

`bc250-40cu enable` requires the phrase `ENABLE-40CU` and reboots. Live
mask/unmask operations require `APPLY-WGP-TABLE`. `bc250-40cu status` reports
module/persistence state plus the live routed-CU summary; kernel/RADV CU counters
are diagnostic and are not treated as the live available total. The guided installer
prepares the module for the running kernel without silently enabling persistent boot mode. CPU-core
unlocking is intentionally avoided: extra CPU cores do not improve the practical
model-capacity limit of this ~16 GB unified-memory appliance and add power/thermal
pressure. See [`CU-UNLOCK.md`](CU-UNLOCK.md) before changing GPU routing.

## Verification and monitoring

```bash
sudo bc250-status
sudo bc250-verify
sudo bc250-verify --summary
sudo bc250-verify --owui-token-file /root/owui-test.key
sudo bc250-openwebui-setup status --verbose --owui-token-file /root/owui-test.key
RUN_MODEL_TESTS=1 sudo bc250-verify
bc250-verify-lan SERVER_IP
sudo llm-run-diagnose --no-load
MODEL=MODEL_NAME LOAD_SECONDS=120 NUM_PREDICT=2000 sudo llm-run-diagnose
bc250-check-temp --once
bc250-benchmark generation
sudo bc250-revalidate start --owui-token-file /root/owui-test.key
sudo bc250-revalidate start --skip-owui
sudo bc250-revalidate status
sudo bc250-revalidate status --raw
sudo bc250-revalidate abort
sudo bc250-revalidate cleanup
```

`bc250-revalidate` harness v4.2 is the root-only systemd-backed package
qualification workflow. A full
`sudo bc250-revalidate start --owui-token-file FILE` follows a compact six-phase
dashboard. Use `--skip-owui` only for an explicitly incomplete Open WebUI coverage
run. The token file must be a protected readable regular file and is authenticated
before run state is created. The worker remains systemd-owned; Ctrl-C detaches and
`--detach` returns immediately. The dashboard reports stage elapsed time, worker
state and the age of the last real progress event rather than treating a periodic
heartbeat as progress.
Harness v4.2 also surfaces non-failing resource observations such as context truncation
under a separate `Diagnostics` section. These diagnostics do not weaken or replace the
existing infrastructure/quality gates. Intermediate successful phases use lighter
checkpoints while high-value topology/restoration boundaries retain full snapshots.

Revalidation tests only promoted package defaults. Configuration-decision work
(`num_batch`, embedding batch, chunk-min, `RAG_SYSTEM_CONTEXT`, thinking-policy,
keepalive, kernel/governor and experimental-model A/B) belongs to explicit
benchmark/diagnostic commands. The preflight also requires a healthy complete live
SPI/WGP routing table with no off/problem cells; it does not hard-code `40/40`.

Benchmark quality exit `3` is recorded and nonfatal. Other benchmark/helper errors
are infrastructure failures and enter the single top-level restoration/finalization
path. Authenticated packaged Open WebUI qualification accepts
`--owui-token-file FILE` and now exercises both the production DE↔FR role/filter path
and the packaged RAG path. The direct translation stage pins the promoted 2048-token
budget; the Open WebUI stage sends source text through the real production role IDs rather
than rebuilding the Filter contract in the harness. Final bundles remain under
`/var/lib/bc250-llm-server/revalidation/results/`; completed work remains
inspectable until `cleanup` or a later `start`.

`bc250-revalidate status` is human-readable by default and separates the installed
harness/worker state from the recorded last-run result; `--raw` preserves the
key/value form for scripts. `abort` requests termination of the current systemd-owned
run through the harness recovery/finalization path; `cleanup` removes completed work
state after its result bundle is no longer needed. Neither command is a substitute
for ordinary service stop/start management. `bc250-status` is a short overview including CPU
topology/power-state exposure, RAM, memory pressure, zram, disk swap, swappiness
and appliance storage. `bc250-verify` is the detailed pass/fail check and accepts
`--owui-token-file FILE` for the authenticated package-owned Open WebUI drift check.
The detailed verifier also checks that every active package-owned Open WebUI role has its
base model registered on the main Ollama lane. `bc250-check-temp` refreshes every
second by default; use `--once` only when a single sample is useful. Verification includes kernel/module alignment, CU state, Ollama version,
internal Ollama listener/firewall policy, service health, optional GFX1013
compute queues and recent Vulkan/AMDGPU failure patterns. `bc250-verify-lan`
runs on a client; `HTTP_PORT` changes its expected web port.

Every benchmark invocation writes one isolated result directory containing canonical
`results.jsonl`, `summary.json`, `summary.txt`, `meta.json` and copied deterministic
fixtures. Categories with a useful table also write `results.csv`. Existing non-empty
output directories are rejected; use `--output-dir DIR` to select a path.

Canonical public benchmark commands are explicit; there is no commandless generation
default and no legacy alias layer:

```bash
bc250-benchmark generation --profile compare MODEL...
bc250-benchmark generation --profile edge --mode production MODEL...
bc250-benchmark generation --profile thermal MODEL...
bc250-benchmark generation --deep-context MODEL...
bc250-benchmark generation --profile thermal --sustained-seconds 180 MODEL...
bc250-benchmark embeddings [MODEL ...]
bc250-benchmark ocr [MODEL ...]
bc250-benchmark task [MODEL ...]
bc250-benchmark usecase [MODEL ...]
bc250-benchmark translation [--think auto|true|false] [MODEL ...]
bc250-benchmark rag-cycle EMBED_MODEL ANSWER_MODEL
bc250-benchmark rag-quality --think true [EMBED_MODEL ANSWER_MODEL]
bc250-benchmark rag-quality --think false [EMBED_MODEL ANSWER_MODEL]

sudo bc250-agent-mode enter
bc250-benchmark agent MODEL --ollama-url http://127.0.0.1:11436
sudo bc250-agent-mode leave

bc250-benchmark concurrency MAIN_MODEL EMBED_MODEL
bc250-benchmark num-batch MODEL [MODEL ...]
bc250-benchmark owui-translation --token-file FILE
bc250-benchmark owui-rag MODEL --token-file FILE
bc250-benchmark owui-embedding-batch --token-file FILE
bc250-benchmark owui-chunk-min MODEL --token-file FILE
sudo bc250-benchmark owui-system-context MODEL --token-file FILE
```

The Open WebUI tuning commands are explicit experiments: they save the observed
package-owned setting, change only the named benchmark setting, use temporary
knowledge/file state, and restore the original value. Restoration failure is an
infrastructure failure. Routine revalidation does not run these A/B sweeps.

Generation and coexistence reporting emphasizes resident size, minimum
`MemAvailable`, swap start/peak/end/delta, temperature and request outcomes. Generation
also records completion-integrity state, effective local Ollama runtime/KV evidence when
available, current CU status and best-effort kernel GPU-error evidence. `--deep-context`
adds approximate 4K/16K targets with actual `prompt_eval_count` as the authority;
`--sustained-seconds` makes the thermal lane continue to a minimum elapsed time. VRAM/GTT
remain diagnostic Vulkan counters and must not be interpreted as independent additive
memory pools on the BC-250. See [`../cmd/benchmark/README.md`](../cmd/benchmark/README.md)
for result schema, category contracts and Ollama 0.34.0 request policy. The installed copy is
`/usr/share/doc/bc250-llm-server/cmd/benchmark/README.md`.

## Open WebUI setup

```bash
sudo bc250-openwebui-setup init
sudo bc250-openwebui-setup init --token-file /root/owui-test.key
sudo bc250-openwebui-setup init --owui-token-file /root/owui-test.key  # alias
OWUI_API_KEY=TEMPORARY_ADMIN_KEY sudo -E bc250-openwebui-setup apply
bc250-openwebui-setup status
sudo bc250-openwebui-setup status --token-file /root/owui-test.key
OWUI_API_KEY=TEMPORARY_ADMIN_KEY sudo -E bc250-openwebui-setup status
```

`init` can create the first administrator, sign in an existing administrator or
use a protected administrator API-key file. The guided installer exposes the same
choice and suggests `/root/owui-test.key` when it already exists with protected
permissions. It applies the package-owned main/task provider, dedicated embedding,
task/RAG, reviewed package-owned Open WebUI Functions and additive model-preset baseline.
`status` also verifies the package Function source/state and package-owned preset fields
needed by the selected production translation contract. Credentials/tokens are not
persisted by the package. Unrelated
operator models, users, prompts and knowledge are not synchronized away.

Agent mode is separate from Open WebUI:

```bash
bc250-agent-mode status
sudo bc250-agent-mode enter
sudo bc250-agent-mode leave
```

Entering agent mode stops main/task/embedding and starts only the 11436 coding
backend; leaving restores normal mode.

## Maintenance

```bash
sudo bc250-maintenance setup [--defaults]
sudo bc250-maintenance status
sudo bc250-maintenance contract
sudo bc250-maintenance companion {status|enable}
sudo bc250-maintenance backup-export {status|enable}
sudo bc250-maintenance request-shutdown
sudo bc250-maintenance run {backup|prune|all}
sudo bc250-maintenance clean-cache
sudo bc250-maintenance disable
```

`setup --defaults` enables verified local backups only. Manual maintenance runs show
only the current systemd invocation instead of a historical journal tail. Upload
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
`/etc/bc250-llm-server/maintenance.env`. See [`MAINTENANCE.md`](MAINTENANCE.md)
and [`MAINTENANCE-CONTRACT.md`](MAINTENANCE-CONTRACT.md).

## Coding and experiments

```bash
bc250-code MODE INPUT [OUTPUT] [TASK...]
bc250-code-commit [--yes]
bc250-gitea-review OWNER/REPOSITORY PR_NUMBER [--output FILE] [--post]
LLAMACPP=/opt/llama.cpp/build/bin/llama-server bc250-compare-mtp MTP_ID
LLAMACPP=/opt/llama.cpp/build/bin/llama-server bc250-run-mtp MTP_ID
```

`MODE` is `generate`, `refactor`, `review`, `document`, `test` or `commit`.
`CODING_AGENT_MODEL` selects an installed agentic model; `OLLAMA_HOST`/`OLLAMA_URL`
override its endpoint, and `CODING_AGENT_NUM_PREDICT` overrides the positive output
token budget (default 3072). `bc250-code` uses `/api/chat` with `think:true` and writes
only terminal non-empty `message.content`. It returns `3` and leaves an existing output
file unchanged if completion is nonterminal, stops at `done_reason=length`, or final
content contains literal reasoning markers. Coding helpers do not stage, push, approve
or merge without the command's explicit local action.

Prepare a candidate first with `sudo bc250-fetch-mtp ID`; the explicit helper exposes
the packaged disabled experiments without making them part of normal convergence.

`bc250-compare-mtp` is a controlled same-target qualification helper: it starts the
same GGUF through the same external llama.cpp build and runtime settings first with
MTP disabled, then with `draft-mtp` enabled. `NUM_PREDICT` and `PROMPT` may override
the bounded completion probe. The result bundle records throughput, terminal
completion integrity, draft accepted/proposed counts and acceptance percentage,
minimum available memory, swap growth, model/source identity, llama.cpp identity and
relevant kernel/GPU faults. Missing MTP draft-acceptance telemetry is insufficient
qualification evidence rather than inference corruption. Use `bc250-benchmark` for
category quality/correctness comparisons. MTP requires a compatible external
llama.cpp server binary through `LLAMACPP`; `PORT`, `CTX`, `DRAFT_N_MAX` and optional
`UBATCH` override runtime values. When supported, the runner passes `--cache-ram 0`
and `--no-cache-idle-slots` to avoid shared serialized prompt-cache state and its RAM
reservation.

## Reset / package removal

```bash
sudo bc250-reset [--yes]
bc250-reset-info
sudo bc250-uninstall [--yes]  # compatibility alias
bc250-uninstall-info          # compatibility alias
```

The greenfield reset removes BC-250-owned runtime state, profiles, official Ollama
and verified CU changes after dedicated confirmation while preserving
`/srv/bc250-documents`. It does not reconstruct historical host ownership, roll
back Fedora upgrades or shrink filesystems. Ordinary
`dnf remove bc250-llm-server.x86_64` retains persistent data. Read
[`UNINSTALL.md`](UNINSTALL.md) first.
