# Benchmark

The package standard is **Ollama 0.33.2**. Keep the Ollama version, model
revision, CU/governor state and cooling setup fixed when comparing runs.

## Whole-appliance revalidation

`bc250-revalidate` is the opt-in root-only appliance revalidation harness. It is
separate from `make validate` and the ordinary category benchmarks because it can
exercise live services and, when explicitly requested, reboot the machine.

```bash
sudo bc250-revalidate start
sudo bc250-revalidate status
sudo bc250-revalidate abort

# Authenticated Open WebUI tuning lanes
sudo bc250-revalidate start --owui-token-file /root/owui-test.key

# Optional hardware-policy A/B lanes
sudo bc250-revalidate start --kernel-ab
sudo bc250-revalidate start --governor-ab
```

Routine runs do not perform kernel/governor reboot A/B tests. The harness records
quality exit `3` separately from infrastructure failure, propagates unexpected
benchmark errors into worker recovery, exercises the promoted
task/embedding defaults, compares implicit/explicit translation direction, and
keeps GPT-OSS/long-prefill diagnostics isolated from ordinary build validation. If
a long-prefill candidate takes down the main Ollama API, the next candidate first
restarts/waits for the main service rather than turning one OOM into a row of
connection-refused results. The phase also restores normal Ollama mode after the
sweep so a final candidate failure cannot poison a later phase.

Persistent result bundles are written below
`/var/lib/bc250-llm-server/revalidation/results/`. Temporary worker state lives
under `/var/lib/bc250-llm-server/revalidation/work/` and
`/run/bc250-llm-server/revalidation/`; after a final tarball is written safely,
the harness disables/removes its temporary systemd worker and deletes that work
state automatically. Phase reports are included in the tarball. Supplied Open
WebUI credentials are not bundled. `cleanup` remains only for abandoned pre-bundle
runs.

This harness is deliberately a pre-1.0 diagnostic tool. Do not make it a mandatory
RPM/build gate.

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
`medium`, the intended production Qwen3.5/Qwen3-4B profiles use request-level `false`, and
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
2026-08-31 Ollama 0.33.2/model comparison produced the same native reasoning
with `think` omitted and with `think=false`; the boolean therefore is not treated
as a suppression control for this LFM profile. `NUM_PREDICT_LATENCY` keeps its
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
near-limit notes are persisted in the JSONL sidecar as well as printed. Set
`RUN_WARM_PREFIX=1` for a separate cold-prefix/warm-prefix pair that keeps a
byte-identical document prefix and changes only the suffix; this measures practical
0.33.x prefix-cache reuse without contaminating the normal cold-runner curve.


## Production role acceptance

```bash
bc250-benchmark usecase
```

This is a deliberately small acceptance suite, not another ranking framework. It
runs one role-defining case for each production model: office drafting (E2B),
evidence-grounded synthesis (E4B), implicit DE→FR translation (LFM2.5), a compact
technical office task (Qwen3.5 with `think=false`), and constrained reasoning
(GPT-OSS). It preserves each registered Modelfile SYSTEM/sampling and only bounds
output length. A failed required/forbidden-content check exits non-zero.

## German/French translation acceptance

```bash
bc250-benchmark translation
# optional comparison model:
bc250-benchmark translation MODEL
```

This lane exercises the registered production translation behavior without a
neutral SYSTEM override. The packaged cases cover DE->FR and FR->DE office text,
formal address, negation, dates, amounts, invoice/reference numbers and terms that
must remain unchanged. It deliberately avoids BLEU/COMET dependencies: pass/fail
is based on deterministic required/forbidden/preserved content, while a small
language hint remains diagnostic rather than pretending to be a full linguistic
quality metric. Human review is still required before changing the production
translation model.

## Main-instance RAG model-switch cycle

```bash
bc250-benchmark rag
# Optional explicit pair:
bc250-benchmark rag EMBED_MODEL ANSWER_MODEL
```

The packaged default sequences Jina → Gemma E4B on the main Ollama instance. It
first records a warm answer-model request, then embeds a query and records whether
the answer model was evicted, then measures the answer-model reload and final
answer. This isolates the `OLLAMA_MAX_LOADED_MODELS=1` model-switch cost; it does
**not** score Open WebUI/vector-database retrieval quality. Override the pair with
`RAG_EMBED_MODEL` / `RAG_ANSWER_MODEL` or positional model names.

