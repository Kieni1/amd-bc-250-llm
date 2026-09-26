# Office documents and RAG pilot

This is the recommended **local, privacy-oriented pilot** for searchable German,
French and English office documents. It uses the package's existing Open WebUI
and Tika, the main answer lane on `11434`, and the dedicated embedding lane on
`11437`. The current package uses Apache Tika 4.0.0 for extraction and tells
Open WebUI to use its Tika-4 API contract. It adds no separate vector service or
RAG daemon; document synchronization remains an explicit operator action.

**Never put confidential documents in this repository.** Keep authoritative
source files under `/srv/bc250-documents/`, Open WebUI-managed copies under
`/var/lib/open-webui/`, and recoverable copies on encrypted operator-controlled
backups. The package contains only blank RAG templates under
`/usr/share/bc250-llm-server/examples/rag/`.

## 1. Back up Open WebUI before ingestion

If the instance already contains useful data, take a stopped full snapshot. The
normal configuration backup is not a complete RAG backup.

```bash
sudo systemctl stop open-webui.service
sudo tar --xattrs --acls --numeric-owner \
  -C /var/lib \
  -czf /PATH/ON/ENCRYPTED-STORAGE/open-webui-pre-rag-$(date +%F).tar.gz \
  open-webui
sudo systemctl start open-webui.service
```

## 2. Install answer and embedding models

For this non-commercial test branch, Jina v5 remains the default because it is
already the package's retrieval recommendation:

```bash
sudo bc250-model apply production prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl
sudo bc250-model apply embedding embed-jina-v5-small-retrieval-q4-k-m
bc250-model list
```

The packaged Jina Q4_K_M file is the upstream refresh that includes
`pooling_type` GGUF metadata used by current Ollama to identify embedding models.
If an existing test index was built with the older package GGUF, refresh the model with `sudo bc250-model refresh embedding embed-jina-v5-small-retrieval-q4-k-m` and **reindex** that Jina-backed Knowledge data.

Jina v5 uses `CC-BY-NC-4.0`. If the deployment later needs unrestricted
commercial use, select the packaged Apache-2.0 Qwen alternative instead:

```bash
sudo bc250-model apply embedding embed-qwen3-0.6b-q8-0
```

Do not mix embedding models or prefix schemes inside one existing index. Changing
the embedding model, embedding prefixes or chunking requires **reindexing** the
affected Knowledge documents. Changing the extraction engine or fixing source
extraction requires **re-uploading/re-syncing the source content**, because a
reindex works from text Open WebUI already extracted. Standalone chat attachments
likewise need re-uploading when their extracted text must change.

### Embedding prefixes

The fresh-install container defaults match Jina:

```text
Query prefix:   "Query: "
Content prefix: "Document: "
```

For Qwen3 Embedding, use an English query instruction and leave the content
prefix empty:

```text
Query prefix: Instruct: Retrieve relevant passages from German, French, and English office documents that answer the query.
Query: [user query]
Content prefix: [empty]
```

Qwen recommends a task-specific instruction on the query side for retrieval,
particularly in multilingual use.

To inspect embedding dimensionality without involving Open WebUI:

```bash
curl -fsS http://127.0.0.1:11437/api/embed \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"embed-jina-v5-small-retrieval-q4-k-m",
    "input":"Query: Welche Kündigungsfrist gilt?"
  }' | jq '.embeddings[0] | length'
```

Both packaged embedding models use up to 1024 dimensions. This request loads the
embedding model, so it is a deliberate operator test rather than part of
`bc250-verify`.

Use `bc250-benchmark embeddings` to compare the packaged models on the same
DE/FR/EN retrieval fixture. It reports Recall@1/@3, MRR, cross-language retrieval
and throughput and rejects inconsistent embedding dimensions; do not select an embedding model on tok/s alone.

## 3. Fresh-install Open WebUI baseline

The packaged Quadlet now uses the **moderate BC-250 profile** by default:

