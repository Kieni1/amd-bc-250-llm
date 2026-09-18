# BC-250 testing strategy

This is the development plan for continuing BC-250 qualification without repeatedly
running one giant hardware campaign. The package already separates health,
measurement, and qualification; the testing process should preserve that separation.

## 1. Three different questions

Use the right tool for the question:

| Question | Primary tool |
|---|---|
| Is the appliance healthy right now? | `bc250-verify` |
| Which model/setting behaves better? | `bc250-benchmark ...` |
| Does the package configuration qualify as a whole? | `bc250-revalidate` |

Do not use a benchmark win as proof of appliance health. Do not use a healthy verifier
as proof of model quality. Do not run whole-appliance revalidation merely to compare
one candidate.

## 2. Test ownership

- **Source/chat environment:** unit/static checks that are actually available.
- **GitHub:** RPM/package build.
- **Workstation:** Ruff and developer linting as configured by the user.
- **BC-250:** real services, GPU/resource behavior, model quality, WOL/power, Open WebUI,
  llama.cpp/MTP and integration qualification.

Never substitute an unavailable local check with an imitation and report it as real.

The deterministic source/unit gate must remain host-independent. Runtime shell integrations
that depend on packaged tools such as `jq` belong to installed-package/BC-250 qualification;
source tests should exercise the underlying data/format contracts without invoking those runtime
dependencies.

## 3. Common promotion funnel

For a candidate change, stop as soon as it no longer has a promotion case.

1. **Source/static gate** — package parses/tests; model definition is sane.
2. **Cheap/direct screen** — deterministic fixture on the narrow role contract.
3. **Real integration path** — Open WebUI or package workflow where the product uses it.
4. **Resource/coexistence gate** — memory, swap, latency, topology and thermal evidence.
5. **Repeatability** — repeat only finalists or production defaults, not every loser.
6. **Decision record** — observed facts, interpretation, decision, retest conditions.

A larger model does not advance merely because it is interesting. A quality winner does
not promote if it makes the real appliance unsafe or unresponsive.

## 4. Evidence envelope for every BC-250 batch

Record:

```text
source release / source SHA when available
installed RPM NEVRA
runtime versions
exact model IDs and relevant digests
exact command(s)
effective settings / benchmark profile
result directory or evidence archive + SHA-256
verifier/topology before and after when stateful
observed facts
interpretation
decision / next gate
restoration result
```

Do not include GGUF contents, API keys, HF tokens, passwords or private backup data.

## 5. Cadence: one bounded hardware batch at a time

The next batch should depend on the previous result. In particular, do not provide a
five-stage destructive machine plan up front. Use read-only baseline evidence before
state changes. Restore state before moving to another lane.

## 6. Recommended current work order

### Lane A — general operations / office availability / power

This is currently the highest product priority because the Pi/maintenance contract was
added after much of the older hardware evidence.

First batch is read-only plus one bounded qualification run:

```text
installed NEVRA and runtime versions
bc250-verify --owui-token-file FILE
bc250-openwebui-setup status --verbose --owui-token-file FILE
bc250-revalidate start --owui-token-file FILE
normal service topology
HTTP :80 readiness
maintenance contract/status
companion status
WOL NIC state
firewall/listener state
```

The current harness v4.2 includes the actual package-owned production translation roles
and should replace the ad-hoc translation smoke used after 0.11.2-0.3.

To preserve evidence value while avoiding redundant runtime, v4.2 keeps direct and
product-path semantic checks distinct, but removes the duplicate generic GPT-OSS edge
performance pass because the dedicated GPT-OSS/Jina coexistence stage is the stronger
resource check. Successful intermediate phases use lightweight checkpoints; full
snapshots remain at preflight, agent transitions, final restoration and failures.

If clean, next batch is a real powered-off/S5 WOL test. Only after S5 wake succeeds
should safe shutdown be exercised: first a deliberately busy/defer case, then an idle
allow case. Backup export is separate and lower priority.

### Lane B — benchmark operations

Before trusting a large new benchmark campaign, establish that the measurement layer
still behaves correctly on the current installed package.

Use a **small production control set**, not every model:

- one normal generation run on a known production model;
- one role-quality benchmark such as `usecase` or `task`;
- one stateful benchmark only if its subsystem is about to be tested;
- verify canonical `meta.json`, `results.jsonl`, `summary.json`, `summary.txt`;
- verify result isolation and refusal to merge into a non-empty output directory;
- for mutating OWUI benchmarks, verify exact restoration and no secret leakage.

