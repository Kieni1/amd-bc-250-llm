#!/usr/bin/env bash
set -Eeuo pipefail
# An Agent session is exclusive. Never wake the main lane behind the user's
# back, even if a scheduled wake timer fires during an Agent operation.
if systemctl is-active --quiet ollama-agent.service; then
  echo "SKIP: warmup suppressed in Agent mode"
  exit 0
fi
if ! systemctl is-active --quiet ollama.service; then
  echo "SKIP: main Ollama lane is inactive; warmup will not start it"
  exit 0
fi
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
MODEL="${WARMUP_MODEL:-prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl}"
KEEP="${WARMUP_KEEP_ALIVE:-15m}"

payload="$(python3 - "$MODEL" "$KEEP" <<'PY_PAYLOAD'
import json, sys
print(json.dumps({"model":sys.argv[1],"prompt":"Reply only: ok","stream":False,
                  "keep_alive":sys.argv[2],"options":{"num_predict":2}}))
PY_PAYLOAD
)"
for attempt in 1 2 3; do
  if response="$(curl --fail --silent --show-error --connect-timeout 5 --max-time 120 \
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