| Setting | Moderate standard | Conservative alternative |
|---|---:|---:|
| Extraction engine | Tika | Tika |
| Embedding engine | Ollama | Ollama |
| RAG Ollama URL | `http://host.containers.internal:11437` | same |
| Embedding model | `embed-jina-v5-small-retrieval-q4-k-m` | same |
| Text splitter | Token | Token |
| Markdown header splitting | On | On |
| Chunk min-size target | `0` (disabled) | `0` |
| Chunk size | `1500` | `1000` |
| Chunk overlap | `200` | `100` |
| Top K | `8` | `5` |
| Relevance threshold | `0` | `0` |
| Hybrid search | Off initially | Off initially |
| Embedding batch size | `1` | `1` |
| Async embedding | Off | Off |
| RAG system-context injection | Off | Off |
| Retrieval-query generation | Off for baseline | Off for baseline |
| Reranker | None | None |

The **moderate** 1500/200/Top-K-8 profile is the package standard for the 32K
document model: it gives each retrieval hit more surrounding office-document
context while keeping the injected context well below the model window. The
**conservative** 1000/100/Top-K-5 profile is useful when testing a larger model,
long chat history, tighter memory headroom or a retrieval problem where smaller
chunks are desirable. These are starting points to measure, not fixed quality
claims.

Open WebUI persists many Admin settings in `webui.db`. The installer therefore
offers `bc250-openwebui-setup init`, which applies the reviewed package-owned
provider/task/RAG state through supported APIs. The Quadlet remains the safe
bootstrap baseline; later intentional operator overrides are not reset silently.

The fresh-install `RAG_TEMPLATE` is intentionally source-grounded: if the retrieved
context does not support the requested fact, it asks the answer model to state that
evidence is insufficient instead of silently falling back to general model
knowledge. Existing database settings can override this template as well.
Keep retrieval-query generation off for the first measured baseline so the user
query reaches retrieval unchanged. Test task-model query rewriting only after the
embedding/chunking baseline is recorded. Do not add a reranker until vector-only
and hybrid-without-reranker results have been measured.

### Measured tuning candidates, not fresh-install defaults

Open WebUI 0.11.4 exposes settings that are relevant to this appliance but
remain conservative in the packaged Quadlet:

- `RAG_SYSTEM_CONTEXT=false`: enabling it moves retrieved context to a stable
  system-message position and can improve Ollama prefix/KV-cache reuse on follow-up
  questions. Test answer grounding as well as latency before enabling it.
- `CHUNK_MIN_SIZE_TARGET=0`: with Markdown header splitting enabled, a non-zero
  target can merge tiny sections into more coherent chunks. Test `750` and `1000`
  against the package retrieval fixture before reindexing real knowledge bases.
- `RAG_EMBEDDING_BATCH_SIZE=1`: Ollama accepts batched embedding inputs, but larger
  batches can increase memory pressure. Compare `1`, `4`, `8` and `16` on the real
  BC-250 before changing the default.

Changing chunking or the embedding model requires reindexing affected Knowledge
documents. `RAG_SYSTEM_CONTEXT` changes prompt placement rather than stored
embeddings, so it should be tested with a repeated multi-turn RAG conversation.
The package deliberately does not auto-tune these settings.

Use the local quality lanes before and after a tuning experiment:

```bash
bc250-benchmark embeddings
bc250-benchmark rag-quality
bc250-benchmark rag-quality --think true
bc250-benchmark rag-quality --think false
bc250-benchmark generation --profile compare \
  prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl
bc250-benchmark owui-rag OWUI_RAG_MODEL \
  --token-file /root/owui-test.key
sudo bc250-benchmark owui-embedding-batch --token-file /root/owui-test.key
sudo bc250-benchmark owui-chunk-min OWUI_RAG_MODEL --token-file /root/owui-test.key
sudo bc250-benchmark owui-system-context OWUI_RAG_MODEL \
  --token-file /root/owui-test.key
```

The Open WebUI tuning commands are explicit experiments and restore the observed
package-owned setting before returning. `owui-system-context` performs the repeated
multi-turn comparison through Open WebUI because standalone Ollama generation cannot
reproduce Open WebUI's message placement.

`owui-rag` is the non-tuning product-path qualification. Prefer an exact active Open WebUI
preset such as `bc250-office-documents`. A raw Ollama base-model ID is also accepted when it
maps to exactly one active preset; ambiguous or unknown mappings fail before temporary
Knowledge/upload state is created. The benchmark keeps only a sanitized preset-to-base-model
mapping in its metadata and waits for real Open WebUI HTTP readiness before beginning.

