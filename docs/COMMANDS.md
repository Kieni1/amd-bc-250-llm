# Command reference

`bc250 COMMAND [ARGUMENTS...]` is the canonical interface. Each command also
has a `bc250-COMMAND` compatibility name, so `bc250 verify` and
`bc250-verify` are equivalent.

## Complete public interface

| Command | Purpose |
|---|---|
| `bc250` | Canonical multicall dispatcher |
| `bc250-40cu` | Replacement-module and live CU controls |
| `bc250-benchmark` | Interactive Ollama performance benchmark |
| `bc250-check-temp` | Continuously refreshed sensors (`--once` for one sample) |
| `bc250-code` | Local generate/refactor/review/document/test helper |
| `bc250-code-commit` | Propose and optionally create a local Git commit |
| `bc250-compare-mtp` | Compare an Ollama baseline with a running llama.cpp MTP server |
| `bc250-cu-status` | Kernel, RADV and live-routing CU summary |
| `bc250-cu-live-manager` | Pinned interactive live WGP manager |
| `bc250-fetch-embeddings` | Install discovered embedding models |
| `bc250-fetch-experiments` | Install discovered experiment models |
| `bc250-fetch-models` | Install discovered production models |
| `bc250-fetch-mtp` | Download enabled MTP catalog entries |
| `bc250-gitea-review` | Generate an optional Gitea pull-request review |
| `bc250-install-ollama` | Install or normalize official Ollama |
| `bc250-maintenance` | Backups, retention and optional power schedules |
| `bc250-memory-profile` | Inspect or change TTM boot arguments |
| `bc250-model` | Unified model discovery, installation and cleanup |
| `bc250-ocr` | Experimental office OCR model list/install/test helper |
| `bc250-rag-import` | Validate and incrementally sync the operator document tree |
| `bc250-ollama-profile` | Switch the main Ollama runtime profile |
| `bc250-run-mtp` | Start a downloaded MTP model with llama.cpp |
| `bc250-setup-coding-agent` | Configure the isolated agent Ollama instance |
| `bc250-setup-task-model` | Configure the isolated task Ollama instance |
| `bc250-status` | Concise read-only appliance status |
| `bc250-swap-profile` | Inspect or change zram/disk-swap policy |
| `bc250-uninstall` | Explicit full appliance purge |
| `bc250-uninstall-info` | Print the full purge policy |
| `bc250-verify` | Detailed local installation verification |
| `bc250-verify-lan` | Test the web endpoint from another machine |
| `llm-run-diagnose` | Capture a model-run diagnostic |

Use `bc250 --help` for the grouped dispatcher list. Commands that modify the
host or service-owned data normally require `sudo`.

## Guided installer

```text
sudo ./install [--rpm FILE-OR-DIRECTORY]
sudo ./install --models-only
```

Normal mode performs the complete host-to-verification workflow. It may pause
for a reboot and should then be rerun. `--models-only` skips host setup and asks
for production, task, agentic, embedding, experiment and MTP selections.

Useful unattended selections are `BC250_PRODUCTION_SELECTION`,
`BC250_TASK_SELECTION`, `BC250_AGENTIC_SELECTION`, `BC250_EMBEDDING_SELECTION`,
`BC250_EXPERIMENT_SELECTION` and `BC250_MTP_SELECTION`; use them with
`BC250_ASSUME_YES=1`. Set
`BC250_HF_ANONYMOUS=1` to skip the token prompt. `BC250_UPDATE_OLLAMA=1`
explicitly refreshes an existing Ollama installation, and `OLLAMA_VERSION`
selects a reviewed version.

## Models

```text
bc250-model list [CATEGORY] [--all] [--source PATH] [--modelfile-dir PATH]
bc250-model resolve CATEGORY ID
bc250-model install CATEGORY [SELECTION] [OPTIONS]
bc250-model cleanup CATEGORY [SELECTION] [--list] [--yes]
```

Categories are `production`, `experiments`, `task`, `agentic`, `embedding` and
`mtp`. Accepted aliases include `experimental`, `tasker`, `coding`, `embed` and
`embedded`. MTP is the only TOML-backed, download-only category; the other
categories are discovered from strict Modelfiles. Four OCR experiments use a
strict experimental `hf.co/...` FROM exception so Ollama can manage their paired
vision projector and model blobs.

With no category, `list` shows every Ollama-backed category as one catalog with
global indexes. A category filters the same catalog without renumbering it.
MTP remains separate and must be requested explicitly.

Every Ollama entry reports its definition origin, download state and whether it
is registered on the category's Ollama instance. `download unknown` means the
model is not registered and the current user cannot inspect its protected GGUF
path; use `sudo bc250-model list` for an exact source-file check. For remote
experimental vision definitions, `download unknown` while unregistered means the
source is Ollama-managed rather than a separately inspectable GGUF. Registrations
without a current Modelfile are reported separately as unmanaged models; known
models found on the wrong Ollama instance are reported as misplaced.

