# Embedding model

The embedding helper pulls and verifies the model used by Open WebUI for local
retrieval. It uses the primary Ollama instance on port `11434` and is separate
from the chat-model catalogs.

```bash
sudo bc250-pull-embedding-model
```

The default is `nomic-embed-text`. Set `EMBED_MODEL` to select another model
and `OLLAMA_HOST` to change the API endpoint. Configure the same model name in
Open WebUI after the verification succeeds.