`rag-quality` keeps retrieval, factual/abstention acceptance, output language and citation
as separate checks. The evaluator uses boundary-aware deterministic matching rather than
naïve substrings or an LLM judge; fixtures can enumerate semantic alternatives and numeric
equivalence explicitly. Short numeric/identifier answers may be recorded as
`language_measurable=false` / `language_not_measurable=true` without becoming a language failure. Its canonical summary also
checks the exact expected case set so missing, duplicate or unexpected rows are structural
failures rather than misleading quality results.

### Current production RAG answer-model decision

The completed 2026-09-19 BC-250 campaign keeps **Office – Documents**
(`bc250-office-documents`) with `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` as the production
document/RAG answer role for the current 16 GiB profile. This is primarily a sustained-residency
resource decision, not an answer-quality rejection of Qwen 9B.

| Evidence | Gemma E4B | Qwen 9B | Qwen3.8 27B IQ3_XXS (16K partial) |
|---|---:|---:|---:|
| Broad/direct RAG overall | 94/96 | 93/96 | 5/5 before resource abort; not comparable to full corpus |
| Fact / citation | 95/96 / 95/96 | 95/96 / 94/96 | 5/5 cited cases only |
| Authenticated Open WebUI short path | 36/36 pass | 36/36 pass | not qualified |
| Long-residency result | 42/42 pass | safety-aborted during third subrun | safety-aborted during sustained RAG |
| Minimum / near-abort MemAvailable | ~2766 MiB | ~338 / ~426 MiB | ~280 MiB before abort |
| Production status | document/RAG default | separate higher-quality office role | experimental only; 16K rejected |

Gemma's continuous arm completed 14 subruns / 42 turns without unload, with roughly 15 MiB swap
growth and no safety or residency failure. Qwen produced correct answers/citations before abort but
reproduced the earlier sustained-memory-pressure behavior on the actual Open WebUI product path.
The Qwen preset remains useful for its separate higher-quality general-office role; it should not
silently replace Gemma as the long-lived document/RAG default on this memory profile.

The long-residency campaign used a 512 MiB MemAvailable safety-abort threshold; that campaign margin
is not the whole-appliance hard floor. The later Qwen3.8 27B IQ3_XXS 16K experiment passed its first
five cited RAG cases but then hit the sustained-memory safety gate, so 16K is rejected on this 16 GiB
profile. The same verified model/GGUF identity is bounded to 8K for explicit experimentation only and
is not a production RAG candidate. The corrected deterministic rescoring above supersedes the earlier
approximate/manual-adjudication summary; full measurements and provenance remain in
`development/model-runs/2026-09-20-rag-qualification-conclusion.md`.

## 4. Authoritative corpus lifecycle and language policy

The package owns a simple filesystem lifecycle below `/srv/bc250-documents`; Open WebUI remains a
derived index, not the source of truth:

```text
/srv/bc250-documents/
├── public/
│   └── COLLECTION/
│       ├── inbox/{german,french,bilingual}/
│       ├── sources/
│       ├── working/
│       ├── active/
│       └── superseded/
└── confidential/
    └── COLLECTION/
        ├── inbox/{german,french,bilingual}/
        ├── sources/
        ├── working/
        ├── active/
        └── superseded/
```

`bc250-rag init` creates the collection. Public-source collections default to mode `0750`;
confidential collections default to root-private mode `0700`. `sources/` contains immutable
authoritative inputs, `working/` contains drafts needing review, `active/` contains the only Markdown
eligible for ingestion, and `superseded/` retains previous revisions for audit. Never index both a
source PDF and its normalized Markdown.

For this appliance the supplied German document is treated as the authoritative/main version and a
French counterpart as its translation unless the source itself establishes different legal authority.
The importer creates separate knowledge bases so parallel DE/FR chunks do not consume the same Top-K
slots:

```text
[PUBLIC] COLLECTION — Originals
[PUBLIC] COLLECTION — Français
[CONFIDENTIAL] COLLECTION — Originals
[CONFIDENTIAL] COLLECTION — Français
```

There is deliberately no automatic query-language router. Attach/select **Originals** for German and
English queries and **Français** for French queries. If source and translation conflict, verify against
the authoritative German source.

## 5. Batch preparation with a mandatory human gate

The supported first-pass workflow is one local command, not a separate conversion framework:

