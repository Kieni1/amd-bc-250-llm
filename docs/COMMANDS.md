# Command and override reference

`TLDR.md` is the setup overview. This document records the supported command
forms and environment overrides that are useful for automation and diagnosis.
Commands that change the system generally require `sudo`; read their status or
help output before applying a profile.

## Dispatcher

`bc250 COMMAND [ARGUMENTS...]` is the canonical interface. Installed
`bc250-COMMAND` names are compatibility symlinks to the same dispatcher.

```bash
bc250 --help
bc250 model --help
bc250-model --help
```

## Model catalogs

The unified manager handles `production`, `experiments`, `mtp`, `task` and
`coding`:

```text
bc250-model list CATEGORY [--all] [--source PATH] [--modelfile-dir PATH]
bc250-model resolve CATEGORY ID [--provider PROVIDER]
  [--source PATH] [--modelfile-dir PATH]
bc250-model install CATEGORY [SELECTION] [OPTIONS]
```

`SELECTION` is `all`, one zero-based index, or a comma-separated set of indices
and ranges such as `0,2-4`. Only entries with `enabled = true` are selectable.
`--list` prints those entries without downloading them.

Install options:

- `--source PATH`: alternate TOML catalog.
- `--modelfile-dir PATH`: alternate packaged-template directory.
- `--host HOST[:PORT]`: Ollama API endpoint.
- `--revision REVISION`: Hugging Face commit, tag, branch or `latest`; requires
  one selected entry.
- `--sha256 DIGEST`: exact downloaded-file checksum; requires one selected
  entry.
- `--destination PATH`: GGUF destination root.
- `--min-free-bytes BYTES`: minimum free space before a new download.

The manager renders a runtime Modelfile for the selected revision and GGUF path.
Registered names stay aligned with the full-name packaged templates. It never
rewrites the packaged template. Relevant environment
overrides are `SOURCE_FILE`, `MODELFILE_SOURCE_DIR`, `DEST`, `MODELFILE_DIR`,
`HF_TOKEN`, `HF_HOME`, `DOWNLOAD_DIR`, `OLLAMA_HOST` and `OLLAMA_URL`. Explicit
CLI options take precedence where both forms exist.

`--provider ollama|download-only` constrains `resolve`. The MTP runner always
uses the separate `mtp` catalog and `--provider download-only`, so an ordinary
Ollama experiment cannot be passed to llama.cpp.

Compatibility commands:

```bash
sudo bc250-fetch-models [SELECTION]
sudo bc250-fetch-experiments [SELECTION]
sudo bc250-fetch-experiments --list
sudo bc250-fetch-mtp [SELECTION]
```

### Upgrade behavior

RPM upgrades preserve operator-edited TOML catalogs through `%config(noreplace)`
and restart the web services. Pre-TOML shell catalogs are not migrated; copy
wanted selections into the TOML catalogs manually before upgrading.

Version 0.6.2 gave every Modelfile its full registered model name. An upgraded
0.6.1 catalog is therefore kept as the existing config, but must be merged with
the new `.rpmnew` catalog before another fetch. No executable migration is run.

Version 0.6.3 adds `/etc/bc250-llm-server/mtp-models.toml` as a separate
`%config(noreplace)` catalog. On an upgrade from 0.6.2, the existing experiment
catalog is deliberately preserved and may still contain its two old MTP tables.
Merge `experiments-models.toml.rpmnew` into the active experiment catalog, and
copy any wanted MTP enablement into `mtp-models.toml`. No executable migration
edits operator configuration.

## Task model setup

```bash
sudo bc250-setup-task-model
```

Overrides:

- `TASK_BIND` (`0.0.0.0`) and `TASK_PORT` (`11435`).
- `TASK_MODEL_SELECTION` (`all`), `TASK_MODEL_REVISION` and
  `TASK_MODEL_SHA256`.
- `HF_TOKEN` and `HF_HOME`.
- `MODEL_MANAGER`, `SOURCE_FILE` and `MODELFILE_SOURCE_DIR` for source-tree or
  test use.

The helper creates the isolated `ollama-task.service`, waits for its API, then
uses the unified manager. Keep its port blocked from the LAN.

## Coding models and agent

```bash
sudo bc250-setup-coding-agent
bc250-code {generate|refactor|review|document|test} INPUT OUTPUT [INSTRUCTION]
bc250-code-commit [--yes]
bc250-gitea-review OWNER/REPOSITORY NUMBER [--output FILE] [--post]
```

The setup creates `ollama-agent.service` on port `11436` and installs both
enabled coding-catalog entries by default. Setup overrides are
`CODING_AGENT_BIND`, `CODING_AGENT_PORT`, `CODING_AGENT_SELECTION`,
`CODING_AGENT_REVISION`, `CODING_AGENT_SHA256`, `CODING_AGENT_GGUF_DIR`,
`CODING_AGENT_MIN_FREE_BYTES` (`8589934592`), `HF_TOKEN` and `HF_HOME`.
Revision and checksum overrides require a single selected entry.

For agent requests, `CODING_AGENT_MODEL` selects an installed model and
`OLLAMA_HOST`/`OLLAMA_URL` override the default `127.0.0.1:11436` endpoint.

