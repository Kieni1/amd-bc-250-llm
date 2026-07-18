#!/usr/bin/env bash
# Download Ministral and create the local Ollama coding model.
set -Eeuo pipefail
umask 0022

[[ ${EUID} -eq 0 ]] || {
  echo "ERROR: run with sudo." >&2
  exit 1
}

MODEL_NAME="${CODING_AGENT_MODEL:-coding-ministral3-8b-unsloth-ud-q5-k-xl}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
OLLAMA_URL="${OLLAMA_URL%/}"
REPO="unsloth/Ministral-3-8B-Instruct-2512-GGUF"
REVISION="${CODING_AGENT_REVISION:-latest}"
FILENAME="Ministral-3-8B-Instruct-2512-UD-Q5_K_XL.gguf"
EXPECTED_SHA256="${CODING_AGENT_SHA256:-}"
DEST="${CODING_AGENT_GGUF_DIR:-/var/llm/gguf}"
MIN_FREE_BYTES="${CODING_AGENT_MIN_FREE_BYTES:-8589934592}"

for cmd in awk curl hf jq ollama sha256sum; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $cmd" >&2
    exit 1
  }
done

curl --fail --silent --show-error \
  --connect-timeout 5 "${OLLAMA_URL}/api/tags" >/dev/null || {
  echo "ERROR: Ollama is not reachable at ${OLLAMA_URL}." >&2
  exit 1
}

getent group ollama >/dev/null || {
  echo "ERROR: the ollama group is missing; run bc250-install-ollama first." >&2
  exit 1
}
install -d -o ollama -g ollama -m 0750 "$DEST"

target="$DEST/$FILENAME"
if [[ ! -f "$target" ]]; then
  available="$(df -PB1 "$DEST" | awk 'NR==2 {print $4}')"
  if [[ ! "$available" =~ ^[0-9]+$ || "$available" -lt "$MIN_FREE_BYTES" ]]; then
    echo "ERROR: at least $((MIN_FREE_BYTES / 1024 / 1024 / 1024)) GiB free is required in $DEST." >&2
    exit 1
  fi

  args=(download "$REPO" "$FILENAME")
  [[ "$REVISION" == latest ]] || args+=(--revision "$REVISION")
  args+=(--local-dir "$DEST")
  [[ -n "${HF_TOKEN:-}" ]] && args+=(--token "$HF_TOKEN")
  hf "${args[@]}"
fi

if [[ -n "$EXPECTED_SHA256" ]]; then
  printf '%s  %s\n' "$EXPECTED_SHA256" "$target" | sha256sum --check --strict -
else
  echo "No checksum configured; using revision '$REVISION'."
fi
chown ollama:ollama "$target"
chmod 0640 "$target"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
modelfile="$script_dir/Modelfile"
if [[ ! -f "$modelfile" ]]; then
  modelfile="/usr/share/bc250-llm-server/examples/coding-agent/Modelfile"
fi
[[ -r "$modelfile" ]] || {
  echo "ERROR: coding-agent Modelfile was not found." >&2
  exit 1
}
declared_name="$(awk -F': ' '/^# Ollama model:/ {print $2; exit}' "$modelfile")"
[[ "$declared_name" == "$MODEL_NAME" ]] || {
  echo "ERROR: Modelfile declares '$declared_name', expected '$MODEL_NAME'." >&2
  exit 1
}

OLLAMA_HOST="$OLLAMA_URL" ollama create "$MODEL_NAME" -f "$modelfile"
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  -d "$(jq -n --arg model "$MODEL_NAME" '{model:$model}')" \
  "${OLLAMA_URL}/api/show" >/dev/null

echo "Created Ollama model: $MODEL_NAME"
echo "Try: bc250-code review path/to/file"
