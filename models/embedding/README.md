# Embedding models

```bash
sudo bc250-model list embedding
sudo bc250-setup-embedding-model
sudo bc250-setup-embedding-model embed-jina-v5-small-retrieval-q4-k-m
```

Embeddings use the dedicated `ollama-embedding.service` on port `11437`. Current choices are:

- `embed-jina-v5-small-retrieval-q4-k-m` — retrieval recommendation;
- `embed-qwen3-0.6b-q8-0` — alternative for comparison or licensing needs.

Jina is CC-BY-NC-4.0; review that restriction before commercial use. The
fresh Open WebUI RAG baseline uses Jina `Query: ` / `Document: ` prefixes. Qwen
is Apache-2.0 and should use an English task instruction on queries with no
content prefix. Changing the embedding model or prefixes requires reindexing.

The harder 2026-08-31 fixture no longer saturates completely: both Jina and Qwen
ranked the intended target first on 11/13 queries and second on the same two
near-duplicate cases (current-vs-archived lease policy and invoice 4821-vs-4822).
That is a useful tie rather than a reason to churn the RAG default; keep Jina as
the reviewed baseline and use Qwen when its Apache-2.0 license is preferable.

See `/usr/share/doc/bc250-llm-server/RAG.md` (source: `docs/RAG.md`) for the
German/French/English office-document pilot.

Verify before selecting the exact name in Open WebUI:

```bash
curl -fsS http://127.0.0.1:11437/api/embed \
  -d '{"model":"embed-jina-v5-small-retrieval-q4-k-m","input":"BC-250 test"}'
```


The dedicated service uses a 4K context and 10-minute keepalive. It is part of
normal mode and is stopped automatically when `bc250-agent-mode enter` starts the
exclusive coding backend. This prevents ordinary RAG indexing from evicting the
main production answer model while keeping the embedding residency bounded.
