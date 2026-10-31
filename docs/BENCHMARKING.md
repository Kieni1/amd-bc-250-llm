# Benchmarking and package qualification

The package deliberately separates three operator questions:

- `bc250 verify`: is the appliance healthy now?
- `bc250 advanced benchmark`: which model or setting behaves better?
- `bc250 advanced revalidate`: does the configuration shipped by this package qualify on this BC-250?

Revalidation does not choose settings. Tuning and A/B comparisons are explicit benchmark commands.

## Office/RAG quality campaign foundation

The 0.20.0-1 source candidate adds a staged campaign surface while preserving the accepted predecessor roles and RAG settings as controls. It also adds one explicit Office - Generalist candidate and additional managed challengers for qualification:

```bash
bc250 advanced benchmark campaign audit
bc250 advanced benchmark campaign corpus-inventory --corpus-dir DIR --corpus-id ID
bc250 advanced benchmark campaign corpus-validate --manifest CORPUS.json --corpus-dir DIR
bc250 advanced benchmark campaign tika-extract --manifest CORPUS.json --corpus-dir DIR
bc250 advanced benchmark campaign gold-validate --manifest CORPUS.json --corpus-dir DIR --tika-results TIKA_RESULT_DIR
bc250 advanced benchmark campaign retrieval-score --manifest CORPUS.json --corpus-dir DIR --rankings RANKINGS.jsonl --arm ARM
bc250 advanced benchmark campaign retrieval-compare --result-dir RETRIEVAL_RESULT_DIR --result-dir RETRIEVAL_RESULT_DIR [...]
bc250 advanced benchmark campaign retrieval-freeze --comparison RETRIEVAL_COMPARISON.json --selected-result-dir RETRIEVAL_RESULT_DIR --selection-note TEXT
bc250 advanced benchmark campaign fixed-export --freeze FROZEN-RETRIEVAL.json --corpus-dir DIR
bc250 advanced benchmark campaign fixed-replay --bundle FIXED-EVIDENCE.json MODEL [MODEL ...]
```

`campaign audit` is the Step-3 control audit. It compares the checked-in campaign snapshot against the actual packaged Modelfiles, product-role request policy and Open WebUI retrieval desired state. A mismatch is reported as configuration drift; the audit never rewrites a production setting. The campaign snapshot deliberately records the current qualified controls separately from setting hypotheses such as an alternative Qwen thinking sampler.

The real PDF corpus is **external benchmark input**. `corpus-inventory` is the Step-4 starting point: it recursively inventories external PDFs without copying them, records deterministic safe logical IDs, relative paths, SHA-256, byte size, PDF-header sanity and byte-identical duplicates, and leaves language/source annotation explicitly unresolved for review. Symlinked PDFs are rejected so the inventory cannot silently escape the declared corpus root. The inventory is measurement evidence, not a finished gold manifest.

`corpus-validate` validates path-safe logical document/question IDs, safe relative paths, SHA-256, size, languages and gold-evidence references and writes a corpus lock into the result directory. A corpus manifest may deliberately contain `questions: []` during Steps 4–5 so provenance and Tika extraction can be established before Step 6 creates gold questions. Retrieval scoring and fixed-evidence export still require at least one gold question. Logical IDs are restricted to `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` because they become evidence artifact names. The tooling never copies the source PDFs into the repository/package fixture tree. `tika-extract` streams each external file through the private Open WebUI-container → Tika path, saves raw JSON and extracted text in benchmark evidence, and scores only conservative literal extraction gold when such gold is present. Missing/blank `tk:content` and the pinned Open WebUI placeholder `<No text content found>` are scored as no usable extraction rather than document text. It does not use embeddings or generation.

`gold-validate` is the Step-6 gate between extraction and retrieval. It requires a non-empty gold-question set and binds it to the exact Step-5 Tika evidence: corpus ID/hash/size provenance must match, every required/acceptable/conflicting evidence entry needs a literal anchor that actually exists in the extracted text, and exact identifiers/names/dates/amounts must be present in the annotated supporting documents. It reports the observed language-pair coverage without inventing an automatic 45/45 balance threshold. Human review still decides whether the question set is representative.