```bash
sudo bc250-rag init public municipal-regulations
# copy PDFs into the appropriate inbox lane
sudo bc250-rag prepare-batch public municipal-regulations --dry-run
sudo bc250-rag prepare-batch public municipal-regulations
sudo bc250-rag review public municipal-regulations
sudo bc250-rag validate public municipal-regulations --include-working
sudo bc250-rag activate public municipal-regulations --all-ready
```

`prepare-batch` uses local `pdfinfo`/`pdftotext` and the exclusive local agent lane on `127.0.0.1:11436`.
If the agent lane is inactive it enters agent mode for the batch and restores normal topology afterwards.
The agent call uses Ollama `/api/chat` with native thinking kept separate from final `message.content`; truncated, empty, fenced or literal reasoning-contaminated final output is rejected before a draft is written. Fidelity checks run only against that validated final Markdown.
No external OCR, conversion, translation or hosted document API is used. Automation writes **only** to
`working/`; it never promotes generated text directly into `active/`.

Inbox semantics:

- `german/`: produce a `de-CH` authoritative draft.
- `french/`: produce a `fr-CH` translation draft and pair it during review.
- `bilingual/`: produce separate DE and FR drafts sharing the source; do not index mixed-language output.

The local transformation prompt preserves complete substantive wording, original legal numbering, dates,
amounts and identifiers while removing extraction/layout noise. Unique codes, markers and alphanumeric labels must not be discarded as layout noise unless repeated decorative/page-furniture behavior is clear. It is intentionally conservative: scanned PDFs with little selectable text are reported as `DEFERRED — OCR required`, and unusually large documents above the safe single-pass limit as `DEFERRED — source split required`; genuine processing failures are reported separately as `ERROR`. This avoids growing `bc250-rag` into a fragile OCR/chunking engine.

The review step is where the operator confirms titles, stable `document_family`, effective date or edition,
authority role, and DE/FR counterpart. Review numbering covers only drafts that still need review, and the prompts make the effective-date-or-edition requirement explicit. For legal, financial or technical sources, visually compare representative PDF pages before marking the draft ready. The agent output is an editorial proposal, not an authoritative transformation until reviewed.

Activation is explicit and atomic at the collection level: a reviewed replacement supersedes the previous
active revision for the same `document_family` and language, retaining old evidence.

## 6. Markdown metadata, validation and ingestion

Use compact front matter like the packaged template:

```yaml
---
document_id: "biel_ortspolizeireglement_de-CH_2023-01-01"
document_family: "biel_ortspolizeireglement"
title: "Ortspolizeireglement der Stadt Biel (OPolR)"
organisation: "Stadt Biel"
language: "de-CH"
authority_role: "authoritative"
document_type: "Ortspolizeireglement"
edition: "Stand 1. Januar 2023"
effective_from: "2023-01-01"
status: "currentness-not-verified"
review_required: false
source_file: "130101_Ortspolizeireglement_der_Stadt_Biel.pdf"
source_sha256: "[64-HEX-SHA256]"
normalization: "Mechanical/local-agent extraction cleanup; source wording preserved"
---
```

For a French translation, use `authority_role: "translation"` and `translation_of` naming the reviewed
German Markdown counterpart. Preserve source article/paragraph identifiers exactly; never invent replacement
legal numbering merely to make retrieval IDs unique. Extra package metadata may use `bc250_*` keys so the
schema can evolve without accepting arbitrary YAML.

`bc250-rag validate` verifies source-file confinement, SHA-256 provenance, review state, unique document IDs,
and one active revision per document-family/language. `currentness-not-verified` is deliberately a warning,
not an automatic failure; ambiguity should remain visible to the operator rather than be silently invented.

Inspect the complete ingestion plan without contacting Open WebUI:

```bash
sudo bc250-rag plan /srv/bc250-documents
```

Then sync only reviewed `active/*.md` files:

```bash
sudo install -m 0600 -o root -g root /PATH/TO/KEY /etc/bc250-llm-server/rag-api-key
sudo bc250-rag ingest --token-file /etc/bc250-llm-server/rag-api-key
```

`ingest` validates the lifecycle schema before using the package-pinned Open WebUI incremental
knowledge API. Unchanged files are skipped and changed Markdown is uploaded before the stale remote copy is
removed. Local removals are reported but retained remotely unless `--prune` is explicitly supplied. The
credential must be a non-empty private regular file (normally `0600`); it is never stored in the corpus.

