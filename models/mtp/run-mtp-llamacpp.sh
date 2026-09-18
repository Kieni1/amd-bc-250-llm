#!/usr/bin/env bash
# Run one disabled/download-only MTP catalog entry with llama.cpp.
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
UBATCH="${UBATCH:-}"
MIN_MEM_AVAILABLE_MIB="${MIN_MEM_AVAILABLE_MIB:-2048}"
REVIEWED_LLAMACPP_RELEASE="b10964"
MODE="mtp"
choice=""

[[ -x "$MANAGER" ]] || { echo "ERROR: model manager is not executable: $MANAGER" >&2; exit 1; }

show_usage() {
  local stream="${1:-1}"
  if [[ "$stream" == 2 ]]; then
    exec 1>&2
  fi
  cat <<USAGE
Usage: LLAMACPP=/path/to/llama-server $0 [--no-mtp] ID

Run an exact package MTP catalog entry with llama.cpp. --no-mtp launches the
same GGUF/settings without speculative decoding for a controlled baseline.

Convenience aliases (do not use them in recorded evidence):
  qwen35-9b   -> qwen3.5-9b-mtp
  qwen36-27b  -> qwen3.6-27b-mtp
  qwen38-27b  -> qwen3.8-27b-hauhaucs-mtp
  qwen36-35b  -> qwen3.6-35b-a3b-mtp

Available MTP entries:
USAGE
  "$MANAGER" list mtp --all --source "$SOURCE_FILE"
}

while (($#)); do
  case "$1" in
    -h|--help) show_usage; exit 0 ;;
    --no-mtp) MODE="baseline" ;;
    --mtp) MODE="mtp" ;;
    --) shift; break ;;
    -*) echo "ERROR: unknown option: $1" >&2; show_usage 2; exit 2 ;;
    *)
      [[ -z "$choice" ]] || { echo "ERROR: only one MTP ID may be selected." >&2; exit 2; }
      choice="$1"
      ;;
  esac
  shift
done
if (($#)); then
  [[ -z "$choice" && $# -eq 1 ]] || { echo "ERROR: only one MTP ID may be selected." >&2; exit 2; }
  choice="$1"
fi

case "$choice" in
  qwen35-9b)  choice=qwen3.5-9b-mtp ;;
  qwen36-27b) choice=qwen3.6-27b-mtp ;;
  qwen38-27b) choice=qwen3.8-27b-hauhaucs-mtp ;;
  qwen36-35b) choice=qwen3.6-35b-a3b-mtp ;;
  "") show_usage 2; exit 2 ;;
esac

resolved="$("$MANAGER" path mtp "$choice" --source "$SOURCE_FILE")" || exit 1
IFS=$'\t' read -r GGUF DEFAULT_CTX DEFAULT_DRAFT <<< "$resolved"
CTX="${CTX:-$DEFAULT_CTX}"
DRAFT_N_MAX="${DRAFT_N_MAX:-$DEFAULT_DRAFT}"

