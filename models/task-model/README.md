# Isolated Open WebUI task models

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
store. With no selection it lists task Modelfiles and prompts. The service uses
`OLLAMA_KEEP_ALIVE=0`; the final command should show no resident task model.

Current candidates:

- `task-gemma3-1b-unsloth-ud-q4-k-xl` — smallest baseline and current default;
- `task-lfm25-2.6b-liquidai-q6-k` — multilingual DE/FR/EN comparison after the
  Gemma 3 1B run showed weak language adherence.

Both Modelfiles deliberately omit a fixed `SYSTEM` prompt: Open WebUI supplies a
different task prompt for title, tags and query rewriting. Run
`bc250-benchmark task MODEL...` before changing the Open WebUI local task model.
The benchmark accepts the same fenced/surrounded JSON shape that Open WebUI
0.11.2 extracts, while also reporting whether the response was strict raw JSON
and an informational language-adherence hint.

Keep port `11435` blocked from untrusted networks. Add
`http://host.containers.internal:11435` as the task connection. Start with title
and tag generation enabled. Keep retrieval-query generation off for the baseline
and enable it only when deliberately testing query rewriting. Leave autocomplete,
follow-ups and web-search query generation off until needed because repeated task
loads can overlap a larger warm chat model.
