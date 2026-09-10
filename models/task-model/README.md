# Isolated Open WebUI task models

## Setup and verify

```bash
sudo bc250-model install task task-gemma3-1b-unsloth-ud-q4-k-xl

curl -fsS http://127.0.0.1:11435/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"task-gemma3-1b-unsloth-ud-q4-k-xl:latest","messages":[{"role":"user","content":"Return only a short title for: Installing Fedora on a BC-250"}],"stream":false,"keep_alive":0}'
sleep 2
OLLAMA_HOST=127.0.0.1:11435 ollama ps
```

The package ships `ollama-task.service` statically on port `11435` with a separate model
store. It is part of required normal mode. With no selection `bc250-model install task` lists task Modelfiles and prompts. The service uses
`OLLAMA_KEEP_ALIVE=0`; the final command should show no resident task model.

Current packaged task model:

- `task-gemma3-1b-unsloth-ud-q4-k-xl` — current default: the 2026-08-31
  Open WebUI 0.11.3 fixture produced usable structure/JSON in all 6 cases,
  although language adherence remained weak (2/6 matched the requested language);

The task Modelfile deliberately omits a fixed `SYSTEM` prompt: Open WebUI supplies a
different task prompt for title, tags and query rewriting. Run
`bc250-benchmark task MODEL...` before changing the Open WebUI local task model.
The benchmark accepts the same fenced/surrounded JSON shape that Open WebUI
0.11.3 extracts, while also reporting whether the response was strict raw JSON
and an informational language-adherence hint.

Keep port `11435` blocked from untrusted networks. Add
`http://host.containers.internal:11435` as the task connection. Start with title
and tag generation enabled. Keep retrieval-query generation off for the baseline
and enable it only when deliberately testing query rewriting. Leave autocomplete,
follow-ups and web-search query generation off until needed because repeated task
loads can overlap a larger warm chat model.

## Hardware/UX decision for Qwen3.8 4B

`exp-qwen38-4b-distill-empero-q6-k` remains an opt-in experiment rather than the
Open WebUI task default. It scored materially better in focused task experiments,
but real BC-250 overlap with the 10.8 GiB GPT-OSS main model drove available
memory to the edge and the kernel OOM-killed the task service. Serializing the
4B task model would also evict a warm large chat model and impose a large cold-load
penalty on the next user message. The packaged 1B task lane therefore remains the
safer low-latency companion while the 4B candidate stays available for deliberate
manual experiments.
