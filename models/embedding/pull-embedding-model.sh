#!/usr/bin/env bash
# Pull and verify the RAG embedding model while online.
set -Eeuo pipefail
MODEL="${EMBED_MODEL:-nomic-embed-text}"
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export OLLAMA_HOST

for cmd in ollama curl python3; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: missing command: $cmd" >&2; exit 1; }
done
curl -fsS "http://${OLLAMA_HOST}/api/tags" >/dev/null || {
  echo "ERROR: Ollama API unavailable at $OLLAMA_HOST." >&2; exit 1;
}
ollama pull "$MODEL"
ollama list | awk -v model="$MODEL" 'NR==1 || $1==model || index($1, model ":")==1'
payload="$(python3 - "$MODEL" <<'PY_PAYLOAD'
import json, sys
print(json.dumps({"model": sys.argv[1], "input": "verification"}))
PY_PAYLOAD
)"
curl -fsS "http://${OLLAMA_HOST}/api/embed" \
  -H 'Content-Type: application/json' --data "$payload" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); e=d.get("embeddings"); assert isinstance(e,list) and e and e[0], "empty embedding"'
echo "Embedding model verified: $MODEL"
