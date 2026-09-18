#!/usr/bin/env bash
# Same-model llama.cpp baseline vs MTP comparison with evidence capture.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x /usr/libexec/bc250-llm-server/modelctl ]]; then
  MANAGER="${MODEL_MANAGER:-/usr/libexec/bc250-llm-server/modelctl}"
  SOURCE_FILE="${SOURCE_FILE:-/etc/bc250-llm-server/mtp-models.toml}"
  RUNNER="${MTP_RUNNER:-/usr/libexec/bc250-llm-server/run-mtp-llamacpp.sh}"
else
  MANAGER="${MODEL_MANAGER:-$SCRIPT_DIR/../modelctl.py}"
  SOURCE_FILE="${SOURCE_FILE:-$SCRIPT_DIR/../mtp/models.toml}"
  RUNNER="${MTP_RUNNER:-$SCRIPT_DIR/../mtp/run-mtp-llamacpp.sh}"
fi

LLAMACPP="${LLAMACPP:-}"
PORT="${PORT:-8090}"
NUM_PREDICT="${NUM_PREDICT:-400}"
REPEATS="${REPEATS:-3}"
READY_TIMEOUT="${READY_TIMEOUT:-180}"
INFER_TIMEOUT="${INFER_TIMEOUT:-900}"
PROMPT="${PROMPT:-Write a concise 300-word explanation of how memory bandwidth limits local LLM inference.}"
RESULT_BASE="${RESULT_BASE:-$HOME}"
choice="${1:-}"
ACTIVE_PGID=""
SAMPLER_PID=""

show_usage() {
  cat <<USAGE
Usage: LLAMACPP=/path/to/llama-server $0 ID

Compare the same catalog GGUF twice with the same llama.cpp build and server
settings: first with MTP disabled, then with draft-mtp enabled. Exact catalog
IDs are preferred for recorded evidence.

Available MTP entries:
USAGE
  "$MANAGER" list mtp --all --source "$SOURCE_FILE"
}

case "$choice" in
  -h|--help) show_usage; exit 0 ;;
  qwen35-9b)  choice=qwen3.5-9b-mtp ;;
  qwen36-27b) choice=qwen3.6-27b-mtp ;;
  qwen38-27b) choice=qwen3.8-27b-hauhaucs-mtp ;;
  qwen36-35b) choice=qwen3.6-35b-a3b-mtp ;;
  "") show_usage >&2; exit 2 ;;
