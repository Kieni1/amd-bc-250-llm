# Benchmark

The package standard is **Ollama 0.33.2**. Keep the Ollama version, model
revision, CU/governor state and cooling setup fixed when comparing runs.

## Generation

```bash
# Cross-model comparison: neutral SYSTEM override + deterministic sampling
bc250-benchmark

# Faster/lower-context pass
BENCH_PROFILE=conservative bc250-benchmark

# Production-configuration comparison: keep registered SYSTEM and sampling
BENCH_MODE=production bc250-benchmark

# Specific registered models
bc250-benchmark generation MODEL_A MODEL_B

# Generic generation on the agent store (performance comparison only)
OLLAMA_URL=http://127.0.0.1:11436 bc250-benchmark generation MODEL
```

`BENCH_MODE=neutral` is the default. Ollama `/api/generate` receives a per-request
`system` override; `/api/chat` receives the same text as a system message. The
registered model is not modified and its normal renderer/template is still used.
`BENCH_MODE=production` omits that override and does not override temperature,
`top_p` or `top_k`. It is a **production-configuration** comparison using the same
generic generation workload; it is not yet the deferred role-specific Office/RAG/
translation use-case suite.

`THINK_MODE=auto` preserves the package's model-family policy: GPT-OSS uses
`medium`, packaged stock Qwen3.5/Qwen3-4B non-thinking profiles use `false`, and
Gemma4/native-reasoning families leave `think` unset. Explicit
`THINK_MODE=omit|false|true|low|medium|high|max` is available for a deliberate
comparison. These values match Ollama 0.33.2's request API.

The standard generation suite records cold/warm chat latency, loaded decode,
document prefill and a context-capacity curve. The prefill request and every
context point start from an unloaded runner so Ollama 0.33.x prompt-cache reuse
cannot make later shared-prefix points look artificially faster; `load_duration_s`
remains separate from `prompt_eval_duration_s`. A run labelled `cold_chat` is
started only after Ollama `/api/ps` confirms the previous model is unloaded; an
unload failure aborts that cold measurement instead of silently recording a warm
load. `RUN_THERMAL=1` adds sustained decode windows. Early-stop warnings are emitted only for an unusually tiny natural
`done_reason=stop` (10% of the requested cap by default); a complete answer that
finishes normally is not treated as suspicious. Reaching the requested limit with
`done_reason=length` is not an early-EOS failure.

Ollama 0.33.2 uses one shared `num_predict` cap for reasoning plus the final
answer. The moderate latency test therefore keeps 96 tokens for explicit
non-thinking (`think=false`) profiles but uses 512 for reasoning-capable/unset
policies; the conservative profile uses 64/384. LFM2.5 stays on the larger
latency budget even during an explicit `think=false` experiment because the
measured Ollama/model path continued to emit native reasoning. `NUM_PREDICT_LATENCY` keeps its
legacy behavior as an override for both unless `NUM_PREDICT_LATENCY_THINKING` is
set separately. Throughput, context and thermal caps are unchanged. CSV/JSONL
now record `answer_started`, `answer_chars` and `thinking_chars`: TTFC means first
reasoning *or* answer content, while TTFA is the first final-answer content and
may legitimately be empty if the shared generation cap is exhausted first.

Repeated prompts are varied only with leading blank lines instead of a visible
request-id marker, avoiding benchmark metadata that a reasoning model may spend
tokens interpreting. For qualitative review, prefer the streamed `/api/chat`
latency records because they preserve Ollama's separate `thinking` and final
`content` fields. Some model/template families can expose native reasoning markers
inside the raw `/api/generate` response; those generate lanes remain intended for
throughput/prefill/runtime measurements. Context-capacity truncation warnings and
near-limit notes are persisted in the JSONL sidecar as well as printed.

## Embeddings

```bash
bc250-benchmark embeddings
bc250-benchmark embeddings embed-jina-v5-small-retrieval-q4-k-m embed-qwen3-0.6b-q8-0
```

The packaged DE/FR/EN office fixture measures Recall@1, Recall@3, MRR,
cross-language retrieval and warm input throughput. It also includes near-duplicate
current/archived lease facts and similar invoice references so a model cannot pass
only by separating unrelated topics. Jina uses `Query:` /
`Document:`; Qwen3 Embedding uses the documented English retrieval instruction
on queries and no content prefix. The packaged Jina GGUF includes upstream
`pooling_type` metadata required for reliable embedding-model detection. Use the
same prefix scheme in Open WebUI and reindex when switching embedding models or
when replacing an older Jina GGUF with the refreshed package file.

