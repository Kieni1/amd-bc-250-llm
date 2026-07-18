#!/usr/bin/env bash
# Run one downloaded MTP experiment with llama.cpp.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_FILE="${SOURCE_FILE:-/etc/bc250-llm-server/experiment-sources.sh}"
DEST="${DEST:-/var/llm/gguf-experiments}"
if [[ ! -r "$SOURCE_FILE" && -r "$SCRIPT_DIR/experiment-sources.sh" ]]; then
  SOURCE_FILE="$SCRIPT_DIR/experiment-sources.sh"
fi
PORT="${PORT:-8090}"
LLAMACPP="${LLAMACPP:-}"

[[ -x "$LLAMACPP" ]] || { echo "ERROR: set LLAMACPP to an executable llama-server." >&2; exit 1; }
[[ -r "$SOURCE_FILE" ]] || { echo "ERROR: cannot read $SOURCE_FILE" >&2; exit 1; }

mtp_ids=() mtp_files=() mtp_contexts=() mtp_drafts=()
ollama_model() { :; }
mtp_model() {
  [[ $# -eq 6 ]] || { echo "ERROR: bad mtp_model entry in $SOURCE_FILE" >&2; exit 1; }
  mtp_ids+=("$1"); mtp_files+=("$4"); mtp_contexts+=("$5"); mtp_drafts+=("$6")
}
# shellcheck source=/dev/null
source "$SOURCE_FILE"

choice="${1:-}"
case "$choice" in
  27b) choice=qwen3.6-27b-mtp ;;
  4b)  choice=qwen3.5-4b-mtp ;;
esac

index=""
for i in "${!mtp_ids[@]}"; do [[ "${mtp_ids[$i]}" == "$choice" ]] && index="$i"; done
if [[ -z "$index" ]]; then
  echo "Usage: LLAMACPP=/path/to/llama-server $0 {27b|4b|ID}" >&2
  printf 'Available IDs:\n' >&2
  printf '  %s\n' "${mtp_ids[@]}" >&2
  exit 1
fi

id="${mtp_ids[$index]}"
GGUF="$DEST/$id/${mtp_files[$index]}"
CTX="${CTX:-${mtp_contexts[$index]}}"
DRAFT_N_MAX="${DRAFT_N_MAX:-${mtp_drafts[$index]}}"
[[ -s "$GGUF" ]] || { echo "ERROR: missing $GGUF; run fetch-experiments.sh first." >&2; exit 1; }

echo "MTP server: http://127.0.0.1:$PORT"
exec "$LLAMACPP" -m "$GGUF" \
  --host 127.0.0.1 --port "$PORT" \
  -ngl 99 -c "$CTX" -fa on -np 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --spec-type draft-mtp --spec-draft-n-max "$DRAFT_N_MAX" \
  --temp 0.7 --top-p 0.8 --top-k 20 --presence-penalty 1.5