esac
[[ $# -eq 1 ]] || { echo "ERROR: provide exactly one MTP catalog ID." >&2; exit 2; }
[[ -x "$RUNNER" ]] || { echo "ERROR: MTP runner is not executable: $RUNNER" >&2; exit 1; }
[[ -x "$LLAMACPP" ]] || { echo "ERROR: set LLAMACPP to an executable llama-server." >&2; exit 1; }
for value in "$PORT" "$NUM_PREDICT" "$REPEATS" "$READY_TIMEOUT" "$INFER_TIMEOUT"; do
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: numeric comparison settings must be positive integers." >&2; exit 2; }
done
((PORT <= 65535)) || { echo "ERROR: PORT must be <= 65535." >&2; exit 2; }
for cmd in awk curl date grep jq journalctl kill pgrep rpm sed setsid sha256sum ss sudo tar; do
  command -v "$cmd" >/dev/null || { echo "ERROR: missing command: $cmd" >&2; exit 1; }
done

# Resolve before asking for runtime credentials so invalid IDs fail cheaply.
resolved="$("$MANAGER" path mtp "$choice" --source "$SOURCE_FILE")" || exit 1
IFS=$'\t' read -r GGUF DEFAULT_CTX DEFAULT_DRAFT <<< "$resolved"
[[ -s "$GGUF" ]] || {
  echo "ERROR: missing $GGUF." >&2
  echo "Fetch it first: sudo bc250-fetch-mtp $choice" >&2
  exit 1
}

sudo -v
STAMP="$(date +%Y%m%d-%H%M%S)"
RESULT_DIR="${RESULT_DIR:-$RESULT_BASE/bc250-mtp-${choice}-${STAMP}}"
mkdir -p "$RESULT_DIR"
RUN_START="$(date -Iseconds)"
printf '%s\n' "$PROMPT" > "$RESULT_DIR/prompt.txt"
printf 'id=%s\ngguf=%s\ncontext=%s\ndraft_n_max=%s\nubatch=%s\nrepeats=%s\nnum_predict=%s\nport=%s\nstarted=%s\n' \
  "$choice" "$GGUF" "${CTX:-$DEFAULT_CTX}" "${DRAFT_N_MAX:-$DEFAULT_DRAFT}" "${UBATCH:-default}" "$REPEATS" "$NUM_PREDICT" "$PORT" "$RUN_START" \
  > "$RESULT_DIR/run-info.txt"
rpm -q --qf '%{NAME} %{VERSION}-%{RELEASE} %{ARCH}\n' bc250-llm-server > "$RESULT_DIR/package.txt" 2>&1 || true
uname -a > "$RESULT_DIR/uname.txt"
rpm -q mesa-vulkan-drivers vulkan-loader > "$RESULT_DIR/graphics-packages.txt" 2>&1 || true
"$LLAMACPP" --version > "$RESULT_DIR/llamacpp-version.txt" 2>&1 || true
sudo "$MANAGER" status mtp "$choice" --include-disabled --source "$SOURCE_FILE" --verbose \
  > "$RESULT_DIR/model-status.txt" 2>&1

cleanup() {
  if [[ -n "$SAMPLER_PID" ]] && kill -0 "$SAMPLER_PID" 2>/dev/null; then
    kill "$SAMPLER_PID" 2>/dev/null || true
    wait "$SAMPLER_PID" 2>/dev/null || true
  fi
  if [[ -n "$ACTIVE_PGID" ]] && kill -0 "$ACTIVE_PGID" 2>/dev/null; then
    kill -TERM -- "-$ACTIVE_PGID" 2>/dev/null || true
    sleep 1
    kill -KILL -- "-$ACTIVE_PGID" 2>/dev/null || true
    wait "$ACTIVE_PGID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

resource_sampler() {
  local pgid="$1" output="$2"
  printf 'epoch\tmem_available_mib\tswap_used_mib\n' > "$output"
  while kill -0 "$pgid" 2>/dev/null; do
    awk -v now="$(date +%s.%N)" '
      /^MemAvailable:/ { mem=$2/1024 }
      /^SwapTotal:/ { total=$2/1024 }
      /^SwapFree:/ { free=$2/1024 }
      END { printf "%s\t%.1f\t%.1f\n", now, mem, total-free }
    ' /proc/meminfo >> "$output"
    sleep 0.2
  done
}

wait_ready() {
  local pgid="$1" i
  for ((i=0; i<READY_TIMEOUT; i++)); do
    kill -0 "$pgid" 2>/dev/null || return 1
    if curl -fsS --connect-timeout 1 --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

has_reserved_token_run() {
  grep -Eq '(<(unused|reserved)[_-]?[0-9]+>[[:space:]]*){8,}' <<< "$1"
}

stop_server() {
  local pgid="$1"
  if kill -0 "$pgid" 2>/dev/null; then
    kill -TERM -- "-$pgid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$pgid" 2>/dev/null || break
      sleep 0.25
    done
    if kill -0 "$pgid" 2>/dev/null; then
      kill -KILL -- "-$pgid" 2>/dev/null || true
    fi
  fi
  local rc=0
  wait "$pgid" 2>/dev/null || rc=$?
  ACTIVE_PGID=""
  return "$rc"
}

run_phase() {
  local phase="$1" mode_arg="$2"
  local phase_dir="$RESULT_DIR/$phase"
  mkdir -p "$phase_dir"
  local runner_args=("$choice")
  [[ -z "$mode_arg" ]] || runner_args=("$mode_arg" "$choice")

  echo "=== $phase: $choice ==="
  setsid env \
    MODEL_MANAGER="$MANAGER" SOURCE_FILE="$SOURCE_FILE" \
    LLAMACPP="$LLAMACPP" PORT="$PORT" \
    CTX="${CTX:-}" DRAFT_N_MAX="${DRAFT_N_MAX:-}" UBATCH="${UBATCH:-}" \
    MIN_MEM_AVAILABLE_MIB="${MIN_MEM_AVAILABLE_MIB:-2048}" \
    "$RUNNER" "${runner_args[@]}" > "$phase_dir/server.log" 2>&1 &
  local pgid=$!
  ACTIVE_PGID="$pgid"

  resource_sampler "$pgid" "$phase_dir/resources.tsv" &
  SAMPLER_PID=$!

  if ! wait_ready "$pgid"; then
    echo "ERROR: $phase server did not become ready." >&2
    stop_server "$pgid" || true
    kill "$SAMPLER_PID" 2>/dev/null || true
    wait "$SAMPLER_PID" 2>/dev/null || true
    SAMPLER_PID=""
    return 1
  fi

  printf 'run\tfinish\tusable\treserved_run\ttps\taccepted\tproposed\n' > "$phase_dir/inference.tsv"
  local phase_rc=0 i response finish text tps accepted proposed usable reserved
  for i in $(seq 1 "$REPEATS"); do
    response="$phase_dir/response-${i}.json"
    if ! jq -nc --arg prompt "$PROMPT" --argjson n "$NUM_PREDICT" \
      '{messages:[{role:"user",content:$prompt}],max_tokens:$n,temperature:0}' \
      | curl -fsS --connect-timeout 5 --max-time "$INFER_TIMEOUT" \
          "http://127.0.0.1:$PORT/v1/chat/completions" \
          -H 'Content-Type: application/json' --data-binary @- > "$response"; then
      echo "ERROR: $phase inference $i failed at HTTP/runtime layer." >&2
      phase_rc=1
      break
    fi
    finish="$(jq -r '.choices[0].finish_reason // empty' "$response")"
    text="$(jq -r '[.choices[0].message.content, .choices[0].message.reasoning_content, .choices[0].message.reasoning] | map(select(type == "string" and length > 0)) | join("\n")' "$response")"
    tps="$(jq -r '.timings.predicted_per_second // empty' "$response")"
    accepted="$(jq -r '.timings.draft_n_accepted // empty' "$response")"
    proposed="$(jq -r '.timings.draft_n // empty' "$response")"
    usable=0; reserved=0
    grep -Eq '[^[:space:]]' <<< "$text" && usable=1
    has_reserved_token_run "$text" && reserved=1
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$i" "$finish" "$usable" "$reserved" "$tps" "$accepted" "$proposed" >> "$phase_dir/inference.tsv"
    if [[ -z "$finish" || "$usable" != 1 || "$reserved" != 0 || -z "$tps" ]]; then
      echo "ERROR: $phase inference $i failed completion/timing integrity." >&2
      phase_rc=1
      break
    fi
    kill -0 "$pgid" 2>/dev/null || { echo "ERROR: $phase server died during inference." >&2; phase_rc=1; break; }
  done

  local alive_after=0
  kill -0 "$pgid" 2>/dev/null && alive_after=1
  local server_wait_rc=0
  stop_server "$pgid" || server_wait_rc=$?
  kill "$SAMPLER_PID" 2>/dev/null || true
  wait "$SAMPLER_PID" 2>/dev/null || true
  SAMPLER_PID=""

  local avg_tps min_mem start_swap max_swap swap_delta accepted_sum proposed_sum acceptance
  avg_tps="$(awk -F'\t' 'NR>1 && $5 ~ /^[0-9.]+$/ {sum+=$5;n++} END {if(n) printf "%.3f",sum/n}' "$phase_dir/inference.tsv")"
  min_mem="$(awk -F'\t' 'NR>1 {if(min=="" || $2<min) min=$2} END {if(min!="") printf "%.1f",min}' "$phase_dir/resources.tsv")"
  start_swap="$(awk -F'\t' 'NR==2 {print $3}' "$phase_dir/resources.tsv")"
  max_swap="$(awk -F'\t' 'NR>1 {if(max=="" || $3>max) max=$3} END {if(max!="") print max}' "$phase_dir/resources.tsv")"
  swap_delta="$(awk -v s="${start_swap:-0}" -v m="${max_swap:-0}" 'BEGIN {d=m-s; if(d<0)d=0; printf "%.1f",d}')"
  accepted_sum="$(awk -F'\t' 'NR>1 && $6 ~ /^[0-9]+$/ {s+=$6;n++} END {if(n) print s}' "$phase_dir/inference.tsv")"
  proposed_sum="$(awk -F'\t' 'NR>1 && $7 ~ /^[0-9]+$/ {s+=$7;n++} END {if(n) print s}' "$phase_dir/inference.tsv")"
  acceptance=""
  if [[ "$accepted_sum" =~ ^[0-9]+$ && "$proposed_sum" =~ ^[1-9][0-9]*$ ]]; then
    acceptance="$(awk -v a="$accepted_sum" -v p="$proposed_sum" 'BEGIN {printf "%.1f",a/p*100}')"
  fi

  printf 'phase\truns_requested\trows\tavg_tps\tmin_mem_mib\tswap_delta_mib\taccepted\tproposed\tacceptance_pct\talive_after\tserver_wait_rc\tphase_rc\n' > "$phase_dir/summary.tsv"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$phase" "$REPEATS" "$(( $(wc -l < "$phase_dir/inference.tsv") - 1 ))" "${avg_tps:-}" "${min_mem:-}" "$swap_delta" \
    "${accepted_sum:-}" "${proposed_sum:-}" "${acceptance:-}" "$alive_after" "$server_wait_rc" "$phase_rc" \
    >> "$phase_dir/summary.tsv"
  return "$phase_rc"
}

overall_rc=0
run_phase baseline --no-mtp || overall_rc=1
if (( overall_rc == 0 )); then
  sleep 2
  run_phase mtp "" || overall_rc=1
fi

# Kernel evidence is part of qualification. If it cannot be captured, fail closed
# rather than treating an unreadable journal as evidence of no GPU faults.
journal_rc=0
sudo journalctl -k --since "$RUN_START" --no-pager > "$RESULT_DIR/journal-kernel.log" 2>&1 || journal_rc=$?
if (( journal_rc != 0 )); then
  echo "ERROR: kernel journal capture failed (rc=$journal_rc); qualification evidence is incomplete." >&2
  overall_rc=1
fi
grep -Ei 'ring .*timeout|GPU reset|amdgpu.*(fault|timeout|reset)|VM fault|device lost|page fault' \
  "$RESULT_DIR/journal-kernel.log" > "$RESULT_DIR/journal-gpu-faults.log" || true

baseline_tps="$(awk -F'\t' 'NR==2 {print $4}' "$RESULT_DIR/baseline/summary.tsv" 2>/dev/null || true)"
mtp_tps="$(awk -F'\t' 'NR==2 {print $4}' "$RESULT_DIR/mtp/summary.tsv" 2>/dev/null || true)"
mtp_accepted="$(awk -F'\t' 'NR==2 {print $7}' "$RESULT_DIR/mtp/summary.tsv" 2>/dev/null || true)"
mtp_proposed="$(awk -F'\t' 'NR==2 {print $8}' "$RESULT_DIR/mtp/summary.tsv" 2>/dev/null || true)"
mtp_acceptance="$(awk -F'\t' 'NR==2 {print $9}' "$RESULT_DIR/mtp/summary.tsv" 2>/dev/null || true)"
speedup=""
if [[ "$baseline_tps" =~ ^[0-9.]+$ && "$mtp_tps" =~ ^[0-9.]+$ ]]; then
  speedup="$(awk -v b="$baseline_tps" -v m="$mtp_tps" 'BEGIN {if(b>0) printf "%.3f",m/b}')"
fi

if [[ ! "$mtp_proposed" =~ ^[1-9][0-9]*$ || ! "$mtp_accepted" =~ ^[0-9]+$ ]]; then
  echo "ERROR: MTP acceptance telemetry is missing; inference may be valid, but qualification evidence is incomplete." >&2
  (( overall_rc == 0 )) && overall_rc=3
fi
if [[ -s "$RESULT_DIR/journal-gpu-faults.log" ]]; then
  echo "ERROR: severe GPU/kernel fault evidence was recorded during the comparison." >&2
  overall_rc=1
fi
if pgrep -af '(^|/|[[:space:]])llama-server([[:space:]]|$)' > "$RESULT_DIR/leftover-llama-server.txt"; then
  echo "ERROR: llama-server remains after comparison cleanup." >&2
  overall_rc=1
else
  : > "$RESULT_DIR/leftover-llama-server.txt"
fi
if ss -H -ltn | awk -v suffix=":$PORT" '$4 ~ suffix "$" { found=1 } END { exit !found }'; then
  echo "ERROR: TCP port $PORT remains occupied after comparison cleanup." >&2
  overall_rc=1
fi

baseline_min_mem="$(awk -F'\t' 'NR==2 {print $5}' "$RESULT_DIR/baseline/summary.tsv" 2>/dev/null || true)"
mtp_min_mem="$(awk -F'\t' 'NR==2 {print $5}' "$RESULT_DIR/mtp/summary.tsv" 2>/dev/null || true)"
baseline_swap_delta="$(awk -F'\t' 'NR==2 {print $6}' "$RESULT_DIR/baseline/summary.tsv" 2>/dev/null || true)"
mtp_swap_delta="$(awk -F'\t' 'NR==2 {print $6}' "$RESULT_DIR/mtp/summary.tsv" 2>/dev/null || true)"
gpu_fault_lines="$(wc -l < "$RESULT_DIR/journal-gpu-faults.log")"
cat > "$RESULT_DIR/README-FIRST.txt" <<SUMMARY
BC-250 MTP same-model comparison
ID: $choice
Baseline avg tok/s: ${baseline_tps:-unavailable}
MTP avg tok/s: ${mtp_tps:-unavailable}
Speedup: ${speedup:-unavailable}x
MTP draft acceptance: ${mtp_accepted:-unavailable}/${mtp_proposed:-unavailable} (${mtp_acceptance:-unavailable}%)
Baseline min MemAvailable MiB: ${baseline_min_mem:-unavailable}
MTP min MemAvailable MiB: ${mtp_min_mem:-unavailable}
Baseline swap delta MiB: ${baseline_swap_delta:-unavailable}
MTP swap delta MiB: ${mtp_swap_delta:-unavailable}
GPU/kernel fault lines: $gpu_fault_lines
Exit status: $overall_rc
SUMMARY
cat "$RESULT_DIR/README-FIRST.txt"

TARBALL="${RESULT_DIR}.tar.gz"
tar -C "$(dirname "$RESULT_DIR")" -czf "$TARBALL" "$(basename "$RESULT_DIR")"
sha256sum "$TARBALL" | tee "$RESULT_DIR/tarball-sha256.txt"
echo "Results: $RESULT_DIR"
echo "Tarball: $TARBALL"
exit "$overall_rc"
