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
| `bc250-check-temp` | Current or continuously refreshed sensors |
| `bc250-code` | Local generate/refactor/review/document/test helper |
| `bc250-code-commit` | Propose and optionally create a local Git commit |
| `bc250-compare-experiments` | Compare experiment responses with a baseline |
| `bc250-cu-status` | Kernel, RADV and live-routing CU summary |
| `bc250-cu-live-manager` | Pinned interactive live WGP manager |
| `bc250-fetch-embeddings` | Install discovered embedding models |
| `bc250-fetch-experiments` | Install discovered experiment models |
| `bc250-fetch-models` | Install discovered production models |
| `bc250-fetch-mtp` | Download enabled MTP catalog entries |
| `bc250-gitea-review` | Generate an optional Gitea pull-request review |
| `bc250-install-cu-manager` | Verify the packaged live manager is available |
| `bc250-install-ollama` | Install or normalize official Ollama |
| `bc250-maintenance` | Backups, retention and optional power schedules |
| `bc250-memory-profile` | Inspect or change TTM boot arguments |
| `bc250-model` | Unified model discovery, installation and cleanup |
| `bc250-ollama-profile` | Switch the main Ollama runtime profile |
| `bc250-pull-embedding-model` | Compatibility alias for embedding installation |
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
separately for production, task, agentic and embedding models.

Useful unattended selections are `BC250_PRODUCTION_SELECTION`,
`BC250_TASK_SELECTION`, `BC250_AGENTIC_SELECTION` and
`BC250_EMBEDDING_SELECTION`; use them with `BC250_ASSUME_YES=1`. Set
`BC250_HF_ANONYMOUS=1` to skip the token prompt. `BC250_UPDATE_OLLAMA=1`
explicitly refreshes an existing Ollama installation, and `OLLAMA_VERSION`
selects a reviewed version.

## Models

```text
bc250-model list CATEGORY [--all] [--source PATH] [--modelfile-dir PATH]
bc250-model resolve CATEGORY ID [--provider PROVIDER]
bc250-model install CATEGORY [SELECTION] [OPTIONS]
bc250-model cleanup CATEGORY [SELECTION] [--list] [--yes]
```

Categories are `production`, `experiments`, `task`, `agentic`, `embedding` and
`mtp`. Accepted aliases include `experimental`, `tasker`, `coding`, `embed` and
`embedded`. MTP is the only TOML-backed, download-only category; the other
categories are discovered from strict Modelfiles.

`SELECTION` accepts a full model name, displayed zero-based index, comma list,
range such as `0,2-4`, or `all`. With no selection, a terminal prompts and Enter
cancels. Prefer full names in automation.

Important install options:

- `--list`: show the selection without downloading;
- `--revision REVISION`: override one model's commit, tag, branch or `latest`;
- `--sha256 DIGEST`: require an exact downloaded-file checksum;
- `--refresh`: download and register again even when state matches;
- `--host HOST[:PORT]`: override the target Ollama API;
- `--destination PATH`: override the GGUF root;
- `--min-free-bytes BYTES`: require free space before downloading;
- `--token-file PATH`: read a Hugging Face token from a protected file;
- `--include-disabled`: include disabled MTP entries;
- `--modelfile-dir PATH`: add a Modelfile search directory;
- `--source PATH`: use another MTP TOML catalog.

Authentication is requested only when a download is required. `HF_TOKEN` or
`--token-file` is validated as the `ollama` account; an empty or rejected token
falls back to anonymous access. Tokens are not persisted by the manager.

Convenience commands:

```bash
sudo bc250-fetch-models [SELECTION]
sudo bc250-fetch-experiments [SELECTION]
sudo bc250-fetch-embeddings [SELECTION]
sudo bc250-fetch-mtp [SELECTION]
sudo bc250-setup-task-model [SELECTION]
sudo bc250-setup-coding-agent [SELECTION]
```