`retrieval-score` intentionally consumes a ranked-chunk JSONL export instead of implementing a second package-owned chunker/indexer. This prevents the quality campaign from silently measuring a home-grown retrieval pipeline rather than the actual product path. The JSONL contract is documented by `retrieval-rankings.schema.json`. It reports Recall@1/@3/@5, reciprocal rank, required/alternate support recovery, conflicting chunks, exact-value recovery and separate DE→DE / FR→FR / DE→FR / FR→DE dimensions when present. Unsupported questions are retained for later fixed-evidence/model checks but are reported as `recall=N/A` and excluded from Recall/MRR aggregates because they have no relevant passage by definition. The named arms in `retrieval-arms.json` are bounded hypotheses and every arm requires a fresh index.

`retrieval-compare` accepts two or more completed retrieval-only result directories only when they use the exact same corpus manifest and retrieval-arm authority. It preserves per-arm and per-language-pair metrics but deliberately does **not** choose a winner. After review, `retrieval-freeze` requires an explicit selection note and copies the selected manifest, arm authority and ranking export by SHA-256 into a self-contained frozen retrieval contract. Old result-directory paths are therefore not the authority for later model comparison.

`fixed-export` accepts only that explicit Step-9 frozen retrieval contract. It freezes the exact retrieved chunks and metadata together with the retrieval-freeze and ranking-export SHA-256 values. `fixed-replay` can then feed those identical chunks to multiple answer models, separating retrieval quality from reading/reasoning/grounding quality. The replay prompt treats retrieved evidence as data rather than instructions and forbids filling unsupported facts from model knowledge. Promotion remains role-specific and requires later DEVICE evidence; these campaign commands do not promote models or change Open WebUI configuration.

### Development versus DEVICE execution boundary

The quality-campaign source may be developed in the main workbench while the previously built candidate is still being qualified elsewhere. A command documented in the post-release workbench is **not** assumed to exist on the currently installed candidate. Real-corpus Tika/retrieval/model evidence becomes DEVICE evidence only after an RPM containing the corresponding campaign tooling is built and installed. Keeping the corpus files on the appliance is fine; do not improvise source-only campaign commands against an older installed package and then label the result as qualification evidence.


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
benchmark options. `summary.json` includes category aggregates plus case-level
`quality_failures`, so a mixed result identifies the failing model/case without reopening
every record. `results.jsonl` remains the canonical per-case evidence.

`results.jsonl` uses the common envelope:

```text
result_type   measurement | qualification
outcome       pass | quality-fail | infra-fail | skipped | incomplete
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
bc250 advanced benchmark generation MODEL [MODEL ...]
bc250 advanced benchmark generation --profile compare MODEL...
bc250 advanced benchmark generation --profile edge --mode production MODEL...
bc250 advanced benchmark generation --profile thermal MODEL...
bc250 advanced benchmark generation --deep-context MODEL...
bc250 advanced benchmark generation --profile thermal --sustained-seconds 180 MODEL...
```

Profiles and optional qualification modes:

- `compare`: normal cold/warm, repeated short decode, prefill and context comparison;
- `edge`: bounded long-prefill/context work for memory-edge qualification;
- `thermal`: repeated generation with thermal/drift reporting; add
  `--sustained-seconds SECONDS` when a fixed minimum heat-soak interval is required;
- `--deep-context`: adds explicit approximate 4K and 16K prompt targets. The recorded
  `prompt_eval_count` is authoritative; this mode deliberately does not force 32K.

Generation evidence records the effective local Ollama service command/environment when
available, including the resolved `OLLAMA_KV_CACHE_TYPE`, and captures the current CU
status. Completion integrity requires Ollama's terminal `done=true` record and rejects
pathological runs of reserved/unused tokens. Kernel GPU-journal capture is best-effort by
default and flags ring timeouts, GPU resets/device loss, VM faults and compute-ring errors;
use `--no-gpu-journal` only when the journal is intentionally unavailable.

