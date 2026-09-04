# Office documents and RAG pilot

This is the recommended **local, privacy-oriented pilot** for searchable German,
French and English office documents. It uses the package's existing Open WebUI
and Tika, the main answer lane on `11434`, and the dedicated embedding lane on
`11437`. It adds no separate vector service or RAG daemon; document
synchronization remains an explicit operator action.

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
sudo bc250-model install production prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl
sudo bc250-model install embedding embed-jina-v5-small-retrieval-q4-k-m
sudo bc250-model list
```

The packaged Jina Q4_K_M file is the upstream refresh that includes
`pooling_type` GGUF metadata used by current Ollama to identify embedding models.
If an existing test index was built with the older package GGUF, refresh/reinstall
the model and **reindex** that Jina-backed Knowledge data.

Jina v5 uses `CC-BY-NC-4.0`. If the deployment later needs unrestricted
commercial use, select the packaged Apache-2.0 Qwen alternative instead:

```bash
sudo bc250-model install embedding embed-qwen3-0.6b-q8-0
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

Open WebUI 0.11.3 exposes three settings that are relevant to this appliance but
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
RUN_WARM_PREFIX=1 RUN_CONTEXT=0 RUN_THERMAL=0 bc250-benchmark generation \
  prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl
```

The last command measures a byte-identical shared document prefix followed by a
different suffix; the ordinary prefill/context curve remains cold-runner by design.
For `RAG_SYSTEM_CONTEXT` specifically, also compare the same follow-up conversation
through Open WebUI because the standalone Ollama benchmark cannot reproduce Open
WebUI's message placement.

## 4. Authoritative document tree and language policy

Keep the operator library outside Open WebUI under the package-created root:

```text
/srv/bc250-documents/
├── confidential/
│   └── COLLECTION/
│       ├── active/
│       └── sources/
└── public/
    └── COLLECTION/
        ├── active/
        └── sources/
```

The root is `root:root` mode `0750`. `sources/` holds the authoritative PDFs;
`active/` holds the canonical Markdown used for RAG. Do not index both copies:
that wastes Top-K slots and can return duplicate passages. PDFs without a ready
Markdown derivative can still be tested manually in Open WebUI, but the bulk
importer intentionally uploads only `active/*.md`.

For this library the German document is the authoritative original. The French
document is a translation and should be searched for French queries only. The
importer therefore creates separate knowledge bases per collection and security
boundary:

```text
[PUBLIC] COLLECTION — Originals
[PUBLIC] COLLECTION — Français
[CONFIDENTIAL] COLLECTION — Originals
[CONFIDENTIAL] COLLECTION — Français
```

There is deliberately no automatic query-language router. Attach/select **Originals** for German and English queries and **Français** for French queries. If a translation and original conflict, verify and cite the German
Originals collection. This separation also prevents parallel DE/FR chunks from
consuming two of the same Top-K retrieval slots.

## 5. Markdown metadata and provenance

Use YAML front matter like the installed template at
`/usr/share/bc250-llm-server/examples/rag/document-template.md`:

```yaml
---
document_id: "[DOCUMENT_ID]"
title: "[DOCUMENT_TITLE]"
language: "de-CH"
status: "currentness-not-verified"
authority: "original"
source_file: "[SOURCE_PDF_FILENAME]"
source_sha256: "[SOURCE_PDF_SHA256]"
relation:
  type: "translation-pair"
  counterpart: "[FRENCH_COUNTERPART.md]"
  source_language: "de-CH"
---
```

The importer intentionally supports only this small YAML subset: scalar
`document_id`, `title`, `language`, `status`, `authority`, `source_file`,
`source_sha256`, plus the three scalar `relation` keys shown above. Use two-space
indentation under `relation`; duplicate/unknown keys and other YAML constructs are
rejected. `source_file` must be a basename inside the collection's `sources/`
directory. Symlinked collection/active/source paths are rejected so provenance
cannot escape the operator-owned collection tree.

`authority` is recommended but not required for the existing DE/FR set:
`bc250-rag-import` infers `de-*` as `original`, and infers a `fr-*`
`translation-pair` whose `source_language` is German as `translation`. Other
languages must state authority explicitly. The importer verifies the declared
source SHA-256 before any network request. If `source_file` has been renamed but
exactly one PDF in `sources/` matches the SHA-256, it reports the mismatch and
continues; a missing or incorrect source checksum is an error.

## 6. Validate and bulk-sync active Markdown

First inspect routing and provenance. This does not contact Open WebUI:

```bash
sudo bc250-rag-import plan /srv/bc250-documents
```

For API sync, enable Open WebUI API keys deliberately, generate a key for the
account that should own the knowledge bases, and store it outside the repository:

```bash
sudo install -m 0600 -o root -g root /PATH/TO/KEY \
  /etc/bc250-llm-server/rag-api-key
sudo bc250-rag-import sync /srv/bc250-documents \
  --token-file /etc/bc250-llm-server/rag-api-key
```

The sync uses Open WebUI v0.11.3's incremental knowledge API. The packaged
baseline keeps `ENABLE_KNOWLEDGE_FILE_RETENTION=false`, so removal from a knowledge
base remains disposable and `/srv/bc250-documents` stays authoritative. Treat these
four generated knowledge-base name patterns as importer-managed: do not add unrelated
files to them manually if you plan to use `--prune`. Unchanged files
are skipped. A changed Markdown file is uploaded first and only then replaces
the stale Open WebUI copy. Files removed locally are reported but retained
remotely; remove them only with an explicit second run using `--prune`. `--prune`
also handles a generated Originals/Français lane that has become completely
empty, so the final stale remote file does not become stranded. The importer
never uploads `sources/` PDFs and never stores the API key itself.

New knowledge bases are private to the API-key account. After the first sync,
review **Workspace → Knowledge** and assign public/restricted group permissions
manually. In particular, do not infer Open WebUI access from the filesystem word
`public`; it is only a local classification boundary.

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

## 7. Retrieval mode: important Open WebUI v0.11.3 behavior

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

This detail matters on Open WebUI v0.11.3: knowledge permanently attached to a
model in Native function-calling mode is accessed through knowledge tools. 0.11.3 retains the knowledge-vector rebuild behavior so so a knowledge-base rebuild includes its files.
If Builtin Tools are disabled at the same time, that model-bound knowledge is not
retrieved. If you want a permanently model-bound knowledge base, keep Native
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

Normal 0.10.0 operation separates the answer and embedding runners: main Ollama
keeps `OLLAMA_MAX_LOADED_MODELS=1` on 11434, while the small embedding model lives
on dedicated 11437 with a 10-minute keepalive. This prevents indexing from
evicting the active production answer model while still keeping concurrency
bounded per process.

Inspect both pools when qualifying memory headroom:

```bash
curl -fsS http://127.0.0.1:11434/api/ps | jq
curl -fsS http://127.0.0.1:11437/api/ps | jq
bc250-benchmark rag
```

The RAG cycle now records whether a warm Gemma E4B answer model remains resident
while Jina runs on the dedicated embedding service. GPT-OSS 20B is the likely
memory-edge production case and was not re-qualified with this new layout before
0.10.0; rerun production/long-context tests with Jina warm after deployment.

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