`SELECTION` accepts a full model name, displayed global catalog index, comma
list, range such as `0,2-4`, or `all`. The same index is used by filtered lists,
install and cleanup. MTP retains its own local indexes. With no selection, a
terminal prompts and Enter cancels. Prefer full names in automation.

Important install options:

- `--list`: show the current status without downloading;
- `--revision REVISION`: override one model's commit, tag, branch or `latest`;
- `--sha256 DIGEST`: require an exact downloaded-file checksum;
- `--refresh`: deliberately download new bytes, then register again;
- `--host HOST[:PORT]`: override the target Ollama API;
- `--destination PATH`: override the GGUF root;
- `--min-free-bytes BYTES`: require free space before downloading;
- `--token-file PATH`: read a Hugging Face token from a protected file;
- `--include-disabled`: include disabled MTP entries;
- `--modelfile-dir PATH`: add a Modelfile search directory;
- `--source PATH`: use another MTP TOML catalog.

Remote experimental `hf.co/...` definitions do not accept `--revision`,
`--sha256` or `--destination`; Ollama owns those source blobs.

Authentication is requested only when a download is required. A validated GGUF
is reused only while its recorded repository, revision and filename match and
its schema-2 size/mtime/ctime metadata is unchanged. If those stat values or a
legacy sidecar differ, the manager recalculates SHA-256 before reuse.
Modelfile-only edits such as SYSTEM or PARAMETER changes therefore rebuild the
Ollama registration without downloading again; changed source provenance
downloads the requested bytes. `HF_TOKEN` or `--token-file` is
validated as the `ollama` account; an empty or rejected token falls back to
anonymous access.
Tokens are not persisted by the manager.

Convenience commands:

```bash
sudo bc250-fetch-models [SELECTION]
sudo bc250-fetch-experiments [SELECTION]
sudo bc250-fetch-embeddings [SELECTION]
sudo bc250-fetch-mtp [SELECTION]
sudo bc250-setup-task-model [SELECTION]
sudo bc250-setup-coding-agent [SELECTION]
```

For office document retrieval, use the existing embedding workflow with
Open WebUI/Tika; see [`RAG.md`](RAG.md). There is no separate RAG daemon or
vector store. `bc250-rag-import` is only a metadata-aware Open WebUI sync client.

## Documents / RAG import