[[ -s "$GGUF" ]] || {
  echo "ERROR: missing $GGUF." >&2
  echo "Fetch this exact experiment first with:" >&2
  echo "  sudo bc250-fetch-mtp $choice" >&2
  exit 1
}
[[ -x "$LLAMACPP" ]] || { echo "ERROR: set LLAMACPP to an executable llama-server." >&2; exit 1; }
[[ "$PORT" =~ ^[1-9][0-9]*$ ]] && ((PORT <= 65535)) || { echo "ERROR: PORT must be 1..65535." >&2; exit 2; }
[[ "$CTX" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: CTX must be a positive integer." >&2; exit 2; }
[[ "$DRAFT_N_MAX" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: DRAFT_N_MAX must be a positive integer." >&2; exit 2; }
[[ "$MIN_MEM_AVAILABLE_MIB" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: MIN_MEM_AVAILABLE_MIB must be a positive integer." >&2; exit 2; }
if [[ -n "$UBATCH" ]]; then
  [[ "$UBATCH" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: UBATCH must be a positive integer." >&2; exit 2; }
fi

for cmd in awk grep pgrep rpm sed ss sudo; do
  command -v "$cmd" >/dev/null || { echo "ERROR: missing command: $cmd" >&2; exit 1; }
done

# Protected manager state is authoritative. Authenticate once, verify it, then
# run llama-server as the dedicated ollama service account rather than root.
sudo -v
status_output="$(sudo "$MANAGER" status mtp "$choice" --include-disabled --source "$SOURCE_FILE" --verbose 2>&1)" || {
  printf '%s\n' "$status_output" >&2
  echo "ERROR: model-state verification failed for $choice." >&2
  exit 1
}
printf '%s\n' "$status_output"
grep -Eq '^  Status:[[:space:]]+CURRENT$' <<< "$status_output" || {
  echo "ERROR: $choice is not CURRENT; reconcile it before runtime testing." >&2
  echo "Run: sudo bc250-model status mtp $choice --include-disabled --verbose" >&2
  exit 1
}
source_sha="$(sed -n 's/^  Source SHA-256:[[:space:]]*//p' <<< "$status_output" | head -n1)"
[[ "$source_sha" =~ ^[0-9a-f]{64}$ ]] || {
  echo "ERROR: verified model state did not expose a valid source SHA-256." >&2
  exit 1
}

if ss -H -ltn | awk -v suffix=":$PORT" '$4 ~ suffix "$" { found=1 } END { exit !found }'; then
  echo "ERROR: TCP port $PORT is already listening; refuse to collide with an existing service." >&2
  exit 1
fi

stale="$(pgrep -af '(^|/|[[:space:]])llama-server([[:space:]]|$)' || true)"
if [[ -n "$stale" ]]; then
  echo "ERROR: another llama-server process is already running; stop it before this isolated MTP run:" >&2
  printf '%s\n' "$stale" >&2
  exit 1
fi

mem_available_mib="$(awk '/^MemAvailable:/ { printf "%d", $2 / 1024 }' /proc/meminfo)"
[[ "$mem_available_mib" =~ ^[0-9]+$ ]] || { echo "ERROR: could not read MemAvailable." >&2; exit 1; }
if (( mem_available_mib < MIN_MEM_AVAILABLE_MIB )); then
  echo "ERROR: MemAvailable=${mem_available_mib} MiB is below the ${MIN_MEM_AVAILABLE_MIB} MiB launch floor." >&2
  echo "Stop other workloads or override MIN_MEM_AVAILABLE_MIB only for an explicitly recorded experiment." >&2
  exit 1
fi

help_output="$("$LLAMACPP" --help 2>&1 || true)"
missing_flags=()
for flag in --n-gpu-layers --ctx-size --flash-attn --parallel \
  --cache-type-k --cache-type-v --spec-type --spec-draft-n-max; do
  grep -Fq -- "$flag" <<< "$help_output" || missing_flags+=("$flag")
done
if ((${#missing_flags[@]})); then
  echo "ERROR: llama-server lacks required option(s): ${missing_flags[*]}" >&2
  echo "Reviewed llama.cpp release: $REVIEWED_LLAMACPP_RELEASE" >&2
  exit 1
fi
if [[ -n "$UBATCH" ]]; then
  grep -Fq -- '--ubatch-size' <<< "$help_output" || {
    echo "ERROR: UBATCH was requested but llama-server lacks --ubatch-size." >&2
    exit 1
  }
fi
cache_flags=()
grep -Fq -- '--cache-ram' <<< "$help_output" && cache_flags+=(--cache-ram 0)
grep -Fq -- '--no-cache-idle-slots' <<< "$help_output" && cache_flags+=(--no-cache-idle-slots)

sudo -n -u ollama test -x "$LLAMACPP" || {
  echo "ERROR: the ollama service user cannot execute LLAMACPP=$LLAMACPP." >&2
  echo "Place the reviewed llama-server build in an ollama-readable/executable path (for example /opt/llama.cpp/...)." >&2
  exit 1
}
sudo -n -u ollama test -r "$GGUF" || {
  echo "ERROR: the ollama service user cannot read the verified GGUF: $GGUF" >&2
  exit 1
}

args=(
  -m "$GGUF"
  --host 127.0.0.1 --port "$PORT"
  --n-gpu-layers 99 --ctx-size "$CTX" --flash-attn on --parallel 1
  "${cache_flags[@]}" --cache-type-k q8_0 --cache-type-v q8_0
  --temp 0.7 --top-p 0.8 --top-k 20 --presence-penalty 1.5
)
if [[ "$MODE" == "mtp" ]]; then
  args+=(--spec-type draft-mtp --spec-draft-n-max "$DRAFT_N_MAX")
fi
[[ -z "$UBATCH" ]] || args+=(--ubatch-size "$UBATCH")

package_nevra="$(rpm -q --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}' bc250-llm-server 2>/dev/null || printf 'bc250-llm-server-not-installed')"
echo "MTP target ID: $choice"
echo "Comparison mode: $MODE"
echo "Package NEVRA: $package_nevra"
echo "Source SHA-256: $source_sha"
echo "MemAvailable at launch: ${mem_available_mib} MiB (floor ${MIN_MEM_AVAILABLE_MIB} MiB)"
echo "Server: http://127.0.0.1:$PORT"
echo "Compatible llama-server detected; reviewed release: $REVIEWED_LLAMACPP_RELEASE"
echo "llama-server executable: $LLAMACPP"
echo "llama-server version/build:"
"$LLAMACPP" --version 2>&1 | sed 's/^/  /' || true
printf 'llama-server flags:'
printf ' %q' "${args[@]}"
printf '\n'
echo "KV cache: k=q8_0 v=q8_0"
echo "ubatch: ${UBATCH:-default}"
echo "runtime user: ollama"

exec sudo -n -u ollama -- "$LLAMACPP" "${args[@]}"