`bc250-rag-import plan|sync` remains as a compatibility interface for existing pre-0.4 corpora. New work
should use `bc250-rag`.

### OCR workflow for scanned office documents

Use Tika for text-native PDFs and office files. Use OCR only for image-only or
poorly extracted scans; OCR is a preprocessing step before RAG, not a replacement
for the answer model.

Current OCR test set:

| Model | Starting use |
|---|---|
| `exp-glm-ocr-ggml-q8-0` | current fidelity leader on packaged office fixtures |
| `exp-ovisocr2-abiray-q8-0` | faster page-to-Markdown/table alternative |

Use `bc250-ocr` for reproducible ingestion tests rather than exposing OCR models
as normal chat models:

```bash
bc250-ocr list
bc250-ocr test glm /PATH/TO/ONE-SCANNED-PAGE.png
```

Use the engine names reported by `bc250-ocr list`. For the pilot, process page
images individually, preserve page order, review the OCR output, and save the
cleaned canonical Markdown under `active/` before indexing it. Do not index both
the scan and its cleaned Markdown derivative.

OCR prompts should **transcribe and preserve the source language**. Do not ask the
OCR model to translate, summarize or rewrite German/French/English content during
extraction. Translation or interpretation belongs in the downstream LLM step.
Preserve headings, paragraphs, tables, numbers, dates and reading order where the
model supports them.

For a comparable regression check, run `bc250-benchmark ocr`. It uses packaged
DE/FR/mixed office-page fixtures with model-specific prompts and reports token precision/recall/F1, character similarity, exact-field/order scores and resource telemetry. Use `bc250-ocr test ENGINE REAL-PAGE.png` on a
representative scan corpus before choosing the production OCR path.

Multimodal OCR GGUFs require their matching image/projector path where applicable;
`bc250-ocr` should own those model-specific invocation details. Open WebUI can be
used for ad-hoc visual A/B tests, but its chat output should not become the
canonical RAG source without the same review/cleanup step.

## 7. Retrieval mode: Open WebUI 0.11.4 candidate behavior

Use **Focused Retrieval** for the growing library. Use **Full Context** only for
one short document that comfortably fits the model context.

For the most predictable baseline with the relatively small local Gemma model:

1. Create an Open WebUI model preset named `Office Documents – Pilot` using
   `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl`.
2. Keep File Context enabled.
3. Keep Memory, Web Search and Code Interpreter disabled.
4. Keep Builtin Tools disabled for this first baseline.
5. **Attach the knowledge base in the chat**, choose Focused Retrieval, and ask
   the evaluation questions.

The preceding v0.11.3 device baseline showed that knowledge permanently attached to a
model in Native function-calling mode is accessed through knowledge tools, and that a knowledge-base rebuild includes its files. The v0.11.4 candidate must requalify this browser/product path rather than silently inheriting the old result. If model-bound knowledge still requires builtin knowledge tools, leaving Builtin Tools disabled will prevent that retrieval path. If you want a permanently model-bound knowledge base, keep Native
mode and enable only the **Knowledge Base** builtin-tool category, then verify
that the model reliably calls the knowledge tools. Do not switch the whole
appliance to legacy tool calling merely to make RAG work.

The packaged Gemma Modelfile already tells the answer model to treat retrieved
context as primary evidence, preserve names/numbers/dates, identify conflicts
and say when evidence is insufficient.

## 8. Evaluate retrieval separately from generation

Copy the installed blank template somewhere private and fill it with your test
questions:

```bash
cp /usr/share/bc250-llm-server/examples/rag/pilot-evaluation.tsv \
  /PATH/ON/PRIVATE-STORAGE/rag-pilot.tsv
```

Include German→German, French→French and cross-language DE↔FR questions; exact
dates, amounts, names and reference numbers; conflicting versions; and questions
whose answer is absent. For every result record whether the correct source and
passage were retrieved before judging the generated answer.

If retrieval selected the wrong passage, changing the answer model usually does
not fix the retrieval problem. Tune extraction, prefixes, chunking, Top K or
hybrid search first.

## 9. Observe memory and model switching

During indexing and questions:

```bash
watch -n 2 bc250-status
```

In another terminal:

```bash
sudo journalctl -fu ollama.service -u ollama-embedding.service
```

Inspect what Ollama actually keeps resident:

