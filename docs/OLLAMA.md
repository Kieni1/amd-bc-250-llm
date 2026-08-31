# Ollama

Ollama is installed separately from the RPM. The guided installer handles the
normal setup; use the commands below for an explicit reinstall or runtime
change.

Package standard: **Ollama v0.32.15**. The helper installs this version unless `OLLAMA_VERSION` is deliberately overridden.

## Install and verify

```bash
sudo bc250-install-ollama
# Deliberate runtime comparison only:
sudo OLLAMA_VERSION=VERSION bc250-install-ollama
ollama --version
sudo systemctl status ollama.service --no-pager -l
curl -fsS http://127.0.0.1:11434/api/tags
```

The helper installs official Ollama under `/usr/local`, normalizes the `ollama`
account and storage, enables the service and waits for the local API. It avoids
keeping Fedora-packaged and official Ollama copies side by side.

The main service uses:

```text
HOME=/var/lib/ollama
OLLAMA_MODELS=/var/lib/bc250-llm-server/ollama/main
OLLAMA_HOST=0.0.0.0:11434
```

Optional task and agent setup create `ollama-task.service` on `11435` and
`ollama-agent.service` on `11436`, each with a separate store. The task service
uses `OLLAMA_KEEP_ALIVE=0` so background tasks unload immediately. The main/task
separation is intentional. The coding-agent service is expected to be used
exclusively rather than alongside a large main-model request. All instances still
share the BC-250 unified-memory pool.

## Runtime profiles

```bash
sudo bc250-ollama-profile status
sudo bc250-ollama-profile balanced
sudo bc250-ollama-profile max-context
sudo bc250-ollama-profile reset
```

| Profile | Context | KV cache | Parallel/loaded models |
|---|---:|---|---|
| Balanced | 32,768 | q8_0 | 1 / 1 |
| Max context | 65,536 | q4_0 | 1 / 1 |

Both enable flash attention. The max-context profile reduces KV-cache memory at
a possible quality cost. Service profiles do not modify individual Modelfiles.

## Benchmark API baseline

`bc250-benchmark` targets the Ollama **0.32.15** request schema. Neutral generation
uses the top-level `/api/generate` `system` override without `raw=true`; production
mode omits the override. `think` may be omitted, boolean, or
`low`/`medium`/`high`/`max` as supported by 0.32.15. Embedding tests use
`/api/embed` with `truncate=false`; model allocation comes from `/api/ps`. The
dedicated `bc250-benchmark agent` lane uses `/api/chat` on port 11436 and does
not globally force reasoning off.

The benchmark samples BC-250 temperature and memory/AMDGPU counters during each
request. `RUN_THERMAL=1` adds sustained decode windows; no second `watch` terminal
is required for peak resource values.

## Network exposure

The host listeners let rootful Open WebUI reach Ollama. They are unauthenticated
and must remain blocked from untrusted networks:

```bash
sudo firewall-cmd --list-all
ss -ltnp | grep -E ':(11434|11435|11436)\b'
```

## Updating safely

Do not replace the package-standard **0.32.15** merely because a newer Ollama is
available. Review release notes and smoke-test each Vulkan update with:

1. a small known-good model;
2. the largest intended model;
3. a representative long prompt; and
4. `sudo bc250-verify` plus the kernel journal.

```bash
sudo OLLAMA_VERSION=VERSION bc250-install-ollama
sudo OLLAMA_REINSTALL=1 OLLAMA_VERSION=VERSION bc250-install-ollama
sudo bc250-verify
```

Recent upstream AMD shared-memory reports include Vulkan device loss,
command-submission memory failures and compute-ring timeouts. Verification
prints the exact Ollama version and scans recent Ollama/kernel logs for those
patterns. A smaller `PARAMETER num_batch 128` in a copied operator Modelfile is
a diagnostic for long-prompt prefill failures, not a package-wide default or a
confirmed BC-250 fix.
