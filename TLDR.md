# BC-250 LLM appliance: quick sheet

This is the common-path operator sheet. Use [`docs/COMMANDS.md`](docs/COMMANDS.md)
for the complete command reference and the topic docs for rationale/recovery details.

## Install

Keep the binary RPM beside the repository bootstrap:

```bash
sudo ./install
```

The bootstrap installs the RPM and invokes `bc250-install`, which owns Fedora update
and appliance provisioning policy. After the requested primary reboot, resume with:

```bash
sudo bc250-install
```

Use `sudo bc250-install --models-only` to reconcile runtime topology, models and Open
WebUI without system/kernel setup. The task and Jina embedding models are baseline
infrastructure; the additional-model prompt accepts indexes/ranges/names or
`recommended`, `production`, `all`, and Enter skips extras. Unattended selection uses
`BC250_MODEL_SELECTION`.

Full interactive installs verify the core appliance first, then offer optional
maintenance/WOL and restricted Raspberry Pi companion setup. Models-only and
noninteractive runs do not silently enable those remote-maintenance features. Legacy
full-unit task/embedding/agent overrides are rejected rather than mixed with the
package-owned four-lane topology.

## Verify and open the UI

```bash
sudo bc250-status
sudo bc250-verify
bc250-verify-lan SERVER_IP
sudo bc250-storage status
sudo bc250-storage dedupe
```

`dedupe` keeps both logical files but shares verified identical XFS extents; `df`
reflects reclaimed capacity even when `du` counts both names. Open
`http://SERVER_IP/` from the trusted LAN. If Open WebUI initialization was skipped:

```bash
sudo bc250-openwebui-setup init
```

For RAG, keep operator documents under `/srv/bc250-documents` and plan before sync:

```bash
sudo bc250-rag-import plan /srv/bc250-documents
```

See [`docs/RAG.md`](docs/RAG.md) before bulk ingestion. HTTP is not encrypted; use
[`docs/HTTPS.md`](docs/HTTPS.md) if HTTPS is required.

## Models

```bash
bc250-model list production
bc250-model list experiments
bc250-model list task
bc250-model list agentic
bc250-model list embedding
bc250-model list mtp --all
sudo bc250-fetch-mtp qwen3.5-9b-mtp  # explicit opt-in MTP preparation
LLAMACPP=/opt/llama.cpp/build/bin/llama-server bc250-compare-mtp qwen3.5-9b-mtp

sudo bc250-model status agentic MODEL
sudo bc250-model status agentic MODEL --verbose
sudo bc250-model apply production
sudo bc250-model apply experiments
sudo bc250-model apply task
sudo bc250-model apply agentic
sudo bc250-model apply embedding

# Deliberately fetch source bytes again
sudo bc250-model refresh experiments MODEL

# Remove registration only; retain verified GGUF/state
sudo bc250-model unregister experiments MODEL

# Remove registration plus manager-owned GGUF/state
sudo bc250-model remove experiments MODEL
```

Selections accept a full name, displayed index, ranges such as `0,2-4`, or `all`.
`list` is catalog-only; use `sudo bc250-model status` when you need downloaded,
registration or Modelfile-drift state. `--verbose` also shows source repository/revision,
verified SHA-256 when available and resolved paths; `--online` checks moving upstream state. Enter cancels an interactive selection. Preserve
downloaded GGUFs where practical; use package lifecycle commands rather than deleting
`/var/lib` content manually.

## Profiles and hardware

```bash
bc250-memory-profile status
sudo bc250-memory-profile ensure
bc250-swap-profile status
sudo bc250-swap-profile ensure
bc250-ollama-profile status
sudo bc250-cu-status
sudo bc250-40cu status
```

The installer prepares the kernel-specific 40-CU module without silently enabling
persistent boot mode. Live routing is separate. Start the guided workflow with
`sudo bc250-40cu`; see [`docs/CU-UNLOCK.md`](docs/CU-UNLOCK.md) before changing routing.

## Operations and maintenance

```bash
bc250-benchmark generation --profile compare
bc250-benchmark generation --profile edge --mode production
bc250-benchmark embeddings
bc250-benchmark ocr
bc250-benchmark task

sudo bc250-agent-mode enter
bc250-benchmark agent
bc250-code review path/to/file review.md
sudo bc250-agent-mode leave

bc250-check-temp --once
sudo llm-run-diagnose --no-load
sudo bc250-revalidate status

sudo bc250-maintenance setup --defaults
sudo bc250-maintenance companion status
sudo bc250-maintenance contract
sudo bc250-maintenance run backup
sudo bc250-maintenance run prune
sudo bc250-maintenance clean-cache
```

`setup --defaults` enables verified local backups only. Guided maintenance can also
configure dry-run upload pruning, optional warm-up and optional after-hours safe power.
Pi integration uses office HTTP :80 and restricted SSH :22 only; Wake-on-LAN is an
Ethernet magic packet and opens no host firewall port.

## Services

```bash
sudo systemctl status \
  cyan-skillfish-governor-smu.service \
  ollama.service ollama-task.service ollama-embedding.service \
  open-webui.service tika.service nginx.service
curl -fsS http://127.0.0.1:11434/api/tags
curl -fsS http://127.0.0.1:11437/api/tags
```

Normal mode uses main `11434`, task `11435` and embedding `11437`. Agent `11436` is
exclusive and disabled at boot. Open WebUI is enabled by `bc250-install` only after
baseline model registration. Keep `11434`–`11437` blocked from untrusted networks.

## Remove

```bash
# Keep models and persistent application data
sudo dnf remove bc250-llm-server.x86_64

# Explicit greenfield appliance reset
sudo bc250-reset
```

Reset preserves `/srv/bc250-documents` and does not undo Fedora upgrades/filesystem
growth. `bc250-uninstall` remains a compatibility alias. Read
[`docs/UNINSTALL.md`](docs/UNINSTALL.md) before reset.

## Full qualification

```bash
sudo bc250-revalidate start --owui-token-file /root/owui-test.key
```

It is opt-in/root-only, includes authenticated production translation-role and RAG
checks when an Open WebUI key is supplied, and stores final bundles under
`/var/lib/bc250-llm-server/revalidation/results/`. See `cmd/benchmark/README.md`
(installed at the same relative path under `/usr/share/doc/bc250-llm-server/`) for
result directories, tuning commands, RAG qualification and thermal profiles.
