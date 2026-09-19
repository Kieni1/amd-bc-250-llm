# 2026-09-19 BC-250 RAG finalist qualification

This is real-device/product-path evidence collected on the BC-250 while exact installed package
`bc250-llm-server-0.11.3-0.4.fc44.x86_64` was active. Later source releases may carry the model-role
decision forward, but this file does **not** qualify later package bytes.

## Platform and roles

- AMD BC-250 / Cyan Skillfish, modified 40-CU configuration
- 16 GiB unified-memory / TTM-constrained profile
- Ollama 0.34.0
- Open WebUI + nginx + Tika
- main Ollama: `127.0.0.1:11434`
- embedding Ollama: `127.0.0.1:11437`
- embedding model: `embed-jina-v5-small-retrieval-q4-k-m`
- Gemma answer model: `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl`
- Gemma Open WebUI preset: `bc250-office-documents`
- Qwen answer model: `prod-qwen35-9b-unsloth-q6-k`
- Qwen Open WebUI preset: `bc250-office-advanced`

## Broad direct RAG campaign

Corpus/contract:

- 56 documents
- 48 answerable cases
- 8 true abstention probes
- two repetitions per model
- fixed Jina retrieval, Top-K 8
- thinking disabled
- 96 qualification interactions per model

Both finalists achieved 96/96 target retrieval, 96/96 all-required-support retrieval, 8/8
abstention and zero truncations.

The raw evaluator had known deterministic false negatives (substring date collisions, terse
language classification, explicit unit/wording equivalence). After manual adjudication of those
obvious scorer defects, observed effective quality was approximately:

| Metric | Gemma E4B | Qwen 9B |
|---|---:|---:|
| effective overall | ~95/96 | ~93/96 |
| fact correctness | ~96/96 | ~95/96 |
| language adherence | ~96/96 | ~96/96 |
| exact citations | ~95/96 | ~94/96 |
| average direct-RAG latency | ~1.86 s | ~4.26 s |
| p95 latency | ~2.39 s | ~7.31 s |

These manually adjudicated values are evidence notes only. They must not be hard-coded as expected
scores; the package evaluator was corrected separately to handle those cases deterministically.

## Authenticated Open WebUI product path

Twelve isolated arms per model, three packaged RAG turns per arm, with model unload between arms:

| Metric | Gemma E4B | Qwen 9B |
|---|---:|---:|
| product-path turns | 36/36 pass | 36/36 pass |
| average latency | ~12.86 s | ~17.50 s |
| p95 latency | ~21.68 s | ~26.32 s |
| minimum MemAvailable | ~5.6 GiB | ~2.36 GiB |
| maximum GPU temperature | 75 C | 75 C |
| safety aborts | 0 | 0 |

Both presets therefore work correctly for short isolated product-path RAG sessions.

## Long-residency Open WebUI campaign

### Gemma E4B

- 14 consecutive subruns
- 42 RAG turns
- no unload inside the arm
- 42/42 answers passed
- 42/42 citations passed
- minimum MemAvailable: ~2766 MiB
- end-of-arm MemAvailable before unload: ~2770 MiB
- swap growth: ~15 MiB
- maximum GPU temperature: 76 C
- no safety abort
- no residency failure

### Qwen 9B

Qwen remained resident without unload and reproduced the earlier sustained-memory-pressure behavior
on the actual Open WebUI product path. It reached the campaign's configured 512 MiB safety floor
after only a few subruns:

- minimum MemAvailable observed: ~338 MiB
- MemAvailable near abort: ~426 MiB
- campaign safety threshold: 512 MiB
- reported swap increase remained relatively small; the external harness aggregate semantics were imperfect
- maximum GPU temperature: 76 C
- no answer/citation failure before abort

The external residency harness discovered an accounting defect around the partial final Qwen
subrun: the arm record showed two completed subruns / six completed turns while one aggregate path
counted the partial third subrun and approximately eight attempted turns. Treat only completed work
as complete evidence. This accounting issue does not alter the memory-safety observation that
caused the abort, but the aggregate attempted/completed totals are not reusable as a clean quality
completion count.

## Decision

Use `bc250-office-documents` / `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` as the production
RAG/document answer role for the current 16 GiB BC-250 profile.

Keep `bc250-office-advanced` / `prod-qwen35-9b-unsloth-q6-k` for its separate higher-quality
general-office role. Qwen was not rejected for answer quality; it is not the long-lived RAG default
because sustained residency leaves materially less memory headroom on this profile.

The 512 MiB value above was the residency campaign's safety-abort setting. It does not redefine the
whole-appliance revalidation policy or its existing hard floor.

## Remaining evidence boundary

This campaign strongly qualifies synthetic/direct retrieval and authenticated Open WebUI product
RAG with the tested fixtures. It does not yet constitute broad real-office-document qualification
for arbitrary PDFs, Tika/OCR edge cases, messy tables, collection lifecycle operations or long
user-created knowledge bases. Those remain product-evidence work, not a reason to reopen the RAG
answer-model tournament.
