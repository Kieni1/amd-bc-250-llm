#!/usr/bin/env bash
# Run one enabled MTP/download-only catalog entry with llama.cpp.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x /usr/libexec/bc250-llm-server/modelctl ]]; then
  MANAGER="${MODEL_MANAGER:-/usr/libexec/bc250-llm-server/modelctl}"
  SOURCE_FILE="${SOURCE_FILE:-/etc/bc250-llm-server/mtp-models.toml}"
else
  MANAGER="${MODEL_MANAGER:-$SCRIPT_DIR/../modelctl.py}"
  SOURCE_FILE="${SOURCE_FILE:-$SCRIPT_DIR/models.toml}"
fi

PORT="${PORT:-8090}"
LLAMACPP="${LLAMACPP:-}"
[[ -x "$LLAMACPP" ]] || { echo "ERROR: set LLAMACPP to an executable llama-server." >&2; exit 1; }
[[ -x "$MANAGER" ]] || { echo "ERROR: model manager is not executable: $MANAGER" >&2; exit 1; }

choice="${1:-}"
case "$choice" in
  27b) choice=qwen3.6-27b-mtp ;;
  4b)  choice=qwen3.5-4b-mtp ;;
esac
if [[ -z "$choice" ]]; then
  echo "Usage: LLAMACPP=/path/to/llama-server $0 {27b|4b|ID}" >&2
  "$MANAGER" list mtp --source "$SOURCE_FILE" >&2
  exit 2
fi

resolved="$("$MANAGER" resolve mtp "$choice" \
  --provider download-only \
  --source "$SOURCE_FILE")" || exit 1
IFS=$'\t' read -r GGUF DEFAULT_CTX DEFAULT_DRAFT <<< "$resolved"
CTX="${CTX:-$DEFAULT_CTX}"
DRAFT_N_MAX="${DRAFT_N_MAX:-$DEFAULT_DRAFT}"
[[ -s "$GGUF" ]] || { echo "ERROR: missing $GGUF; run bc250-fetch-mtp first." >&2; exit 1; }

echo "MTP server: http://127.0.0.1:$PORT"
exec "$LLAMACPP" -m "$GGUF" \
  --host 127.0.0.1 --port "$PORT" \
  -ngl 99 -c "$CTX" -fa on -np 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --spec-type draft-mtp --spec-draft-n-max "$DRAFT_N_MAX" \
  --temp 0.7 --top-p 0.8 --top-k 20 --presence-penalty 1.5
