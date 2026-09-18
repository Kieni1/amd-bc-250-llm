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

- `task-lfm25-1.2b-instruct-liquidai-q6-k` — **default**. Promotion evidence remains 15/18 direct,
  15/18 through the actual Open WebUI title/tag/query endpoints with package-owned
  prompts, and 9/9 true-overlap trials while warm GPT-OSS remained resident. Current
  cheap canonical screens place its reference envelope around 4/6-5/6. The open
  quality issue is concise first-turn tag robustness; coexistence remains proven.
- `task-gemma3-1b-unsloth-ud-q4-k-xl` — retained as the previous low-memory fallback/control.
  The current task screen is about 2/6 with substantial language/relevance misses.

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

## Current candidate funnel

Use cheap rejection and expensive acceptance. A new candidate should normally pass:

1. one cheap canonical quality screen;
2. for any materially larger model, `quality-checks/task/20-survival-gate.sh` beside
   the warm production GPT-OSS model;
   The gate expects a separately staged, uniquely named temporary task alias; staging and
   definition parity are campaign responsibilities rather than hidden gate behavior.
3. concise first-turn DE/EN/FR usefulness/robustness;
4. repeated canonical direct quality;
5. authenticated Open WebUI task routing;
6. real first-turn persistence; and only then
7. true concurrent overlap/stability.

`exp-qwen3-4b-lmstudio-q6-k` is the current safety regression case: it scored 5/6
twice, but both exact-source task staging and a 4096-context task-tuned alias caused
global OOM and killed the warm main model. Do not retest it for the concurrent task
role unless the hardware/topology memory envelope changes. After any OOM experiment, use `quality-checks/task/30-appliance-recovery-check.sh` to
prove normal services, reload/warm GPT-OSS when necessary, confirm main residency and an
empty task lane, and detect any new serious faults caused by the recovery probe. The
preceding experiment's OOM remains visible as historical context but is not itself a
reason for the recovery check to fail.