For main-model qualification, use the highest-precision **feasible** KV configuration as
the correctness reference. `q8_0` is a useful first compressed comparison and `q4_0` is a
more aggressive comparison, but neither is globally promoted by this policy. Do not force
F16 when it makes the target context infeasible.

After load/resource/completion-integrity smoke, use the existing compact
`bc250 advanced benchmark usecase MODEL` as the tiny semantic sanity gate before expensive
deep-context or sustained testing.

The normal comparison summary emphasizes decode mean/CV, cold load, warm answer
latency where available, prefill, resident size, minimum `MemAvailable`, swap
start/peak/end/delta, maximum per-case temperature p95 plus run maximum, and
context/output diagnostics. GPU-journal evidence remains a canonical runtime record,
but aggregate summaries expose it as runtime diagnostics rather than a pseudo-model
with empty performance metrics. VRAM/GTT counters remain raw Vulkan diagnostics and
are not additive memory pools on BC-250 UMA.

`--mode neutral` supplies the neutral benchmark system prompt. For `--mode production`, generation
loads any package-owned request policy from the existing Open WebUI model authority and applies supported
sampler options plus request-level `think`; this keeps Qwen qualification aligned with the actual product
without writing `think` into Modelfiles. Models without a package request policy continue to use their
registered Modelfile sampling. `--mode production`
preserves the packaged model policy. `--think` can explicitly select a supported
thinking policy for a comparison.

For thinking-capable generation, visible-answer identity and hidden thinking are separate evidence.
Every generation measurement records `visible_response_identity` with a state, a
`determinism_eligible` flag and a SHA-256 only when a non-empty visible `response` exists. A
thinking-only completion therefore has `sha256: null` and cannot be presented as deterministic
visible-output evidence. If a run completes without any visible answer, the measurement is recorded
as `INCOMPLETE`; output/thinking budget diagnostics remain explicit and no throughput or quality
threshold is weakened.

## Embeddings

```bash
bc250 advanced benchmark embeddings [MODEL ...]
```

Reports Recall@1, Recall@3, MRR, cross-language metrics, hard-case Recall@1 and
within-model target-vs-best-competitor margins. Experimental embedding models are
measurement-only. The promoted Jina fixture contains the explicit aggregate
qualification policy; individual query rows are observations.

## OCR

```bash
bc250 advanced benchmark ocr [MODEL ...]
```

Package-owned model kind is selected from `models/model-catalog.json` capability metadata first;
name heuristics are retained only for unknown external models. The canonical evaluator currently
supports the package OCR profiles for GLM-OCR, OvisOCR2 and MiniCPM-V, with MiniCPM using a
direct extraction prompt suited to its document-vision/OCR role.

Text fidelity is scored on canonicalized plain text so requested Markdown/HTML
markup does not distort transcription quality. Semantic literal matching likewise normalizes paired
Markdown emphasis plus Unicode space/hyphen presentation before deciding that required content is
missing. Structure reconstruction is measured
separately. OCR remains a benchmark role until a production OCR model is promoted.

## Task

```bash
bc250 advanced benchmark task [MODEL ...]
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
sudo bc250 advanced agent enter
bc250 advanced benchmark agent MODEL --ollama-url http://127.0.0.1:11436
sudo bc250 advanced agent leave
```

The agent benchmark is a safe static contract check. Package profiles expose this
qualification boundary as `agent_validation=static-output-contract`. It records raw-format, syntax
and required-structure evidence; literal thinking markers in final output are a format
failure. NUL-safe `xargs -0 -r ... basename` is accepted for the basename contract,
while omitting `-r` remains an empty-input robustness miss. The benchmark does not
execute generated Bash/Python as root, does not exercise/qualify native Ollama `tool_calls`,
and does not claim arbitrary behavioral correctness. Intrinsic `tools=true` capability
therefore remains distinct from the validation contract actually proven on BC-250. The final
2026-10-31 DEVICE closure passed the canonical Bash/Python/JSON mini-regression 3/3 after
changing only the Bash case to the contract-first raw-output wording.