Once the benchmark substrate is trusted, specialist lanes can reuse it without
revalidating every formatter on every run.

### Lane C — task and translation role decisions

The current task search is **not** an open invitation to keep trying larger models.
`task-lfm25-1.2b-instruct-liquidai-q6-k` remains the production default. Installed
0.11.3-0.2 again produced the same `tags-de` double-JSON format miss, so 0.11.3-0.3
tightens only the tag prompt: broad/specific tags share one array and exactly one raw JSON
object is allowed. First retest the existing six canonical task cases; do not change the
strict evaluator or 128-token budget to make that result green. Qwen3 4B remains a
role-specific rejection despite 5/6 quality because both exact-source and bounded-4K task
staging caused global OOM and warm-main loss. Future materially larger task challengers
must pass one cheap quality screen, then the tiny warm-main survival gate, before
product-path or repeated quality work.

For translation, broad model/configuration qualification is now closed. Stage-2E selected
Translate-Gemma E4B with the exact explicit-direction v1 contract, thinking omitted and
`max_tokens=2048`. By maintainer decision, Translate-Gemma is now the package production
translation base behind the two package-owned direction roles. The current release still
needs one bounded post-install product-path verification before it is called fully
hardware-qualified. LFM is retained only as an experimental rollback/reference; TIR is
closed as the normal deployment choice under current evidence.

Next translation sequence:

1. install the production translation model with
   `sudo bc250-model apply production prod-translate-gemma4-sub-e4b-17s-q4-k-xl`,
   then apply the source-owned `bc250-office-translation-de-fr` and
   `bc250-office-translation-fr-de` desired state;
2. verify the exact system prompt, non-global direction Filter, `max_tokens=2048`, and
   no forced `think` through authenticated Open WebUI desired state;
3. run one or two repetitions of the bounded final set only: canonical sanity plus the
   Stage-2 targeted protected-finance, bullets/table, `Avoir`, and both long-document
   cases;
4. verify preset/provider/function restoration or desired-state integrity, privacy,
   memory and serious GPU/OOM warnings;
5. if the integrated production path is unacceptable, classify the remaining defect
   before deciding whether rollback or product-layer handling is required; do not silently
   reopen broad model discovery.

Do not restart the broad translation candidate campaign or resume preservation prompt
micro-tuning. Exact byte-for-byte protected financial typography is not claimed by the
current integration; preserve the known caveat rather than weakening the evaluator.

### Lane D — RAG / office documents

RAG is a core office use case and should be tested in layers:

1. **retrieval correctness** with the embedding lane;
2. **direct answer quality** via `rag-quality`;
3. **real Open WebUI path** via `owui-rag` using packaged settings;
4. only then A/B one tuning axis at a time (`embedding-batch`, `chunk-min`,
   `system-context`, thinking policy, hybrid search when explicitly tested);
5. exact restoration after every mutation.

Expand the fixture around the failure modes that matter for office use:

- answer absent / required abstention;
- multiple required sources;
- conflicting documents;
- invoices/tables and OCR-derived text;
- German/French/multilingual documents;
- preservation of names, numbers and dates;
- citation/source correctness;
- privacy-restricted or insufficient-evidence questions.

Do not change retrieval and answer model/settings in the same experiment unless the
question explicitly requires an interaction study.

### Lane E — general assistant / main lane

Start with the production role map, not experimental candidates:

- `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` — standard office;
- `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` — RAG answer;
- `prod-qwen35-9b-unsloth-q6-k` — higher-quality office;
- `prod-gpt-oss20b-ggml-org-mxfp4` — deep reasoning / warm main.

Keep production GPT-OSS and Ollama `0.34.0` unchanged while the current qualification
cycle is open. Candidate qualification follows this funnel:

```text
load / resource / backend-aware completion integrity
-> tiny semantic sanity (`bc250-benchmark usecase`)
-> optional 4K/16K context performance where useful
-> gfx1013/runtime stability
-> optional sustained thermal/CU testing for finalists
-> full semantic + product-path + coexistence qualification
-> restoration/integrity verification
-> decision
```