Task setup creates `ollama-task.service` on port `11435`; agentic setup creates
`ollama-agent.service` on `11436`. Each has its own model store. Setup selection
can also be supplied through `TASK_MODEL_SELECTION` or
`CODING_AGENT_SELECTION`. Revision and checksum overrides require one model.

See [`../models/README.md`](../models/README.md) for the Modelfile contract and
storage behavior.

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
bc250-install-cu-manager
bc250-40cu
bc250-40cu {status|verify|prepare|enable|disable|restore}
bc250-40cu {live-status|live-full|live-stock}
bc250-40cu {mask|unmask} WGP_ID [WGP_ID ...]
bc250-40cu health-test [OLLAMA_MODEL]
bc250-cu-live-manager {menu|status}
```

`bc250-40cu enable` requires the phrase `ENABLE-40CU` and reboots. Live
mask/unmask operations require `APPLY-WGP-TABLE`. The guided installer prepares
the module for the running kernel but never enables additional CUs. See
[`CU-UNLOCK.md`](CU-UNLOCK.md) before changing routing.

## Verification and monitoring

```bash
sudo bc250-status
sudo bc250-verify
RUN_MODEL_TESTS=1 sudo bc250-verify
bc250-verify-lan SERVER_IP
sudo llm-run-diagnose --no-load
MODEL=MODEL_NAME LOAD_SECONDS=120 NUM_PREDICT=2000 sudo llm-run-diagnose
bc250-check-temp [--watch]
bc250-benchmark
```

`bc250-status` is a short overview; `bc250-verify` is the detailed pass/fail
check. Verification includes kernel/module alignment, CU state, Ollama version,
service health, optional GFX1013 compute queues and recent Vulkan/AMDGPU failure
patterns. `bc250-verify-lan` runs on a client; `HTTP_PORT` changes its expected
web port.

The benchmark writes a timestamped CSV and metadata file in the current
directory. Important overrides include `OLLAMA_URL`, `THINK_MODE`, `REPEATS`,
`RUN_LATENCY`, `NUM_PREDICT_SHORT`, `NUM_PREDICT_LONG`, `CTX_POINTS` and
`THROTTLE_WINDOWS`.

## Maintenance

```text
bc250-maintenance setup [--defaults]
bc250-maintenance status
bc250-maintenance run {backup|prune|all}
bc250-maintenance disable
```

`setup --defaults` enables verified local backups only. Interactive setup can
also configure dry-run upload pruning, model warm-up and an after-hours power
action. Configuration is stored in root-readable
`/etc/bc250-llm-server/maintenance.env`. See
[`MAINTENANCE.md`](MAINTENANCE.md) before enabling deletion or power actions.

## Coding and experiments

```text
bc250-code MODE INPUT [OUTPUT] [TASK...]
bc250-code-commit [--yes]
bc250-gitea-review OWNER/REPOSITORY PR_NUMBER [--output FILE] [--post]
bc250-compare-experiments
bc250-run-mtp {27b|4b|ID}
```

`MODE` is `generate`, `refactor`, `review`, `document`, `test` or `commit`.
`CODING_AGENT_MODEL` selects an installed agentic model;
`OLLAMA_HOST`/`OLLAMA_URL` override its endpoint. Coding helpers do not stage,
push, approve or merge without the command's explicit local action.

Experiment comparison accepts `BASELINE_MODEL`, `OLLAMA_URL`, `MTP_URL`,
`NUM_PREDICT` and `PROMPT`. MTP requires a compatible external llama.cpp
server binary through `LLAMACPP`; `PORT`, `CTX` and `DRAFT_N_MAX` override its
runtime values.

## Uninstall

```text
bc250-uninstall [--yes]
bc250-uninstall-info
```

The full purge removes application data, models, profiles, setup-added
packages, official Ollama and verified CU changes after dedicated confirmation.
Ordinary `dnf remove bc250-llm-server.x86_64` retains persistent data. Read
[`UNINSTALL.md`](UNINSTALL.md) first.