Long-running qualification scripts should emit explicit operator progress (step/case/repeat start and completion/result) so a healthy long run is distinguishable from a stalled harness.

Generation canonical summaries expose more than headline decode throughput: cold request wall time and
actual `cold_load_s` are separate, optional 4K/16K deep-context lanes report target versus actual prompt
tokens plus prefill rate, thermal runs report window count/mean/min/max/first/last/drift, and each selected
lane emits a completeness qualification. Missing selected lanes are infrastructure evidence rather than a
silently incomplete benchmark summary. These are observability improvements; no synthetic board score or
machine ranking is produced.

## Production use-case acceptance

```bash
bc250 advanced benchmark usecase [MODEL ...]
```

Runs a compact deterministic role-level acceptance set. This is quality evidence,
not a general model ranking score.

## Translation

```bash
bc250 advanced benchmark translation [--think auto|true|false] [MODEL ...]
```

Records target-language adherence, semantic anchors, preserved identifiers/numbers,
source-language leakage, meaningful-content checks, answer/thinking sizes, prompt/eval
counts and timings, load/wall time and device telemetry. Modality-labelled cases also call
the package-owned clause-local translation authority used by the Open WebUI delivery
guard; benchmark code does not maintain an independent adjacency/substring modality
parser. When that authority finds a change, the exact semantic detail is retained in CSV
and JSONL diagnostics (for example `negated recommendation / temporal polarity was
lost` or `prohibition weakened to no-obligation`). `--think auto` preserves the runtime
default; `--think true` and `--think false` make a direct-transform reasoning contract
explicit and record it in result provenance. Explicit-vs-implicit direction belongs here
as a comparison; routine revalidation tests only the packaged production translation
preset.


For packaged generation models, `reasoning_request_policy=nonthinking-first-pass` is an explicit
qualification request policy: `--think auto` resolves that first pass to `think=false`. Device evidence
shows that a provider/model template can still serialize a literal `<think>...</think>` block into the raw
response despite that request. The generation benchmark therefore preserves the raw provider response and
records `reasoning-present-despite-think-false` rather than silently stripping it. Product presentation is a
separate role/UI contract and must not be inferred from benchmark cleanup.

Model-comparison reports should present quality and latency together. The 2026-10-31
Qwen3.5 Advanced DEVICE block is the reference example: `think=true` passed 15/15 at
about 32.65 s median, while `think=false` passed 12/15 at about 9.83 s median and
deterministically violated one scheduling constraint 3/3. A faster arm with a repeatable
quality regression is not a promotion win. The subsequent minimal `presence_penalty=1.5`
intervention retained `think=true` and reproduced 14/14 PASS twice; the 0.20.0-1 source
candidate adopts that one sampler change rather than reopening broad sampler fishing.
Reasoning-budget exhaustion with no visible answer remains `INCOMPLETE` unless the strict
repetition oracle fires, but the evidence now also records diagnostic-only tail repetition
indicators so operators can see an exhausted check-loop even when it does not cross the
quality-fail threshold.

## Direct RAG

```bash
bc250 advanced benchmark rag-cycle EMBED_MODEL ANSWER_MODEL
bc250 advanced benchmark rag-quality [EMBED_MODEL ANSWER_MODEL]
bc250 advanced benchmark rag-quality --think true [EMBED_MODEL ANSWER_MODEL]
bc250 advanced benchmark rag-quality --think false [EMBED_MODEL ANSWER_MODEL]
```

