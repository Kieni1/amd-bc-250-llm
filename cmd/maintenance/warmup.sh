#!/usr/bin/env bash
set -Eeuo pipefail
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
MODEL="${WARMUP_MODEL:-prod-qwen3-4b-lmstudio-q6-k}"
KEEP="${WARMUP_KEEP_ALIVE:-3h}"

payload="$(python3 - "$MODEL" "$KEEP" <<'PY_PAYLOAD'
import json, sys
print(json.dumps({"model":sys.argv[1],"prompt":"Reply only: ok","stream":False,
                  "keep_alive":sys.argv[2],"options":{"num_predict":2}}))
PY_PAYLOAD
)"
for attempt in 1 2 3 4 5; do
  if response="$(curl --fail --silent --show-error --connect-timeout 5 --max-time 300 \
      -H 'Content-Type: application/json' --data "$payload" "$OLLAMA_URL/api/generate")" \
      && printf '%s' "$response" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("done") is True'; then
    echo "warmed: $MODEL (keep_alive=$KEEP)"
    exit 0
  fi
  echo "warmup attempt $attempt failed" >&2
  sleep $((attempt*3))
done
echo "ERROR: warmup failed for $MODEL" >&2
exit 1
