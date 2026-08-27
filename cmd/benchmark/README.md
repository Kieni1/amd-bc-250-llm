# Benchmark

```bash
bc250-benchmark

# Faster/lower-context comparison
BENCH_PROFILE=conservative bc250-benchmark

# Include embedding models and benchmark them through /api/embed
INCLUDE_EMBEDDINGS=1 bc250-benchmark

# Dedicated task/agent instances use the same benchmark with their own endpoint
OLLAMA_URL=http://127.0.0.1:11435 bc250-benchmark
OLLAMA_URL=http://127.0.0.1:11436 bc250-benchmark

# Optional sensor trace in another terminal
/usr/libexec/bc250-llm-server/log_sensors.sh sensors.log
```

`moderate` is the package-standard profile. It uses three loaded decode repeats,
two warm latency repeats, a document-sized prefill test and, by default, a
context-capacity curve at roughly 1K/4K/8K/16K prompt tokens. `conservative`
uses fewer repeats and roughly 0.5K/2K/5K context points for quicker checks or
tighter memory headroom. Environment overrides still take precedence.

Run each model on the Ollama instance that actually owns it: main/production and
embeddings on 11434, task models on 11435, and agentic models on 11436. This keeps
model stores and service settings comparable instead of copying models between
instances just for a benchmark.

The benchmark records the datapoints that matter most when comparing models on
the BC-250:

- **cold model-switch latency**: model load time, TTFC, TTFA and wall time;
- **warm interaction latency**: TTFC/TTFA once the model is resident;
- **decode throughput**: repeated loaded generation tok/s and variance;
- **document prefill**: prompt-evaluation tok/s on a synthetic office-sized
  prompt, separated from long generation;
- **context capacity**: actual `prompt_eval_count`, allocated context from
  `/api/ps`, generation speed at larger prompts and warnings when the evaluated
  prompt stops growing or reaches the context edge;
- **memory/headroom**: `/api/ps` resident size, reported VRAM allocation,
  allocated context, host `MemAvailable` and swap use after each request;
- **sustained stability**: optional decode-throughput drift plus an optional
  external temperature/power trace;
- **embedding indexing cost**: optional cold/warm multilingual office batches via
  `/api/embed`, including vector dimensions and input-token throughput.

Ollama's generation API exposes load, prompt-evaluation, generation and total
durations directly. The embedding API exposes total/load duration and input-token
count but not a separate prompt-evaluation duration, so embedding input tok/s is
computed from `prompt_eval_count / (total_duration - load_duration)` and is
labelled as an indexing-throughput estimate. The CSV keeps that inferred
`embedding_process_duration_s` separate instead of pretending Ollama reported a
prompt-evaluation duration for embeddings.

Use the same Ollama version (**package standard 0.32.15**), model revision,
governor, CU state, profile, prompts and cooling state when comparing results.
The CSV and metadata file make those runs easier to audit. `/api/ps`
`size_vram` is an Ollama-reported allocation and should be treated as indicative
on this unified-memory Vulkan system rather than a calibrated physical-VRAM
measurement. SMU/PPT power is likewise uncalibrated and useful only for
same-board comparisons.

This is a **runtime benchmark**, not an answer-quality score. For office/RAG
quality, use `examples/rag/pilot-evaluation.tsv` and inspect retrieval, citations,
source correctness, language choice and refusal on unanswered questions. OCR
quality should be compared with the same real page corpus through `bc250-ocr`.

For planning, roughly 13 GiB of model weights remains a practical BC-250 ceiling,
not a fixed technical limit: KV/context buffers, the OS and resident services all
share the same ~16 GB memory. See [`../../docs/COMMANDS.md`](../../docs/COMMANDS.md)
for environment controls.
