# BC-250 LLM appliance: quick sheet

## Install

Keep the binary RPM beside the repository's installer, then run:

```bash
sudo ./install
```

Rerun it after the requested reboot. Resume only model selection with:

```bash
sudo ./install --models-only
```

The model stage asks separately for production, task, agentic, embedding,
experiment and MTP models. Enter skips only the current category; MTP entries
remain disabled by default outside an explicit guided selection.

## Verify and open the UI

```bash
sudo bc250-status
sudo bc250-verify
bc250-verify-lan SERVER_IP
```

Open `http://SERVER_IP/` from the trusted LAN and register the first
administrator. HTTP is not encrypted.

For a document/RAG pilot, install the document answer model and embedding model,
then follow [`docs/RAG.md`](docs/RAG.md) before uploading confidential files.

## Models

```bash
bc250-model list production
bc250-model list experiments
bc250-model list task
bc250-model list agentic
bc250-model list embedding
bc250-ocr list

sudo bc250-fetch-models
sudo bc250-fetch-experiments
sudo bc250-fetch-embeddings
sudo bc250-setup-task-model
sudo bc250-setup-coding-agent

# Review before removing source GGUF and Ollama registration
sudo bc250-model cleanup production --list
sudo bc250-model cleanup production MODEL-NAME
```

Selections accept a full name, displayed index, range such as `0,2-4`, or
`all`. With no selection, the command prompts; Enter cancels.

## Profiles and hardware

```bash
sudo bc250-memory-profile status
sudo bc250-swap-profile status
sudo bc250-ollama-profile status
sudo bc250-cu-status
sudo bc250-40cu status
```

The guided installer applies the memory/swap profiles and prepares the
kernel-specific 40-CU module, but leaves extra CUs disabled. Start with
`sudo bc250-40cu`, then test the feasible CU count for the individual board;
see [`docs/CU-UNLOCK.md`](docs/CU-UNLOCK.md).

## Operations

```bash
bc250-benchmark
bc250-check-temp --once
sudo llm-run-diagnose --no-load

sudo bc250-maintenance setup --defaults
sudo bc250-maintenance run backup
sudo bc250-maintenance clean-cache
```

`setup --defaults` enables verified local backups only. Guided maintenance can
also configure dry-run upload pruning, optional warm-up and optional after-hours
power saving.

## Services

```bash
sudo systemctl status \
  cyan-skillfish-governor-smu.service \
  ollama.service open-webui.service tika.service nginx.service
curl -fsS http://127.0.0.1:11434/api/tags
```

Optional task and agent services use `ollama-task.service` on port `11435` and
`ollama-agent.service` on `11436`. Keep ports `11434`–`11436` blocked from
untrusted networks.

## Remove

```bash
# Keep models and persistent application data
sudo dnf remove bc250-llm-server.x86_64

# Explicitly purge the complete appliance setup
sudo bc250-uninstall
```

See [`docs/COMMANDS.md`](docs/COMMANDS.md) for every installed command and
[`docs/UNINSTALL.md`](docs/UNINSTALL.md) before a full purge.