```text
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

```text
bc250-ocr list
sudo bc250-ocr install glm|ovis
bc250-ocr show glm|ovis
bc250-ocr test glm|ovis IMAGE
```

OCR models stay in the normal `experiments` category and main Ollama instance;
there is no OCR daemon or separate model store. The helper tests one image and
prints extracted text/Markdown for comparison. GLM is the measured fidelity
leader and OvisOCR2 remains the faster structured-document alternative. Test DE/FR/EN
letters, invoices, forms and table-heavy scans before using OCR output for RAG.

Task setup creates `ollama-task.service` on port `11435`; agentic setup creates
`ollama-agent.service` on `11436`. Each has its own model store. Setup selection
can also be supplied through `TASK_MODEL_SELECTION` or
`CODING_AGENT_SELECTION`. Revision and checksum overrides require one model.

See [`../MODEL.md`](../MODEL.md) for model roles/swapping and
[`../models/README.md`](../models/README.md) for the detailed Modelfile contract.

## Runtime profiles

```text
bc250-memory-profile {status|recommend|apply-full|apply-safe|remove}
bc250-swap-profile {status|apply|remove}
bc250-ollama-profile {status|balanced|max-context|reset}
```

- The full memory profile applies `ttm.pages_limit=4194304` and removes legacy
  BC-250 boot arguments. It does not reboot automatically.
- The swap profile defaults to 2 GiB zram and a 16 GiB disk swap file.
  `ZRAM_MIB`, `SWAP_GIB` and optional `SWAPPINESS=0..200` override it.
- The balanced Ollama profile uses 32K context and q8_0 KV cache. Max-context
  uses 64K and q4_0; both keep one parallel request and one loaded model.

## CU tools

```text
bc250-cu-status
bc250-40cu
bc250-40cu {status|verify|prepare|enable|disable|restore}
bc250-40cu {live-status|live-full|live-stock}
bc250-40cu {mask|unmask} WGP_ID [WGP_ID ...]
bc250-40cu health-test [OLLAMA_MODEL]
bc250-cu-live-manager {menu|status}
```

`bc250-40cu enable` requires the phrase `ENABLE-40CU` and reboots. Live
mask/unmask operations require `APPLY-WGP-TABLE`. The guided installer prepares
the module for the running kernel but never enables additional CUs. CPU-core
unlocking is intentionally avoided: extra CPU cores do not improve the practical
model-capacity limit of this ~16 GB unified-memory appliance and add power/thermal
pressure. See [`CU-UNLOCK.md`](CU-UNLOCK.md) before changing GPU routing.

## Verification and monitoring

```bash
sudo bc250-status
sudo bc250-verify
RUN_MODEL_TESTS=1 sudo bc250-verify
bc250-verify-lan SERVER_IP
sudo llm-run-diagnose --no-load
MODEL=MODEL_NAME LOAD_SECONDS=120 NUM_PREDICT=2000 sudo llm-run-diagnose
bc250-check-temp --once
bc250-benchmark
```

`bc250-status` is a short overview including CPU topology/power-state exposure,
RAM, memory pressure, zram, disk swap, swappiness and appliance storage.
`bc250-verify` is the detailed pass/fail check. `bc250-check-temp` refreshes every
second by default; use `--once` only when a single sample is useful. Verification includes kernel/module alignment, CU state, Ollama version,
internal Ollama listener/firewall policy, service health, optional GFX1013
compute queues and recent Vulkan/AMDGPU failure patterns. `bc250-verify-lan`
runs on a client; `HTTP_PORT` changes its expected web port.

The benchmark writes timestamped CSV, JSONL and metadata files in the current
directory. The default generation lane uses `BENCH_MODE=neutral`: a per-request
neutral SYSTEM override and deterministic sampling for comparable model/runtime
measurements. `BENCH_MODE=production` is the production-configuration
comparison: it keeps the registered Modelfile SYSTEM and sampling while running the same generic workload.
Role-specific Office/RAG/translation use-case fixtures are intentionally deferred.
`THINK_MODE=auto` applies the package's model-family policy. Latency runs use a
larger shared `num_predict` cap for reasoning-capable/unset policies so TTFA is
not routinely starved by thinking; LFM2.5 keeps that larger cap even in an
explicit `think=false` experiment because measured native reasoning persisted.
`NUM_PREDICT_LATENCY_THINKING` can override that cap separately.

```bash
bc250-benchmark                         # generation, neutral mode
BENCH_MODE=production bc250-benchmark
BENCH_PROFILE=conservative bc250-benchmark
bc250-benchmark embeddings              # DE/FR/EN retrieval quality + speed
bc250-benchmark ocr                     # office OCR fixtures
bc250-benchmark task                    # Open WebUI 0.11.1-compatible task behavior
bc250-benchmark agent                   # coding correctness, defaults to port 11436
OLLAMA_URL=http://127.0.0.1:11436 bc250-benchmark generation MODEL
```

Generation, embedding and OCR record the full request-time thermal/GPU/UMA
telemetry set from one selected AMD DRM device; use `BC250_DRM_CARD=cardN` only
when automatic boot-GPU selection is wrong. Task and agent runs intentionally
keep the smaller subset useful for those short correctness/latency workloads. `RUN_THERMAL=1` applies to the
generation lane. Treat resource figures as overlapping UMA signals, not
independent pools. See [`../cmd/benchmark/README.md`](../cmd/benchmark/README.md)
for metrics, fixtures and Ollama 0.32.15 request policy. The installed copy is
`/usr/share/doc/bc250-llm-server/BENCHMARK.md`.

## Maintenance

```text
bc250-maintenance setup [--defaults]
bc250-maintenance status
bc250-maintenance run {backup|prune|all}
bc250-maintenance clean-cache
bc250-maintenance disable
```

`setup --defaults` enables verified local backups only. `clean-cache` requires
confirmation and removes only rebuildable Hugging Face cache, dangling Podman
images and old **system-wide** journal archives; model and Open WebUI data are
retained.
Interactive setup can also configure dry-run upload pruning, model warm-up and
an after-hours power action. Configuration is stored in root-readable
`/etc/bc250-llm-server/maintenance.env`. See
[`MAINTENANCE.md`](MAINTENANCE.md) before enabling deletion or power actions.

## Coding and experiments

```text
bc250-code MODE INPUT [OUTPUT] [TASK...]
bc250-code-commit [--yes]
bc250-gitea-review OWNER/REPOSITORY PR_NUMBER [--output FILE] [--post]
bc250-compare-mtp
bc250-run-mtp {27b|4b|ID}
```

`MODE` is `generate`, `refactor`, `review`, `document`, `test` or `commit`.
`CODING_AGENT_MODEL` selects an installed agentic model;
`OLLAMA_HOST`/`OLLAMA_URL` override its endpoint. Coding helpers do not stage,
push, approve or merge without the command's explicit local action.

The quick MTP comparison accepts `BASELINE_MODEL`, `OLLAMA_URL`, `MTP_URL`,
`NUM_PREDICT` and `PROMPT`. It is a speed-oriented Ollama-vs-llama.cpp helper;
use `bc250-benchmark` for category quality/correctness comparisons. MTP requires
a compatible external llama.cpp
server binary through `LLAMACPP`; `PORT`, `CTX` and `DRAFT_N_MAX` override its
runtime values. When supported, the runner passes `--cache-ram 0` and
`--no-cache-idle-slots` to avoid shared serialized prompt-cache state and its
RAM reservation.

## Uninstall

```text
bc250-uninstall [--yes]
bc250-uninstall-info
```

The full purge removes application data, models, profiles, setup-added
packages, official Ollama and verified CU changes after dedicated confirmation.
Ordinary `dnf remove bc250-llm-server.x86_64` retains persistent data. Read
[`UNINSTALL.md`](UNINSTALL.md) first.
