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
RESIDENCY_POLICY="${BC250_MTP_RESIDENCY_POLICY:-restore}"
OLLAMA_PORTS=(11434 11435 11436 11437)
declare -A OLLAMA_RESIDENCY_SNAPSHOT=()
RESIDENCY_CAPTURED=0
SERVER_PID=""

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

Direct operator runs snapshot and drain resident Ollama models before launch, then
restore the exact pre-run residency set on exit. Qualification/comparison harnesses
set BC250_MTP_RESIDENCY_POLICY=drain-only and intentionally leave Ollama cold.

Convenience aliases (do not use them in recorded evidence):
  qwen35-9b   -> qwen3.5-9b-mtp
  qwen36-27b  -> qwen3.6-27b-mtp
  qwen38-27b  -> qwen3.8-27b-hauhaucs-mtp

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
case "$RESIDENCY_POLICY" in
  restore|drain-only) ;;
  *) echo "ERROR: BC250_MTP_RESIDENCY_POLICY must be restore or drain-only." >&2; exit 2 ;;
esac
if [[ -n "$UBATCH" ]]; then
  [[ "$UBATCH" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: UBATCH must be a positive integer." >&2; exit 2; }
fi

for cmd in awk curl grep jq ollama pgrep rpm sed ss sudo timeout; do
  command -v "$cmd" >/dev/null || { echo "ERROR: missing command: $cmd" >&2; exit 1; }
done

ollama_api_ready() {
  local port="$1"
  curl -fsS --connect-timeout 1 --max-time 2 \
    "http://127.0.0.1:$port/api/version" >/dev/null 2>&1
}

ollama_resident_names() {
  local port="$1"
  curl -fsS --connect-timeout 1 --max-time 3 \
    "http://127.0.0.1:$port/api/ps" \
    | jq -r '[.models[]? | (.name // .model // empty) | sub(":latest$"; "")] | unique | .[]'
}

snapshot_ollama_residency() {
  local port
  for port in "${OLLAMA_PORTS[@]}"; do
    if ollama_api_ready "$port"; then
      OLLAMA_RESIDENCY_SNAPSHOT[$port]="$(ollama_resident_names "$port")" || {
        echo "ERROR: could not snapshot Ollama residency on :$port." >&2
        return 1
      }
    else
      OLLAMA_RESIDENCY_SNAPSHOT[$port]="__OFFLINE__"
    fi
  done
  RESIDENCY_CAPTURED=1
}

stop_ollama_model() {
  local port="$1" model="$2"
  env OLLAMA_HOST="http://127.0.0.1:$port" timeout 30 ollama stop "$model" \
    >/dev/null 2>&1
}

drain_ollama_residency() {
  local port model remaining drained=0
  for port in "${OLLAMA_PORTS[@]}"; do
    [[ "${OLLAMA_RESIDENCY_SNAPSHOT[$port]}" != "__OFFLINE__" ]] || continue
    while IFS= read -r model; do
      [[ -n "$model" ]] || continue
      echo "Draining Ollama :$port resident model: $model"
      stop_ollama_model "$port" "$model" || {
        echo "ERROR: could not unload Ollama model $model from :$port." >&2
        return 1
      }
      ((drained += 1))
    done <<< "${OLLAMA_RESIDENCY_SNAPSHOT[$port]}"
  done

  for port in "${OLLAMA_PORTS[@]}"; do
    [[ "${OLLAMA_RESIDENCY_SNAPSHOT[$port]}" != "__OFFLINE__" ]] || continue
    for _ in $(seq 1 120); do
      remaining="$(ollama_resident_names "$port")" || return 1
      [[ -z "$remaining" ]] && break
      sleep 0.25
    done
    [[ -z "$remaining" ]] || {
      echo "ERROR: Ollama :$port still has resident model(s) after drain: $remaining" >&2
      return 1
    }
  done
  echo "Ollama residency drained: $drained model(s); policy=$RESIDENCY_POLICY."
}

load_ollama_model() {
  local port="$1" model="$2" payload
  payload="$(jq -nc --arg model "$model" \
    '{model:$model,prompt:"",stream:false,options:{num_predict:1}}')"
  if curl -fsS --connect-timeout 2 --max-time 60 \
      "http://127.0.0.1:$port/api/generate" \
      -H 'Content-Type: application/json' --data-binary "$payload" >/dev/null 2>&1; then
    return 0
  fi
  # Embedding-only models need a non-empty embed probe. keep_alive is omitted so
  # the lane's configured default residency policy applies after restoration.
  payload="$(jq -nc --arg model "$model" \
    '{model:$model,input:["bc250 MTP residency restore probe"],truncate:false}')"
  curl -fsS --connect-timeout 2 --max-time 60 \
    "http://127.0.0.1:$port/api/embed" \
    -H 'Content-Type: application/json' --data-binary "$payload" >/dev/null 2>&1
}

restore_ollama_residency() {
  [[ "$RESIDENCY_CAPTURED" == 1 && "$RESIDENCY_POLICY" == restore ]] || return 0
  local port model current expected failed=0
  echo "Restoring pre-MTP Ollama residency set."
  for port in "${OLLAMA_PORTS[@]}"; do
    expected="${OLLAMA_RESIDENCY_SNAPSHOT[$port]}"
    [[ "$expected" != "__OFFLINE__" ]] || continue
    ollama_api_ready "$port" || {
      echo "ERROR: Ollama :$port is unavailable during residency restoration." >&2
      failed=1
      continue
    }

    if ! current="$(ollama_resident_names "$port")"; then
      echo "ERROR: could not inspect Ollama :$port during residency restoration." >&2
      failed=1
      continue
    fi
    while IFS= read -r model; do
      [[ -n "$model" ]] || continue
      grep -Fxq -- "$model" <<< "$expected" || stop_ollama_model "$port" "$model" || failed=1
    done <<< "$current"

    while IFS= read -r model; do
      [[ -n "$model" ]] || continue
      if ! current="$(ollama_resident_names "$port")"; then
        failed=1
        continue
      fi
      grep -Fxq -- "$model" <<< "$current" || load_ollama_model "$port" "$model" || failed=1
    done <<< "$expected"

    for _ in $(seq 1 120); do
      current="$(ollama_resident_names "$port")" || current="__API_ERROR__"
      [[ "$current" == "$expected" ]] && break
      sleep 0.25
    done
    [[ "$current" == "$expected" ]] || {
      echo "ERROR: Ollama :$port residency restoration mismatch: expected='${expected:-<empty>}' actual='${current:-<empty>}'" >&2
      failed=1
    }
  done
  ((failed == 0)) || return 1
  echo "Ollama residency restoration: PASS"
}

restore_on_exit() {
  local rc=$?
  trap - EXIT
  if ! restore_ollama_residency; then
    echo "ERROR: MTP run ended but Ollama residency restoration failed." >&2
    ((rc != 0)) || rc=74
  fi
  exit "$rc"
}

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

snapshot_ollama_residency || exit 1
if [[ "$RESIDENCY_POLICY" == restore ]]; then
  trap restore_on_exit EXIT
fi
drain_ollama_residency || exit 1

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
echo "Ollama residency policy: $RESIDENCY_POLICY"
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

if [[ "$RESIDENCY_POLICY" == drain-only ]]; then
  exec sudo -n -u ollama -- "$LLAMACPP" "${args[@]}"
fi

forward_server_signal() {
  local signal="$1" code="$2"
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "-$signal" "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    SERVER_PID=""
  fi
  exit "$code"
}
trap 'forward_server_signal INT 130' INT
trap 'forward_server_signal TERM 143' TERM

sudo -n -u ollama -- "$LLAMACPP" "${args[@]}" &
SERVER_PID=$!
set +e
wait "$SERVER_PID"
server_rc=$?
set -e
SERVER_PID=""
exit "$server_rc"
