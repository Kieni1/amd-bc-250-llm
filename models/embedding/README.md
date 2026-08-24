# Embedding models

```bash
bc250-model list embedding
sudo bc250-fetch-embeddings
sudo bc250-fetch-embeddings embed-jina-v5-small-retrieval-q4-k-m
```

Embeddings use the main Ollama instance on port `11434`. Current choices are:

- `embed-jina-v5-small-retrieval-q4-k-m` — retrieval recommendation;
- `embed-qwen3-0.6b-q8-0` — alternative for comparison or licensing needs.

Jina is CC-BY-NC-4.0; review that restriction before commercial use.
`bc250-pull-embedding-model` is a compatibility alias for the same workflow.

Verify before selecting the exact name in Open WebUI:

```bash
curl -fsS http://127.0.0.1:11434/api/embed \
  -d '{"model":"embed-jina-v5-small-retrieval-q4-k-m","input":"BC-250 test"}'
```
