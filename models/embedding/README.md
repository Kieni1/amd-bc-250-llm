# Embedding models

Embedding GGUFs use the same discovered Modelfile workflow as other models and
register on the primary Ollama instance at port `11434`.

```bash
bc250-model list embedding
sudo bc250-fetch-embeddings embed-jina-v5-small-retrieval-q4-k-m
```

`bc250-pull-embedding-model` remains a compatibility alias and accepts the same
selection. The current retrieval recommendation is
`embed-jina-v5-small-retrieval-q4-k-m`; Qwen3 Embedding remains available for
comparison. Jina's template is CC-BY-NC-4.0, so review its license before any
commercial use.

Verify a registered model before selecting the same name in Open WebUI:

```bash
curl -fsS http://127.0.0.1:11434/api/embed \
  -d '{"model":"embed-jina-v5-small-retrieval-q4-k-m","input":"BC-250 test"}'
```
