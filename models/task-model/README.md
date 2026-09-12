# Isolated Open WebUI task models

## Setup and verify

```bash
sudo bc250-model install task task-lfm25-1.2b-instruct-liquidai-q6-k

curl -fsS http://127.0.0.1:11435/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"task-lfm25-1.2b-instruct-liquidai-q6-k:latest","messages":[{"role":"user","content":"Return only a short title for: Installing Fedora on a BC-250"}],"stream":false,"keep_alive":0}'
sleep 2
OLLAMA_HOST=127.0.0.1:11435 ollama ps
```

The package ships `ollama-task.service` statically on port `11435` with a separate
model store. It is part of required normal mode. With no selection,
`bc250-model install task` lists task Modelfiles and prompts. The service uses
`OLLAMA_KEEP_ALIVE=0`; the final command should show no resident task model.

Current packaged task models:

- `task-lfm25-1.2b-instruct-liquidai-q6-k` — **default**. Real BC-250 evidence on 2026-09-12: 15/18 direct
  qualification (5/6 each round), 15/18 again through the actual Open WebUI
  title/tag/query endpoints with the package-owned prompts, and 9/9 successful
  true-overlap trials while warm GPT-OSS remained resident. The known residual
  miss is the French-title relevance fixture.
- `task-gemma3-1b-unsloth-ud-q4-k-xl` — retained as the previous low-memory fallback/control, but no
  longer selected by default.

The default LFM Modelfile deliberately omits a fixed `SYSTEM` prompt. A generic
SYSTEM was tested and caused task-shape contamination (for example title responses
that also emitted tags/search-query fields). Open WebUI therefore owns the exact
title/tag/retrieval-query prompt templates in `openwebui/desired-state.json`. The
direct `bc250-benchmark task` path reads those same templates so direct and live
qualification cannot silently drift to different prompt contracts again.

Keep port `11435` blocked from untrusted networks. The package adds
`http://host.containers.internal:11435` as the task connection. Title and tag
generation are enabled. Retrieval-query generation remains off by default and
should be enabled deliberately when required. Autocomplete, follow-ups and
web-search query generation remain off because repeated task loads can overlap a
larger warm chat model.

## Promotion lessons

Do not promote a task model from the direct score alone. This evaluation found a
15/18 direct result that collapsed to 6/18 through real Open WebUI while Open
WebUI's upstream default task prompts were still in use. Applying the package-owned
prompt contract restored 15/18 live. Future task candidates therefore need:

1. direct task qualification against the package-owned prompt templates;
2. a real authenticated Open WebUI task-path check using those same templates;
3. sequential warm-main coexistence/resource evidence; and
4. true simultaneous main/task generation before promotion.

The earlier Qwen3.8 4B Distill task candidate is retired from routine discovery:
although quality was promising, simultaneous residency with warm GPT-OSS
OOM-killed the task service. The smaller promoted LFM survived nine true-overlap
trials with no additional swap growth or serious GPU/OOM warning.