Evidence must record the exact runtime/build/meaningful flags, KV cache type, memory/swap
and GPU-journal state. Use the highest-precision **feasible** KV configuration as the
correctness reference; compare compressed KV types model-by-model rather than changing a
global default. Do not force F16 or 32K when they make the candidate's intended envelope
infeasible.

For affected hybrid/SSM/direct-llama paths on gfx1013, compare runtime-default ubatch
against `384` as a conservative control only when warranted by the path. Do not set 384
globally from external GFX10 reports. Current CU/governor policy remains unchanged.

First establish current production `usecase` and representative generation/resource
metrics with normal task+embedding topology present. Only candidates that survive the
cheap gates advance to the broader human/general-office corpus. Human review should remain
explicit for subjective dimensions such as helpfulness, correction/follow-up quality and
overall daily-use acceptability. Do not manufacture a single precise score for inherently
subjective judgments.

### Lane F — agentic / coding

Agent mode is exclusive by design. Always capture normal topology before entry and
verify full restoration after leaving.

Keep two test layers separate:

1. `bc250-benchmark agent` — safe static shape/syntax/contract evidence;
2. actual `bc250-code` workflows on disposable inputs — review, refactor, tests,
   documentation, structured config work and commit-message generation.

The product helper must consume final content separately from native reasoning and fail
closed on nonterminal completion, output-limit truncation or literal reasoning markers.
Do not treat a successful HTTP response as valid inference unless terminal completion
integrity passes. Keep the package default output budget at 3072 until a bounded A/B
shows that a higher default improves complete product outputs without unacceptable cost;
use `CODING_AGENT_NUM_PREDICT` for that comparison.

Generated code must not be automatically executed as root. If behavior needs execution,
run deliberately reviewed output in a disposable/safe context and then run the relevant
real tests. The product claim remains a local coding helper, not an autonomous repository
agent.

For the next comparative funnel, use Ornith as baseline, then Qwable 9B, Qwen3.5 4B
Q6_K and Gemma 4 E4B Q4_K_M, followed by the baseline again. Reject cheaply on
completion integrity/static semantics before promoting candidates into broader real
`bc250-code` workflows. Only revisit Gemma 4 12B if the E4B comparison leaves that
question open.

### Lane G — MTP / speculative decoding

MTP is experimental and should stay behind the production-office lanes.

Prerequisites:

- one explicitly selected MTP catalog entry (`bc250-fetch-mtp ID` exposes packaged
  disabled candidates without making them part of generic convergence);
- pinned/recorded GGUF identity;
- an external `llama-server` whose CLI supports the required options;
- reviewed baseline is llama.cpp `b10069` / commit
  `178a6c44937154dc4c4eff0d166f4a044c4fceba`, but compatible newer releases may be
  tested and must be recorded.

Prepare and verify one MTP model at a time:

```bash
bc250-model list mtp --all
sudo bc250-fetch-mtp ID
sudo bc250-model status mtp ID --include-disabled --verbose
LLAMACPP=/path/to/llama-server bc250-run-mtp ID
```

A useful MTP comparison must include:

```text
same or closely comparable task/prompt
exact llama.cpp build/commit and effective launch flags
baseline throughput and answer quality
MTP throughput
accepted draft tokens / proposed draft tokens / acceptance rate
context, KV types, draft-n and effective ubatch settings
resident memory / MemAvailable / swap
stability and error logs
output-quality regressions
```

`models/experiments/compare-mtp.sh` is a quick speed probe, not a promotion evaluator.
Do not claim an MTP win from tok/s alone. A speedup that changes answer quality,
exhausts memory, or relies on a fragile external runtime is not a production win.

## 7. Routine revalidation vs specialist campaigns

Run full `bc250-revalidate` when:

- preparing a meaningful release candidate;
- runtime/service topology changed;
- a promoted role model changed;
- Open WebUI/package integration changed materially;
- enough independent changes accumulated that cross-lane interaction is uncertain.

Do **not** run full revalidation after a documentation-only/source-memory refresh.

Specialist campaigns should return to main integration with a compact handoff and should
not independently change production defaults, release metadata or cross-stream policy.

## 8. Promotion rules

Promotion requires all applicable gates:

```text
quality improvement or clear role benefit
real product-path success
resource safety on 16 GB shared GDDR6
acceptable latency/UX
repeatability
restoration/integrity clean
no regression of another production role
```

When a candidate is rejected, record **Retest only if** conditions so future work does
not repeat a disproven experiment without a material reason.