`rag-cycle` checks that the answer model remains available while the dedicated
embedding lane does work. `rag-quality` records target retrieval, all-required-source
retrieval, fact/abstention acceptance, deterministic language evidence, citation behavior,
thinking/output sizes and multi-cause failure information. Language evidence exposes both
`language_ok` and `language_measurable`; short numeric/identifier answers can therefore pass
without being misreported as a positive language match. Acceptance matching is boundary-aware
for dates/numbers/IDs/currency and fixtures may declare explicit `required_any_groups` and
case-scoped `numeric_values`; grading remains deterministic. Grouped bracket citations are parsed
by member source ID, so a required source may appear alongside another source without becoming a
false negative. The known office invoice forms `INV-YYYY-NNNN` and `Invoice YYYY-NNNN` are treated
as the same unambiguous identifier. Clean hidden-reasoning budget exhaustion with no visible answer
is `INCOMPLETE`/retry when no independent retrieval or semantic defect exists; repetition remains a
quality failure. Use `numeric_values` when the number itself is sufficient, and combine it with
`required`/`required_any_groups` when a unit or qualifier is mandatory instead of adding a second
unit-policy schema.
Canonical summaries also verify that every expected RAG case appears exactly once, so a
partial result stream cannot be mistaken for a complete quality run. `rag-quality` snapshots the
starting main/embedding Ollama residency set, restores and verifies that set on every exit path,
and treats restoration failure as infrastructure failure. Reloads omit an explicit keep-alive so
each Ollama service applies its normal configured/default lane policy; embedding-only registrations
use a harmless non-empty `/api/embed` probe when `/api/generate` is unsupported. Exact remaining
expiry time is not reconstructed. Its canonical resource summary reports resident-session MemAvailable
start/min/end/delta plus swap start/peak/end and `swap_peak_delta_mib`,
while keeping the existing qualification thresholds unchanged. The canonical
thinking-policy A/B is `rag-quality --think true` versus
`rag-quality --think false`; routine revalidation never performs that comparison and
qualifies only the policy shipped by the package.

## Coexistence and tuning workflows

These commands are explicit experiments. They are not part of routine package
revalidation unless a promoted setting is later exercised there.

```bash
bc250 advanced benchmark concurrency MAIN_MODEL EMBED_MODEL
bc250 advanced benchmark num-batch MODEL [MODEL ...]

bc250 advanced benchmark owui-translation --token-file FILE
bc250 advanced benchmark owui-rag MODEL --token-file FILE
bc250 advanced benchmark owui-embedding-batch --token-file FILE
bc250 advanced benchmark owui-chunk-min MODEL --token-file FILE
sudo bc250 advanced benchmark owui-system-context MODEL --token-file FILE
```

Open WebUI benchmark `--token-file` inputs must be non-empty regular files with no
group/world access (normally mode `0600`), matching the package credential-file boundary.

The pinned Open WebUI v0.12.5 OpenAI-style adapter is not an external BC-250 compatibility
contract. A client-supplied root `max_tokens` field on that external-style endpoint is not advertised
as a reliable hard cap for Ollama-backed requests. The package-owned Advanced model record is a
different package-owned internal path: exact-device evidence from the 1.4 campaign records `params.max_tokens=6144` reaching Ollama as `options.num_predict=6144`, with no root-level Ollama `max_tokens`. Later releases use that path as a bounded no-regression check when the Open WebUI/Ollama request boundary changes. The raw outbound capture is not retained in this source tree. Direct benchmark callers
that require a hard generation cap likewise use native nested `options.num_predict`. See
`docs/OPENWEBUI.md` for the related reasoning-token and finish-reason metadata limitations.

`concurrency` records both request outcomes, latency, minimum `MemAvailable`, swap
start/peak/end/delta and device-facing telemetry.

The three mutating Open WebUI tuning commands save the package-owned setting they
observe, change only the named benchmark setting, use temporary knowledge/file state,
and restore the original setting before returning. Restoration failure is an
infrastructure failure.