Agent limits are `CODING_AGENT_MAX_INPUT_BYTES` (default `60000`) and
`CODING_AGENT_MAX_DIFF_BYTES` (`60000` for commits, `50000` for Gitea review).
Gitea connection settings belong in the mode-0600 example configuration;
`GITEA_INSECURE=1` disables TLS verification and is only for an isolated test
environment. The helpers do not stage, push, approve or merge.

## Experiments and MTP

Ollama experiments and download-only MTP models use separate editable catalogs:

```bash
sudoedit /etc/bc250-llm-server/experiments-models.toml
sudo bc250-fetch-experiments
BASELINE_MODEL=MODEL bc250-compare-experiments

sudoedit /etc/bc250-llm-server/mtp-models.toml
bc250-model list mtp --all
sudo bc250-fetch-mtp
LLAMACPP=/path/to/llama-server bc250-run-mtp {27b|4b|ID}
```

MTP overrides are `LLAMACPP`, `PORT` (`8090`), `CTX` and `DRAFT_N_MAX`.
Comparison overrides are `OLLAMA_URL`, `MTP_URL`, `BASELINE_MODEL`,
`NUM_PREDICT` and `PROMPT`.

## Ollama, memory and swap

```text
bc250-install-ollama
bc250-ollama-profile {status|balanced|max-context|reset}
bc250-memory-profile {status|recommend|apply-full|apply-safe|remove}
bc250-swap-profile {status|apply|remove}
bc250-pull-embedding-model
```

- `OLLAMA_VERSION` selects the reviewed version or `latest` for the installer.
- `BC250_ASSUME_YES=1` confirms memory/swap changes for automation.
- `SWAP_GIB` (`16`) and `ZRAM_MIB` (`2048`) size the swap profile.
- `EMBED_MODEL` (`nomic-embed-text`) selects the embedding model.

See [`../models/embedding/README.md`](../models/embedding/README.md) for the
embedding workflow.

Memory and swap changes are explicit and may require a reboot. The RPM does not
apply them during installation.

## Governor and compute units

```text
bc250-cu-status
bc250-40cu
bc250-40cu {verify|live-status|live-full|live-stock}
bc250-40cu health-test MODEL
bc250-40cu {mask|unmask} WGP
bc250-40cu {build|status|enable|disable|restore}
```

Live WGP-table changes require `APPLY-WGP-TABLE`. The replacement-module
`enable` path requires `ENABLE-40CU` and a reboot. Neither path changes the
operator’s governor clock/voltage policy.

## Verification and diagnostics

These tools have different execution contexts and are intentionally separate:

```bash
sudo bc250-verify
RUN_MODEL_TESTS=1 sudo bc250-verify
bc250-verify-lan SERVER_IP
sudo llm-run-diagnose --no-load
MODEL=MODEL_NAME LOAD_SECONDS=120 NUM_PREDICT=2000 sudo llm-run-diagnose
```

`bc250-verify` is the post-RPM check on the server. `bc250-verify-lan` runs from
another machine; `HTTP_PORT` changes its expected web port. The diagnostic is
only for model-run investigation: without `--no-load` it generates sustained
load. It also accepts `OLLAMA_URL`.

## Benchmark and sensors

```bash
bc250-benchmark
bc250-check-temp [--watch]
SENSOR_INTERVAL=2 /usr/libexec/bc250-llm-server/log_sensors.sh FILE
```

Benchmark controls:

- Selection/output: `ALLOW_EMBED`, `BOARD_NOTE`, `OLLAMA_URL`.
- Thinking: `THINK_MODE=false|true|low|medium|high|max`.
- Work sizes: `NUM_PREDICT_SHORT`, `NUM_PREDICT_LONG`,
  `NUM_PREDICT_LATENCY`, `CTX_POINTS`.
- Repetition: `REPEATS`, `LATENCY_REPEATS`, `RUN_LATENCY`,
  `THROTTLE_WINDOWS`.
- Requests: `KEEP_ALIVE`, `CONNECT_TIMEOUT`, `REQUEST_TIMEOUT`, `MAX_RETRIES`.
- Cold-start checks: `UNLOAD_TIMEOUT`, `UNLOAD_POLL_INTERVAL`,
  `COLD_UNLOAD_WAIT`.
- Analysis thresholds: `OVERHEAD_WARN_S`, `EARLY_EOS_FRACTION`.
- Latency prompts: `CHAT_SYSTEM_PROMPT`, `CHAT_PROMPT`.

The benchmark writes `results_TIMESTAMP.csv` and a matching `.meta.txt` file in
the current directory. Sensor logging also accepts `SENSOR_PATTERN`.

## Open WebUI maintenance

Configuration is read from `/etc/bc250-llm-server/maintenance.env`. Supported
settings are documented in the installed example and include `OWUI_URL`,
`OWUI_API_KEY`, `DRY_RUN`, `MAX_AGE_DAYS`, `MAX_TOTAL_GB`, `WARMUP_MODEL`,
`WARMUP_KEEP_ALIVE`, backup retention/output/rollback directories, and
`SAFE_SUSPEND_PORTS`.

```bash
systemctl list-timers 'owui-*'
sudo systemctl enable --now owui-backup-config.timer
sudo systemctl enable --now owui-backup-users.timer
sudo systemctl enable --now owui-prune.timer
sudo systemctl enable --now owui-warmup.timer
```

Keep pruning in dry-run mode until its output has been reviewed. Restore tools
require explicit confirmation and create rollback data first.