## End-to-end RAG quality acceptance

```bash
bc250-benchmark rag-quality
# optional pair:
bc250-benchmark rag-quality EMBED_MODEL ANSWER_MODEL
```

This lane uses the packaged multilingual office corpus, embeds the real query,
ranks the documents, passes the retrieved Top-K context to the answer model and
checks the grounded answer. It specifically includes the difficult current-vs-
archived Zürich lease and near-identical invoice references that exposed the two
shared Recall@1 misses in the 2026-08-31 embedding comparison. The default pair is
Jina v5 plus production Gemma E4B. It is intentionally small and stdlib-only.

This is still not a clone of Open WebUI's database/vector implementation; use it
as a package/model acceptance layer, then validate Open WebUI-specific settings
(`RAG_SYSTEM_CONTEXT`, chunk merging, batching) through the actual UI/API before
changing fresh-install defaults.

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
field recall, key-field reading order, local row/field association, a table-markup
signal and runtime. Two deterministic harder variants add a slight rotation and
a low-contrast/blurred scan without turning the suite into a large OCR corpus. The packaged comparison set
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
relevant Open WebUI **0.11.3** task behavior in compact fixtures: title uses the
latest two messages, tags the latest six (with the short-chat `General` fallback),
and retrieval-query generation the latest six plus the current date. It parses
the JSON object the same tolerant way Open WebUI 0.11.3 does (including fenced or
surrounded JSON), while separately reporting `strict_json`. It checks structure,
simple content relevance, latency and DE/FR/EN `language_hint` plus explicit
`language_required`/`language_pass` reporting. Titles and retrieval queries require
the requested language for the report; tags remain informational. Language does
not change the process exit code yet, so one weak multilingual task model cannot
turn a routine benchmark into a package-build failure. Requests use
`keep_alive=0`, matching the isolated task service. The Open WebUI container
leaves 0.11.3 `TASK_MODEL_PARAMS` at `{}` until this benchmark demonstrates a
reason to tune it. Its CSV deliberately keeps only the small telemetry subset
useful for this short background workload.

## Agent/coding

```bash
bc250-benchmark agent
bc250-benchmark agent agentic-qwen25-coder7b-unsloth-q5-k-m
```

This lane defaults to `http://127.0.0.1:11436`. Stop/avoid a large main-model
workload while using it. The small fixture set checks Bash/Python syntax plus deliberately narrow static
semantic requirements and JSON shape without executing model-generated code. A
response passes only when a non-empty final answer has valid syntax/structure,
uses the requested raw-output format, and satisfies the fixture's required
patterns (including space-safe Bash handling and explicit Python range rejection). Native model reasoning is not globally
forced off. The cases provide 768-1024 shared output tokens so reasoning-oriented
models have room to reach final code, and JSONL records thinking/final character
counts, `eval_count` and `done_reason` for starvation diagnosis. The lane also leaves
temperature/top-p/top-k to the deployed Modelfile by default; set
`AGENT_TEMPERATURE=0` only for an explicit deterministic comparison. It does not
override the agent service keep-alive and unloads each benchmarked model after
the run.

## Sustained thermal qualification

The built-in `RUN_THERMAL=1` wave is intentionally short and is best treated as
a regression signal. For a real board/cooling qualification, repeat the same
representative generation workload for at least 20-30 minutes and compare the
first and final decode rate, edge-temperature p95/max, active clock, swap and
AMDGPU/Vulkan error logs. One simple operator recipe is:

```bash
end=$((SECONDS + 1800))
while (( SECONDS < end )); do
  RUN_LATENCY=0 RUN_CONTEXT=0 RUN_THERMAL=1 \
    THROTTLE_WINDOWS=3 NUM_PREDICT_LONG=6000 \
    bc250-benchmark generation MODEL || break
done
```

This deliberately stays manual: cooling, room temperature and model stopping
behavior differ between boards, so the package does not turn a long thermal soak
into an install/build gate. Preserve the generated result files and the board
conditions when comparing runs.

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
