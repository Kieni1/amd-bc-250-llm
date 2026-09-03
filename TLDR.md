# BC-250 LLM appliance: quick sheet

## Install

Keep the binary RPM beside the repository bootstrap:

```bash
sudo ./install
```

The bootstrap installs the RPM and invokes the packaged `bc250-install`,
which owns Fedora update policy. Rerun after the requested primary reboot with:

```bash
sudo bc250-install
```

Use `sudo bc250-install --models-only` to resume only models/Open WebUI. There is
one model prompt; select global indexes/ranges/names or `recommended`,
`production`, `all`, and press Enter to skip. Unattended selection uses
`BC250_MODEL_SELECTION`.

Before 1.0 this is intentionally a green-field appliance flow. Kernel update and
the TTM-only profile are prepared before one primary reboot; 40-CU is then built
for the exact running kernel. A second reboot is requested only when an already
persistent 40-CU configuration needs the prepared module loaded.

## Verify and open the UI

```bash
sudo bc250-status
sudo bc250-verify
bc250-verify-lan SERVER_IP
```

```bash
sudo bc250-storage status
sudo bc250-storage dedupe
```

`dedupe` preserves both logical files and shares verified identical XFS extents;
`df` reflects reclaimed capacity even when `du` still counts shared extents twice.

Open `http://SERVER_IP/` from the trusted LAN. The installer can initialize the
Open WebUI administrator/API baseline interactively; if skipped, run
`sudo bc250-openwebui-setup init`. HTTP is not encrypted.

For a document/RAG pilot, install the document answer model and embedding model,
then follow [`docs/RAG.md`](docs/RAG.md). Operator documents live under `/srv/bc250-documents`; run `sudo bc250-rag-import plan` before any bulk sync.

## Models

```bash
sudo bc250-model list production
sudo bc250-model list experiments
sudo bc250-model list task
sudo bc250-model list agentic
sudo bc250-model list embedding
bc250-ocr list
sudo bc250-rag-import plan /srv/bc250-documents

sudo bc250-model install production
sudo bc250-model install experiments
sudo bc250-setup-embedding-model
sudo bc250-setup-task-model
sudo bc250-openwebui-setup init
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
bc250-benchmark                       # neutral generation comparison
BENCH_MODE=production bc250-benchmark    # generic workload + deployed config
bc250-benchmark embeddings
bc250-benchmark ocr
bc250-benchmark task
sudo bc250-agent-mode enter
bc250-benchmark agent                 # exclusive agent correctness lane, port 11436
sudo bc250-agent-mode leave
bc250-check-temp --once
sudo llm-run-diagnose --no-load
sudo bc250-revalidate status

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
  ollama.service ollama-task.service ollama-embedding.service \
  open-webui.service tika.service nginx.service
curl -fsS http://127.0.0.1:11434/api/tags
curl -fsS http://127.0.0.1:11437/api/tags
```

Normal mode uses task `11435` and embedding `11437` alongside main `11434`.
Agent `11436` is exclusive and disabled at boot. Keep ports `11434`–`11437`
blocked from untrusted networks.

## Remove

```bash
# Keep models and persistent application data
sudo dnf remove bc250-llm-server.x86_64

# Explicitly purge the complete appliance setup
sudo bc250-uninstall
```

See [`docs/COMMANDS.md`](docs/COMMANDS.md) for every installed command and
[`docs/UNINSTALL.md`](docs/UNINSTALL.md) before a full purge.

## Benchmark quick checks

```bash
bc250-benchmark usecase
bc250-benchmark translation
bc250-benchmark rag-quality
bc250-benchmark embeddings
bc250-benchmark ocr
bc250-benchmark task
```

For a full live-appliance pass use `sudo bc250-revalidate start`; it is opt-in,
root-only, and stores its final tarball under `/var/lib/bc250-llm-server/revalidation/results/`.
See `cmd/benchmark/README.md` / installed `BENCHMARK.md` for revalidation, optional
warm-prefix, RAG tuning and sustained thermal qualification procedures.

