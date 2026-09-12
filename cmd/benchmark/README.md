# BC-250 benchmark and package qualification

The package deliberately separates three operator questions:

- `bc250-verify`: is the appliance healthy now?
- `bc250-benchmark`: which model or setting behaves better?
- `bc250-revalidate`: does the configuration shipped by this package qualify on this BC-250?

Revalidation does not choose settings. Tuning and A/B comparisons are explicit benchmark commands.

## Canonical benchmark results

Every benchmark invocation owns one isolated result directory. The default is under
`./bc250-results/`; use `--output-dir DIR` when a predictable path is useful. An
existing non-empty directory is rejected rather than merged with a new run.

Each run contains:

```text
meta.json       run/category metadata
results.jsonl   canonical per-case evidence
summary.json    canonical aggregate
summary.txt     compact human summary
fixtures/       deterministic inputs copied once
results.csv     optional category export where useful
```

`meta.json` uses one shared envelope for package identity, kernel, benchmark version,
runtime endpoints/versions, model names/digests, fixture SHA-256 values and effective
benchmark options. `summary.json` includes a small category-specific aggregate section
so the canonical summary is useful without reopening every case record.

`results.jsonl` uses the common envelope:

```text
result_type   measurement | qualification
outcome       pass | quality-fail | infra-fail | skipped
failure_kinds actual qualification failures
diagnostics   useful warnings that are not automatically failures
checks        case-specific booleans/scores
metrics       timing/resource/quality measurements
```

Examples of diagnostics are thinking/output budget exhaustion, context truncation,
swap pressure and thermal observations. They become failure causes only when a
qualification contract actually makes them fail the case. `summary.json` derives
Quality only from `result_type=qualification`; pure measurements therefore report
Quality `NOT-RUN` even when the measurements themselves completed successfully.

## Generation

```bash
bc250-benchmark generation MODEL [MODEL ...]
bc250-benchmark generation --profile compare MODEL...
bc250-benchmark generation --profile edge --mode production MODEL...
bc250-benchmark generation --profile thermal MODEL...
```

Profiles:

- `compare`: normal cold/warm, repeated short decode, prefill and context comparison;
- `edge`: bounded long-prefill/context work for memory-edge qualification;
- `thermal`: repeated sustained generation with thermal/drift reporting.

The normal comparison summary emphasizes decode mean/CV, cold load, warm answer
latency where available, prefill, resident size, minimum `MemAvailable`, swap
start/peak/end/delta, maximum per-case temperature p95 plus run maximum, and
context/output diagnostics. VRAM/GTT
counters remain raw Vulkan diagnostics and are not additive memory pools on BC-250 UMA.

`--mode neutral` supplies the neutral benchmark system prompt. `--mode production`
preserves the packaged model policy. `--think` can explicitly select a supported
thinking policy for a comparison.

## Embeddings

```bash
bc250-benchmark embeddings [MODEL ...]
```

Reports Recall@1, Recall@3, MRR, cross-language metrics, hard-case Recall@1 and
within-model target-vs-best-competitor margins. Experimental embedding models are
measurement-only. The promoted Jina fixture contains the explicit aggregate
qualification policy; individual query rows are observations.

## OCR

```bash
bc250-benchmark ocr [MODEL ...]
```

Text fidelity is scored on canonicalized plain text so requested Markdown/HTML
markup does not distort transcription quality. Structure reconstruction is measured
separately. OCR remains a benchmark role until a production OCR model is promoted.

## Task

```bash
bc250-benchmark task [MODEL ...]
```

Exercises title, tag and retrieval-query shapes using the exact package-owned prompt
templates from `openwebui/desired-state.json`. Acceptance evaluates the parsed
content: structure, requested language and semantic groups. Empty output and budget
behavior are recorded separately. This direct Ollama path is a fast qualification
gate, not a substitute for a real authenticated Open WebUI endpoint check when
promoting or requalifying a task model; the 2026-09-12 LFM work demonstrated that
upstream/default Open WebUI prompts could turn a 15/18 direct result into 6/18 live.

## Agent

Agent mode is exclusive. Enter it before benchmarking the packaged agent lane:

```bash
sudo bc250-agent-mode enter
bc250-benchmark agent MODEL --ollama-url http://127.0.0.1:11436
sudo bc250-agent-mode leave
```

The agent benchmark is a safe static contract check. It records raw-format, syntax
and required-structure evidence; it does not execute generated Bash/Python as root
and does not claim arbitrary behavioral correctness.

## Production use-case acceptance

```bash
bc250-benchmark usecase [MODEL ...]
```

Runs a compact deterministic role-level acceptance set. This is quality evidence,
not a general model ranking score.

## Translation

```bash
bc250-benchmark translation [MODEL ...]
```

Records target-language adherence, semantic anchors, preserved identifiers/numbers,
source-language leakage and meaningful-content checks. Explicit-vs-implicit direction
belongs here as a comparison; routine revalidation tests only the packaged production
translation preset.

## Direct RAG

```bash
bc250-benchmark rag-cycle EMBED_MODEL ANSWER_MODEL
bc250-benchmark rag-quality [EMBED_MODEL ANSWER_MODEL]
bc250-benchmark rag-quality --think true [EMBED_MODEL ANSWER_MODEL]
bc250-benchmark rag-quality --think false [EMBED_MODEL ANSWER_MODEL]
```

`rag-cycle` checks that the answer model remains available while the dedicated
embedding lane does work. `rag-quality` records retrieval rank, answer correctness,
citation/source behavior, thinking/output sizes and multi-cause failure information.
The canonical thinking-policy A/B is `rag-quality --think true` versus
`rag-quality --think false`; routine revalidation never performs that comparison and
qualifies only the policy shipped by the package.

## Coexistence and tuning workflows

These commands are explicit experiments. They are not part of routine package
revalidation unless a promoted setting is later exercised there.

```bash
bc250-benchmark concurrency MAIN_MODEL EMBED_MODEL
bc250-benchmark num-batch MODEL [MODEL ...]

bc250-benchmark owui-rag MODEL --token-file FILE
bc250-benchmark owui-embedding-batch --token-file FILE
bc250-benchmark owui-chunk-min MODEL --token-file FILE
sudo bc250-benchmark owui-system-context MODEL --token-file FILE
```

`concurrency` records both request outcomes, latency, minimum `MemAvailable`, swap
start/peak/end/delta and device-facing telemetry.

The three mutating Open WebUI tuning commands save the package-owned setting they
observe, change only the named benchmark setting, use temporary knowledge/file state,
and restore the original setting before returning. Restoration failure is an
infrastructure failure.

`owui-rag` does not tune configuration; it qualifies the currently configured
Open WebUI RAG path with deterministic multi-turn grounding/citation checks.

## Revalidation harness v4

```bash
sudo bc250-revalidate start --owui-token-file /root/owui-test.key
# Explicit partial coverage only:
sudo bc250-revalidate start --skip-owui
sudo bc250-revalidate status
sudo bc250-revalidate status --raw
```

The systemd-owned worker uses six phases:

1. preflight;
2. production roles;
3. resource edge;
4. exclusive agent mode;
5. packaged Open WebUI RAG;
6. restore/report.

The complete live SPI/WGP routing table is the CU authority. A particular machine may
report 40/40 routed, but revalidation does not hard-code that number as the generic
success rule.

Case-quality `rc=3` is recorded and does not abort the worker. Other benchmark/helper
errors are infrastructure failures. Final status reports run state, infrastructure,
quality and restoration separately. Worker liveness and the age of the last real
progress event are also separate; a free-running pulse is never presented as proof
of benchmark progress.