```bash
curl -fsS http://127.0.0.1:11434/api/ps | jq
```

After the pilot:

```bash
sudo bc250-verify
sudo du -sh /var/lib/open-webui
sudo du -sh /var/lib/open-webui/uploads \
  /var/lib/open-webui/vector_db 2>/dev/null
```

Normal operation separates the answer and embedding runners: main Ollama
keeps `OLLAMA_MAX_LOADED_MODELS=1` on 11434, while the small embedding model lives
on dedicated 11437 with a 10-minute keepalive. This prevents indexing from
evicting the active production answer model while still keeping concurrency
bounded per process.

Inspect both pools when qualifying memory headroom:

```bash
curl -fsS http://127.0.0.1:11434/api/ps | jq
curl -fsS http://127.0.0.1:11437/api/ps | jq
bc250-benchmark rag-cycle embed-jina-v5-small-retrieval-q4-k-m \
  prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl
```

The RAG cycle now records whether a warm Gemma E4B answer model remains resident
while Jina runs on the dedicated embedding service. GPT-OSS 20B remains the
dedicated production memory-edge qualification. Rerun it after a candidate
promotion or material runtime change.

## 10. Second phase: hybrid search

Only after recording the vector-only baseline, enable Hybrid Search and repeat
the same evaluation set. Open WebUI combines BM25 keyword matching with vector
retrieval, which is particularly useful for exact clauses, invoice/document
numbers, product names, abbreviations and German compound terms.

Keep the reranker disabled for this second phase. A reranker adds memory and
latency and should earn its place through measured retrieval improvement.

## 11. Privacy, access and backups

- Require Open WebUI authentication.
- Keep confidential knowledge bases private/restricted and grant access only to
  the required users or groups.
- Disable public/open sharing for confidential material.
- Keep cloud model/API connections and web search disabled for confidential
  document work unless an operator deliberately approves them.
- Do not expose Tika or Ollama ports to untrusted networks.
- Treat `/var/lib/open-webui/webui.db`, `/var/lib/open-webui/uploads/` and
  `/var/lib/open-webui/vector_db/` as confidential data.
- `bc250-maintenance run backup` does **not** include uploads or vector data. Use
  a stopped full `/var/lib/open-webui` snapshot on encrypted storage when the
  RAG corpus must be recoverable.

## Choosing the document path

| Material | Preferred starting approach |
|---|---|
| One short document | Full Context |
| A few documents for one task | Attach to the chat |
| Growing office library | Focused RAG, then test hybrid search |
| Exact tables/accounting data | Deterministic database/SQL query |
| Exact clause/reference lookup | Hybrid keyword + vector retrieval |
| Scanned documents | OCR first, then RAG |
| Frequently changing confidential knowledge | RAG rather than fine-tuning |

Fine-tuning is not a substitute for a document store with citations and
revocable data. GraphRAG or an external vector database would add complexity
without a demonstrated benefit for this single-machine pilot.

## References

- [Open WebUI environment configuration](https://docs.openwebui.com/reference/env-configuration/)
- [Open WebUI RAG and File Context behavior](https://docs.openwebui.com/features/chat-conversations/rag/)
- [Open WebUI Knowledge retrieval modes](https://docs.openwebui.com/features/workspace/knowledge/)
- [Open WebUI API endpoints](https://docs.openwebui.com/reference/api-endpoints/)
- [Open WebUI API keys](https://docs.openwebui.com/features/authentication-access/api-keys/)
- [Jina v5 small retrieval model card](https://huggingface.co/jinaai/jina-embeddings-v5-text-small-retrieval)
- [Qwen3 Embedding 0.6B GGUF model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF)
- [GLM-OCR GGUF](https://huggingface.co/ggml-org/GLM-OCR-GGUF)
- [OvisOCR2 GGUF](https://huggingface.co/Abiray/OvisOCR2-GGUF)

## Upload resource limits

The Open WebUI container limits ad-hoc office uploads to 128 MiB and 20 files per
request/chat and allowlists common office/text/document formats through
`RAG_ALLOWED_FILE_EXTENSIONS`. Knowledge-base synchronization is still intended
for curated bulk content and has its own lifecycle. `RAG_EMBEDDING_BATCH_SIZE`
remains 1 until the BC-250 embedding benchmark demonstrates that larger Ollama
batches improve throughput without memory or compatibility regressions.
