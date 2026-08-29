# Isolated Open WebUI task model

## Setup and verify

```bash
sudo bc250-setup-task-model task-gemma3-1b-unsloth-ud-q4-k-xl

curl -fsS http://127.0.0.1:11435/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"task-gemma3-1b-unsloth-ud-q4-k-xl:latest","messages":[{"role":"user","content":"Return only a short title for: Installing Fedora on a BC-250"}],"stream":false,"keep_alive":0}'
sleep 2
OLLAMA_HOST=127.0.0.1:11435 ollama ps
```

The helper creates `ollama-task.service` on port `11435` with a separate model
store. With no selection it lists task Modelfiles and prompts. The model unloads
after each request; the last command should show no resident task model.

Keep port `11435` blocked from untrusted networks. Add this Open WebUI
connection:

```text
http://host.containers.internal:11435
```

Set the local task model to:

```text
task-gemma3-1b-unsloth-ud-q4-k-xl:latest
```

Start with title and tag generation enabled. Keep retrieval-query generation
off for the baseline and enable it only when deliberately testing query rewriting.
Leave autocomplete, follow-ups and web-search query generation off until needed.
Autocomplete can repeatedly load the task model while a larger chat model remains
warm. Run `bc250-benchmark task` for the packaged DE/FR/EN task comparison.

The Modelfile deliberately has no fixed `SYSTEM` prompt: Open WebUI supplies a
different task prompt for each title, tag or query-rewrite request.
