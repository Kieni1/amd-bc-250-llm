# Benchmark

The package standard is **Ollama 0.32.15**. Keep the Ollama version, model
revision, CU/governor state and cooling setup fixed when comparing runs.

## Generation

```bash
# Cross-model comparison: neutral SYSTEM override + deterministic sampling
bc250-benchmark

# Faster/lower-context pass
BENCH_PROFILE=conservative bc250-benchmark

# Test the registered Modelfile as deployed (SYSTEM and sampling unchanged)
BENCH_MODE=production bc250-benchmark

# Specific registered models
bc250-benchmark generation MODEL_A MODEL_B

# Agentic store; use the agent service exclusively while benchmarking it
OLLAMA_URL=http://127.0.0.1:11436 bc250-benchmark generation MODEL
```

`BENCH_MODE=neutral` is the default. Ollama `/api/generate` receives a per-request
`system` override; `/api/chat` receives the same text as a system message. The
registered model is not modified and its normal renderer/template is still used.
`BENCH_MODE=production` omits that override and does not override temperature,
`top_p` or `top_k`.

`THINK_MODE=auto` preserves the package's model-family policy: GPT-OSS uses
`medium`, packaged stock Qwen3.5/Qwen3-4B non-thinking profiles use `false`, and
Gemma4/native-reasoning families leave `think` unset. Explicit
`THINK_MODE=omit|false|true|low|medium|high|max` is available for a deliberate
comparison. These values match Ollama 0.32.15's request API.

The standard generation suite records cold/warm chat latency, loaded decode,
document prefill and a context-capacity curve. `RUN_THERMAL=1` adds sustained
decode windows. Early-stop warnings are emitted only for a short
`done_reason=stop`; reaching the requested limit with `done_reason=length` is not
an early-EOS failure.

## Embeddings

```bash
bc250-benchmark embeddings
bc250-benchmark embeddings embed-jina-v5-small-retrieval-q4-k-m embed-qwen3-0.6b-q8-0
```

The packaged DE/FR/EN office fixture measures Recall@1, Recall@3, MRR,
cross-language retrieval and warm input throughput. Jina uses `Query:` /
`Document:`; Qwen3 Embedding uses the documented English retrieval instruction
on queries and no content prefix. Use the same prefix scheme in Open WebUI and
reindex when switching embedding models.

## OCR

```bash
bc250-benchmark ocr
bc250-ocr test dots /PATH/TO/REAL-PAGE.png
```

The benchmark uses deterministic German, French and mixed office-page images and
checks text/field recall plus runtime. GLM, dots.ocr, OvisOCR2 and Chandra receive
model-specific extraction prompts. OCR must preserve the source language; review
and clean the result before putting canonical Markdown under the RAG `active/`
tree. The packaged fixtures are regression/comparison tests, not a substitute for
a representative real scan corpus.

## Task model

```bash
bc250-benchmark task
```

The task suite targets `http://127.0.0.1:11435` by default and exercises Open
WebUI 0.11-style title, tag and retrieval-query prompts in German, French and
English. It checks JSON shape, simple content relevance and latency. Requests use
`keep_alive=0`, matching the isolated task service.

## Telemetry and outputs

All benchmark lanes sample hardware/resource telemetry during the request rather
than relying on a second terminal:

- peak and p95 temperature plus time at/above 80/83/85 °C;
- GPU busy percentage and observed min/max GPU clock;
- AMDGPU `mem_info_vram_used` / `mem_info_gtt_used` peaks when exposed;
- minimum Linux `MemAvailable` and maximum swap use;
- Ollama `/api/ps` resident size, reported `size_vram` and allocated context.

On the BC-250 these are overlapping views of unified memory. Do **not** add host,
VRAM and GTT values as separate pools or automatically infer that a larger quant
will fit. Use them as same-board headroom signals and validate a larger quant
with an actual run.

Generation produces CSV + JSONL response sidecar + JSON metadata. Category runs
produce the same three-file pattern. Metadata records Ollama version, model
digest/family/quant and benchmark policy so refreshed model registrations are not
silently compared as if they were identical.

Useful overrides include `OLLAMA_URL`, `BENCH_MODE`, `THINK_MODE`,
`BENCH_PROFILE`, `RUN_LATENCY`, `RUN_CONTEXT`, `RUN_THERMAL`, `REPEATS`,
`TELEMETRY_INTERVAL`, `KEEP_ALIVE`, `CTX_POINTS` and the `NUM_PREDICT_*` values.
