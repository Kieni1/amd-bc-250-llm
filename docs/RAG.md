# Office documents and RAG pilot

This is the recommended **local, privacy-oriented pilot** for searchable German,
French and English office documents. It uses the package's existing Open WebUI,
Tika and main Ollama instance; it adds no vector service, RAG daemon or automatic
ingestion.

**Never put confidential documents in this repository.** Real files belong only
in the live Open WebUI data under `/var/lib/open-webui/` and in encrypted
operator-controlled backups. The repository contains only a blank evaluation
template at `/usr/share/bc250-llm-server/examples/rag/pilot-evaluation.tsv`.

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
sudo bc250-fetch-models prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl
sudo bc250-fetch-embeddings embed-jina-v5-small-retrieval-q4-k-m
bc250-model list
```

Jina v5 uses `CC-BY-NC-4.0`. If the deployment later needs unrestricted
commercial use, select the packaged Apache-2.0 Qwen alternative instead:

```bash
sudo bc250-fetch-embeddings embed-qwen3-0.6b-q8-0
```

Do not mix embedding models or prefix schemes inside one existing index. Change
the Open WebUI embedding model/prefixes first, then reindex the affected files
or knowledge bases.

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
curl -fsS http://127.0.0.1:11434/api/embed \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"embed-jina-v5-small-retrieval-q4-k-m",
    "input":"Query: Welche Kündigungsfrist gilt?"
  }' | jq '.embeddings[0] | length'
```

Both packaged embedding models use up to 1024 dimensions. This request loads the
embedding model, so it is a deliberate operator test rather than part of
`bc250-verify`.

## 3. Fresh-install Open WebUI baseline

The packaged Quadlet supplies these starting values:

| Setting | Fresh-install value |
|---|---|
| Extraction engine | Tika |
| Embedding engine | Ollama |
| RAG Ollama URL | `http://host.containers.internal:11434` |
| Embedding model | `embed-jina-v5-small-retrieval-q4-k-m` |
| Text splitter | Token |
| Markdown header splitting | On |
| Chunk size | `1000` |
| Chunk overlap | `100` |
| Top K | `5` |
| Relevance threshold | `0` |
| Hybrid search | Off initially |
| Async embedding | Off |
| Reranker | None |

Open WebUI persists many Admin settings in `webui.db`. After first launch,
database values can override packaged `ConfigVar` defaults. Treat the Quadlet as
a fresh-install baseline and make later changes in **Admin Settings → Documents**.

The 1000/100/Top-K-5 baseline keeps retrieval context bounded on this 16 GB UMA
machine. Do not add a reranker until vector-only and hybrid-without-reranker
results have been measured.

## 4. Build a controlled pilot library

In **Workspace → Knowledge**, create collections by subject and confidentiality,
not just by language. Example *names only*:

```text
Office procedures
Product documentation
Customer project [PLACEHOLDER]
Restricted [PLACEHOLDER]
```

Start with approximately 10–30 locally held representative files. Suggested
placeholders for your own private test set:

```text
[GERMAN_SEARCHABLE_PDF]
[FRENCH_SEARCHABLE_PDF]
[GERMAN_SOURCE_FRENCH_QUERY]
[FRENCH_SOURCE_GERMAN_QUERY]
[DOCX_OR_ODT]
[MIXED_LANGUAGE_DOCUMENT]
[INVOICE_OR_REFERENCE_NUMBERS]
[CONFLICTING_OR_OUTDATED_VERSION]
[TABLE_HEAVY_DOCUMENT]
[POOR_SCAN_OR_SCANNED_PDF]
```

For scans, run the OCR experiments first and evaluate the extracted text before
it becomes retrieval input:

```bash
bc250-ocr list
bc250-ocr test glm /PATH/TO/ONE-SCANNED-PAGE.png
```

Tika extracts searchable PDFs and office documents; it is not a substitute for
OCR on image-only scans.

## 5. Retrieval mode: important Open WebUI v0.11.0 behavior

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

This detail matters on Open WebUI v0.11.0: knowledge permanently attached to a
model in Native function-calling mode is accessed through knowledge tools. If
Builtin Tools are disabled at the same time, that model-bound knowledge is not
retrieved. If you want a permanently model-bound knowledge base, keep Native
mode and enable only the **Knowledge Base** builtin-tool category, then verify
that the model reliably calls the knowledge tools. Do not switch the whole
appliance to legacy tool calling merely to make RAG work.

The packaged Gemma Modelfile already tells the answer model to treat retrieved
context as primary evidence, preserve names/numbers/dates, identify conflicts
and say when evidence is insufficient.

## 6. Evaluate retrieval separately from generation

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

## 7. Observe memory and model switching

During indexing and questions:

```bash
watch -n 2 bc250-status
```

In another terminal:

```bash
sudo journalctl -fu ollama.service
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

The package deliberately keeps `OLLAMA_MAX_LOADED_MODELS=1`. Indexing can evict
the answer model and questions can evict the embedding model. Record cold-start
latency before considering more resident models; the unified-memory budget is
more important than avoiding every model switch.

## 8. Second phase: hybrid search

Only after recording the vector-only baseline, enable Hybrid Search and repeat
the same evaluation set. Open WebUI combines BM25 keyword matching with vector
retrieval, which is particularly useful for exact clauses, invoice/document
numbers, product names, abbreviations and German compound terms.

Keep the reranker disabled for this second phase. A reranker adds memory and
latency and should earn its place through measured retrieval improvement.

## 9. Privacy, access and backups

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
- [Jina v5 small retrieval model card](https://huggingface.co/jinaai/jina-embeddings-v5-text-small-retrieval)
- [Qwen3 Embedding 0.6B GGUF model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF)