`owui-translation` and `owui-rag` do not tune configuration. `owui-translation`
qualifies the packaged DE↔FR regression corpus through the actual package-owned
production role IDs, so the live model-specific direction Filter and 2048-token preset are
part of the path. The corpus includes the historically known recommendation-strengthening
case plus negated-recommendation/temporal-polarity, prohibition/no-obligation,
no-obligation and permission/prohibition controls. A raw semantic failure may therefore
remain a model-quality failure while the finalized product path passes by withholding it. `owui-rag` qualifies the currently configured Open WebUI RAG path with
deterministic multi-turn grounding/citation checks. Its MODEL argument may be an exact active
Open WebUI preset ID or an Ollama base model that maps to exactly one active preset. The
benchmark resolves that relationship through authenticated Open WebUI metadata before creating
temporary knowledge/upload state; ambiguous or unknown model selections fail early and list the
valid matching preset IDs. Only the sanitized active `preset_id -> base_model` mapping is retained
in benchmark metadata. Open WebUI must answer HTTP readiness before the product-path benchmark
starts; the readiness allowance is bounded to five minutes for slow application restarts.

## Revalidation harness v4.9

```bash
sudo bc250 advanced revalidate start
sudo bc250 advanced revalidate start --output-dir /path/to/existing/export-dir
# Explicit partial coverage only:
sudo bc250 advanced revalidate start --skip-owui
sudo bc250 advanced revalidate status
sudo bc250 advanced revalidate status --raw  # machine-readable key=value state
```

Agent is an optional add-on. If the recommended Ornith Agent source/registration is absent, its
qualification is reported as `coverage unavailable/skipped` and overall coverage becomes PARTIAL; this is
not a GPU/runtime infrastructure failure and does not invalidate the core appliance. A run that executes all
required phases still reports `Run completion: completed`; completion and optional coverage are independent.
Install the Agent explicitly with `sudo bc250 model apply agentic agentic-ornith15-9b-ornith-q5-k-m` when
Agent coverage is desired.

The Open WebUI translation phase finalizes direct API completions through `/api/chat/completed`
before scoring so the package-owned translation `outlet()` integrity filter is part of the qualified product
path. Evidence keeps the raw-model translation result separate from the delivered product result: when a raw
translation violates the modality/literal guard and the outlet withholds it, the product integrity control is
PASS while the underlying raw-model quality failure remains recorded. Over-blocking a valid translation remains
a product quality failure.

The systemd-owned worker uses six phases:

1. preflight;
2. production roles;
3. resource edge;
4. exclusive agent mode;
5. packaged Open WebUI translation + RAG;
6. restore/report.

The complete live SPI/WGP routing table is the CU authority. A particular machine may
report 40/40 routed, but revalidation does not hard-code that number as the generic
success rule.

Case-quality `rc=3` is recorded and does not abort the worker. Other benchmark/helper
errors are infrastructure failures. Final status reports run completion, infrastructure, model quality, product integrity and topology restoration separately. Human summaries additionally separate `Quality suites` from `Qualification cases`: suite outcomes describe the higher-level qualification paths, while case counts report the underlying pass/quality-fail/incomplete/skipped records. `Coverage: FULL — all scheduled qualification paths executed` describes execution scope only and never implies that every quality case passed. Worker liveness and the age of the last real
progress event are also separate; a free-running pulse is never presented as proof
of benchmark progress.

Harness v4.9 keeps the dedicated GPT-OSS/Jina coexistence test as the authoritative
deep GPT-OSS resource check and omits GPT-OSS from the redundant generic edge sweep.
Successful roles/edge/Open-WebUI phase boundaries use lightweight checkpoints; full
snapshots remain at preflight, agent-topology transitions, final restoration and failures.
Non-severe context truncation is surfaced under `Diagnostics` with explicit requested→evaluated token counts and the wording that it is accepted by current context policy, without changing PASS criteria; severe early truncation remains an infrastructure qualification failure. The
same section also reports tight resource headroom when MemAvailable falls below 512 MiB
while remaining above the unchanged 128 MiB hard floor, and accepted use cases that reach
their output budget. These are visibility signals, not relaxed acceptance criteria.
