# Office documents and RAG pilot

This is the recommended **local, privacy-oriented pilot** for searchable German,
French and English office documents. It uses the package's existing Open WebUI,
Tika and main Ollama instance. It adds no separate vector service or RAG daemon;
document synchronization remains an explicit operator action.

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
bc250-rag-import plan /srv/bc250-documents
```

For API sync, enable Open WebUI API keys deliberately, generate a key for the
account that should own the knowledge bases, and store it outside the repository:

```bash
sudo install -m 0600 -o root -g root /PATH/TO/KEY \
  /etc/bc250-llm-server/rag-api-key
sudo bc250-rag-import sync /srv/bc250-documents \
  --token-file /etc/bc250-llm-server/rag-api-key
```

The sync uses Open WebUI v0.11.0's incremental knowledge API. Treat these four generated knowledge-base name patterns as importer-managed: do not add unrelated files to them manually if you plan to use `--prune`. Unchanged files
are skipped. A changed Markdown file is uploaded first and only then replaces
the stale Open WebUI copy. Files removed locally are reported but retained
remotely; remove them only with an explicit second run using `--prune`. The
importer never uploads `sources/` PDFs and never stores the API key itself.

New knowledge bases are private to the API-key account. After the first sync,
review **Workspace → Knowledge** and assign public/restricted group permissions
manually. In particular, do not infer Open WebUI access from the filesystem word
`public`; it is only a local classification boundary.

For scans, run the OCR experiments first and evaluate the extracted text before
placing cleaned Markdown in `active/`:

```bash
bc250-ocr list
bc250-ocr test glm /PATH/TO/ONE-SCANNED-PAGE.png
```

Tika extracts searchable PDFs and office documents; it is not a substitute for
OCR on image-only scans.

## 7. Retrieval mode: important Open WebUI v0.11.0 behavior

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