## OCR

```bash
bc250-benchmark ocr
bc250-ocr test glm /PATH/TO/REAL-PAGE.png
```

The benchmark uses deterministic German, French and mixed office-page images and
checks token precision/recall/F1, normalized character similarity, exact required-
field recall, key-field reading order and runtime. The packaged comparison set
is GLM-OCR plus OvisOCR2; the scorer keeps model-specific prompt support for
operator-added OCR experiments. OCR must preserve the source language; review
and clean the result before putting canonical Markdown under the RAG `active/`
tree. The packaged fixtures are regression/comparison tests, not a substitute for
a representative real scan corpus.

## Task model

```bash
bc250-benchmark task
```

The task suite targets `http://127.0.0.1:11435` by default and mirrors the
relevant Open WebUI **0.11.2** task behavior in compact fixtures: title uses the
latest two messages, tags the latest six (with the short-chat `General` fallback),
and retrieval-query generation the latest six plus the current date. It parses
the JSON object the same tolerant way Open WebUI 0.11.2 does (including fenced or
surrounded JSON), while separately reporting `strict_json`. It checks structure,
simple content relevance, latency and an informational DE/FR/EN `language_hint`;
the language hint is not a hard correctness gate. Requests use
`keep_alive=0`, matching the isolated task service. The Open WebUI container
leaves 0.11.2 `TASK_MODEL_PARAMS` at `{}` until this benchmark demonstrates a
reason to tune it. Its CSV deliberately keeps only the small telemetry subset
useful for this short background workload.

## Agent/coding

```bash
bc250-benchmark agent
bc250-benchmark agent agentic-ornith15-9b-ornith-q5-k-m
```

This lane defaults to `http://127.0.0.1:11436`. Stop/avoid a large main-model
workload while using it. The small fixture set checks Bash syntax, Python syntax
and required structured output without executing model-generated code. A response
passes only when a non-empty final answer has valid syntax/structure and the
fixture's required elements both pass. Native model reasoning is not globally
forced off. The cases provide 768-1024 shared output tokens so reasoning-oriented
models have room to reach final code, and JSONL records thinking/final character
counts, `eval_count` and `done_reason` for starvation diagnosis. The lane also leaves
temperature/top-p/top-k to the deployed Modelfile by default; set
`AGENT_TEMPERATURE=0` only for an explicit deterministic comparison. It does not
override the agent service keep-alive and unloads each benchmarked model after
the run.

## Telemetry and outputs

Generation, embedding and OCR lanes sample the full hardware/resource set during
the request rather than relying on a second terminal. One AMD DRM device is
selected (prefer the boot VGA device; override with `BC250_DRM_CARD=cardN`) and
its on-die/edge temperature is used for the 80/83/85 °C thresholds:

- peak and p95 GPU edge temperature plus time at/above 80/83/85 °C;
- selected-GPU busy percentage and observed min/max GPU clock;
- selected AMDGPU `mem_info_vram_used` / `mem_info_gtt_used` peaks when exposed;
- minimum Linux `MemAvailable` and maximum swap use;
- Ollama `/api/ps` resident size, reported `size_vram` and allocated context.

On the BC-250 these are overlapping views of unified memory. Do **not** add host,
VRAM and GTT values as separate pools or automatically infer that a larger quant
will fit. Use them as same-board headroom signals and validate a larger quant
with an actual run.

Generation produces CSV + JSONL response sidecar + JSON metadata. Category runs
produce the same three-file pattern. Category metadata is intentionally lighter
than generation metadata but still records Ollama version and model identity.
Task and agent CSVs intentionally keep a smaller telemetry subset.

Useful overrides include `OLLAMA_URL`, `BENCH_MODE`, `THINK_MODE`,
`BENCH_PROFILE`, `RUN_LATENCY`, `RUN_CONTEXT`, `RUN_THERMAL`, `REPEATS`,
`TELEMETRY_INTERVAL`, `BC250_DRM_CARD`, `KEEP_ALIVE`, `CTX_POINTS`,
`AGENT_TEMPERATURE`, `NUM_PREDICT_LATENCY_THINKING` and the other `NUM_PREDICT_*`
values. `KEEP_ALIVE` applies to the generation/embedding/OCR
paths; task keeps `0` and the agent lane relies on its service policy then unloads.
