#!/usr/bin/env bash
# Ollama model benchmark v6.1
#
# Measures:
#   - cold model-switch and warm streaming chat latency (TTFC / TTFA)
#   - Ollama model-load, prompt-eval, generation, and total durations
#   - loaded model allocation from /api/ps plus host memory/swap headroom
#   - repeated decode throughput and a dedicated document-prefill test
#   - optional context-capacity curve with truncation warnings
#   - optional sustained tok/s drift / throttle test
#   - optional embedding cold/warm batch throughput via /api/embed
#
# Dependencies: bash, jq, curl, awk, GNU date.
# Fedora: sudo dnf install -y jq curl gawk coreutils
#
# Profiles:
#   - moderate (default): representative office-model comparison
#   - conservative: shorter, lower-context smoke/comparison pass
#
# Notes:
#   - The streaming chat test calls Ollama directly. It approximates OpenWebUI's
#     backend experience but does not include OpenWebUI middleware, RAG, tools,
#     web search, database access, or browser rendering overhead.
#   - Set THINK_MODE=false|true|low|medium|high|max. GPT-OSS normally uses a
#     reasoning level and may not fully disable its reasoning trace.
#   - Set LATENCY_REPEATS=0 to disable warm latency repeats. The cold test still
#     runs unless RUN_LATENCY=0 is set.
set -uo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF_HELP'
Usage: bc250-benchmark

Interactive runtime benchmark for registered Ollama models.
BENCH_PROFILE=moderate is the package standard; use BENCH_PROFILE=conservative
for a faster, lower-context pass. Set INCLUDE_EMBEDDINGS=1 to benchmark embedding
models through /api/embed instead of generation endpoints. OCR models are intentionally
excluded; compare them with the same page corpus through bc250-ocr.

Important overrides: OLLAMA_URL, THINK_MODE, RUN_LATENCY, REPEATS, CTX_POINTS,
NUM_PREDICT_SHORT, NUM_PREDICT_PREFILL, NUM_PREDICT_CONTEXT, NUM_PREDICT_LONG.
EOF_HELP
  exit 0
fi

QUESTION="Write a structured office memo that summarizes the relevant policy points, dates, responsibilities, and next actions. Use around 500 words."
PROMPT_SHORT="$QUESTION"

CHAT_SYSTEM_PROMPT="${CHAT_SYSTEM_PROMPT:-You are a concise, helpful assistant. Answer directly.}"
CHAT_PROMPT="${CHAT_PROMPT:-In one concise paragraph, summarize a routine office policy update and state the next action clearly.}"

EMBED_INPUT_JSON='["Kündigungsfrist und Zahlungsbedingungen im Mietvertrag","Délai de résiliation et conditions de paiement du contrat","Meeting minutes approving the annual maintenance budget","Reglement über die Benutzung gemeinsamer Räume","Règlement concernant l’utilisation des locaux communs","Invoice reference 2026-0317 and due date 30 September 2026"]'

BENCH_PROFILE="${BENCH_PROFILE:-moderate}"
case "${BENCH_PROFILE,,}" in
  moderate)
    : "${NUM_PREDICT_SHORT:=384}"
    : "${NUM_PREDICT_PREFILL:=32}"
    : "${NUM_PREDICT_CONTEXT:=128}"
    : "${NUM_PREDICT_LONG:=3072}"
    : "${NUM_PREDICT_LATENCY:=96}"
    : "${REPEATS:=3}"
    : "${LATENCY_REPEATS:=2}"
    : "${EMBED_REPEATS:=2}"
    : "${PREFILL_SENTENCES:=220}"
    : "${CTX_POINTS:=44 176 352 704}"
    DEFAULT_CTX="y"
    ;;
  conservative)
    : "${NUM_PREDICT_SHORT:=256}"
    : "${NUM_PREDICT_PREFILL:=24}"
    : "${NUM_PREDICT_CONTEXT:=96}"
    : "${NUM_PREDICT_LONG:=2048}"
    : "${NUM_PREDICT_LATENCY:=64}"
    : "${REPEATS:=2}"
    : "${LATENCY_REPEATS:=1}"
    : "${EMBED_REPEATS:=1}"
    : "${PREFILL_SENTENCES:=110}"
    : "${CTX_POINTS:=22 88 220}"
    DEFAULT_CTX="n"
    ;;
  *)
    echo "ERROR: BENCH_PROFILE must be moderate or conservative" >&2
    exit 2
    ;;
esac

RUN_LATENCY="${RUN_LATENCY:-1}"
THROTTLE_WINDOWS="${THROTTLE_WINDOWS:-3}"
OLLAMA="${OLLAMA_URL:-${OLLAMA_HOST:-http://localhost:11434}}"
MAX_RETRIES="${MAX_RETRIES:-3}"
CONNECT_TIMEOUT="${CONNECT_TIMEOUT:-10}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-900}"
UNLOAD_TIMEOUT="${UNLOAD_TIMEOUT:-30}"
UNLOAD_POLL_INTERVAL="${UNLOAD_POLL_INTERVAL:-0.25}"
OVERHEAD_WARN_S="${OVERHEAD_WARN_S:-2.0}"
KEEP_ALIVE="${KEEP_ALIVE:-30m}"
COLD_UNLOAD_WAIT="${COLD_UNLOAD_WAIT:-2}"
THINK_MODE="${THINK_MODE:-false}"
INCLUDE_EMBEDDINGS="${INCLUDE_EMBEDDINGS:-${ALLOW_EMBED:-0}}"
EARLY_EOS_FRACTION="${EARLY_EOS_FRACTION:-0.90}"
STANDARD_OLLAMA_VERSION="${STANDARD_OLLAMA_VERSION:-0.32.15}"

# Approximate prompt sizes use ~23 tokens per synthetic office sentence.
# Moderate: ~1k, 4k, 8k, 16k. Conservative: ~0.5k, 2k, 5k.

command -v jq   >/dev/null || { echo "ERROR: jq missing -> sudo dnf install -y jq"; exit 1; }
command -v curl >/dev/null || { echo "ERROR: curl missing"; exit 1; }
command -v awk  >/dev/null || { echo "ERROR: awk missing"; exit 1; }

for numeric_var in NUM_PREDICT_SHORT NUM_PREDICT_PREFILL NUM_PREDICT_CONTEXT NUM_PREDICT_LONG NUM_PREDICT_LATENCY REPEATS LATENCY_REPEATS EMBED_REPEATS PREFILL_SENTENCES THROTTLE_WINDOWS MAX_RETRIES; do
  value="${!numeric_var}"
  [[ "$value" =~ ^[0-9]+$ ]] || { echo "ERROR: $numeric_var must be a non-negative integer (got '$value')"; exit 1; }
done
(( THROTTLE_WINDOWS > 0 )) || { echo "ERROR: THROTTLE_WINDOWS must be greater than zero"; exit 1; }
(( MAX_RETRIES > 0 )) || { echo "ERROR: MAX_RETRIES must be greater than zero"; exit 1; }
(( NUM_PREDICT_LONG >= THROTTLE_WINDOWS )) || {
  echo "ERROR: NUM_PREDICT_LONG must be at least THROTTLE_WINDOWS"
  exit 1
}
for point in $CTX_POINTS; do
  [[ "$point" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: every CTX_POINTS entry must be a positive integer (got '$point')"
    exit 1
  }
done
awk -v fraction="$EARLY_EOS_FRACTION" 'BEGIN { exit !(fraction > 0 && fraction <= 1) }' || {
  echo "ERROR: EARLY_EOS_FRACTION must be greater than 0 and at most 1"
  exit 1
}

for duration_var in CONNECT_TIMEOUT REQUEST_TIMEOUT UNLOAD_POLL_INTERVAL OVERHEAD_WARN_S COLD_UNLOAD_WAIT; do
  value="${!duration_var}"
  [[ "$value" =~ ^[0-9]+([.][0-9]+)?$ ]] || {
    echo "ERROR: $duration_var must be a non-negative number (got '$value')"
    exit 1
  }
done

[[ "$UNLOAD_TIMEOUT" =~ ^[0-9]+$ ]] || {
  echo "ERROR: UNLOAD_TIMEOUT must be a non-negative integer (got '$UNLOAD_TIMEOUT')"
  exit 1
}

for toggle in RUN_LATENCY INCLUDE_EMBEDDINGS; do
  value="${!toggle}"
  [[ "$value" == "0" || "$value" == "1" ]] || {
    echo "ERROR: $toggle must be 0 or 1"
    exit 1
  }
done

CURL_TIMEOUT_ARGS=(--connect-timeout "$CONNECT_TIMEOUT")
if awk -v timeout="$REQUEST_TIMEOUT" 'BEGIN { exit !(timeout > 0) }'; then
  CURL_TIMEOUT_ARGS+=(--max-time "$REQUEST_TIMEOUT")
fi

case "${THINK_MODE,,}" in
  true|false)
    THINK_JSON="${THINK_MODE,,}"
    ;;
  low|medium|high|max)
    THINK_JSON="$(jq -nc --arg value "${THINK_MODE,,}" '$value')"
    ;;
  *)
    echo "ERROR: THINK_MODE must be false, true, low, medium, high, or max"
    exit 1
    ;;
esac

# Prepend a nonce so Ollama/llama.cpp cannot reuse a KV-prefix cache entry.
make_unique_prompt() {
  printf '[reqid %s_%s] %s' "$(date +%s%N)" "$RANDOM" "$1"
}

# Build synthetic office-document text for prefill/context-pressure tests.
make_filler() {
  local n="$1" i out=""
  for ((i=1; i<=n; i++)); do
    out+="Office document paragraph sentence $i records a dated policy item, reference number, responsible department, payment term, and procedural note for later retrieval. "
  done
  printf '%s' "$out"
}

PROMPT_LONG="$(make_filler "$PREFILL_SENTENCES") Given all of the above office-document context, $QUESTION"

# Short readable label from a full model name.
short() {
  local n="$1"
  n="${n##*/}"
  n="${n%:*}"
  n="${n%-GGUF}"; n="${n%-gguf}"
  n="${n%-Instruct}"; n="${n%-instruct}"
  printf '%s' "$n"
}

calc() {
  awk -v numerator="$1" -v denominator="$2" \
    'BEGIN { if (denominator > 0) printf "%.2f", numerator / denominator; else printf "0.00" }'
}

ns_diff_s() {
  awk -v start="$1" -v finish="$2" \
    'BEGIN { if (finish >= start) printf "%.3f", (finish-start)/1e9; else printf "0.000" }'
}

mean_stdev() {
  awk '{
    n=NF; sum=0
    for (i=1; i<=n; i++) sum += $i
    mean=sum/n
    sq=0
    for (i=1; i<=n; i++) sq += ($i-mean)^2
    sd=(n>1) ? sqrt(sq/(n-1)) : 0
    printf "%.2f %.2f", mean, sd
  }' <<< "$1"
}

warn_early_eos() {
  local ec="$1" np="$2"
  awk -v ec="$ec" -v np="$np" -v f="$EARLY_EOS_FRACTION" \
    'BEGIN { if (ec < np*f) printf "    WARNING: early EOS — generated only %d/%d tokens; tok/s may not be regime-comparable\n", ec, np }'
}

calc_nonnegative_remainder() {
  # Prints max(total - part1 - part2 - part3, 0).
  awk -v total="$1" -v p1="$2" -v p2="$3" -v p3="$4" '
    BEGIN {
      value = total - p1 - p2 - p3
      if (value < 0 && value > -0.01) value = 0
      if (value < 0) value = 0
      printf "%.6f", value
    }
  '
}

warn_hidden_overhead() {
  local overhead="$1"
  awk -v overhead="$overhead" -v threshold="$OVERHEAD_WARN_S" '
    BEGIN {
      if (overhead >= threshold)
        printf "    WARNING: %.3fs of Ollama total time is outside load, prompt-eval, and generation phases\n", overhead
    }
  '
}

format_optional_seconds() {
  local value="$1"
  if [[ "$value" == "NA" || -z "$value" ]]; then
    printf 'n/a'
  else
    printf '%.3fs' "$value"
  fi
}

runtime_state() {
  local model="$1" base ps row
  base="${model%:latest}"
  resident_size_bytes=""
  resident_vram_bytes=""
  allocated_context=""
  if ps="$(curl -sS "${CURL_TIMEOUT_ARGS[@]}" "$OLLAMA/api/ps" 2>/dev/null)"; then
    row="$(jq -r --arg base "$base" '
      [(.models // [])[] | select(((.name // .model // "") | sub(":latest$"; "")) == $base)]
      | first // empty
      | [(.size // ""), (.size_vram // ""), (.context_length // "")] | @tsv
    ' <<< "$ps" 2>/dev/null || true)"
    [[ -z "$row" ]] || IFS=$'\t' read -r resident_size_bytes resident_vram_bytes allocated_context <<< "$row"
  fi
  read -r mem_available_mib swap_used_mib < <(awk '
    /MemAvailable:/ {available=$2}
    /SwapTotal:/ {total=$2}
    /SwapFree:/ {free=$2}
    END {printf "%.0f %.0f\n", available/1024, (total-free)/1024}
  ' /proc/meminfo)
}

build_generate_payload() {
  local model="$1" prompt="$2" np="$3"
  jq -nc \
    --arg model "$model" \
    --arg prompt "$prompt" \
    --argjson np "$np" \
    --argjson think "$THINK_JSON" \
    --arg keep_alive "$KEEP_ALIVE" \
    '{
      model: $model,
      prompt: $prompt,
      stream: false,
      think: $think,
      keep_alive: $keep_alive,
      options: {temperature: 0, num_predict: $np}
    }'
}

build_chat_payload() {
  local model="$1" prompt="$2" np="$3"
  jq -nc \
    --arg model "$model" \
    --arg system "$CHAT_SYSTEM_PROMPT" \
    --arg prompt "$prompt" \
    --argjson np "$np" \
    --argjson think "$THINK_JSON" \
    --arg keep_alive "$KEEP_ALIVE" \
    '{
      model: $model,
      messages: (
        if $system == "" then
          [{role: "user", content: $prompt}]
        else
          [
            {role: "system", content: $system},
            {role: "user", content: $prompt}
          ]
        end
      ),
      stream: true,
      think: $think,
      keep_alive: $keep_alive,
      options: {temperature: 0, num_predict: $np}
    }'
}

# CSV columns:
#  1 timestamp
#  2 model
#  3 label
#  4 test
#  5 run
#  6 status
#  7 eval_count
#  8 eval_duration_s
#  9 tokens_per_second      (decode for chat; input throughput for embed rows)
# 10 prompt_eval_count
# 11 prompt_eval_duration_s
# 12 prompt_tokens_per_second
# 13 total_duration_s       (reported by Ollama)
# 14 load_duration_s        (reported by Ollama)
# 15 wall_duration_s        (measured externally around curl)
# 16 time_to_first_content_s
# 17 time_to_first_answer_s
# 18 done_reason
# 19 server_overhead_s
# 20 client_overhead_s
# 21 resident_size_bytes    (/api/ps after the request)
# 22 resident_vram_bytes    (/api/ps; indicative on unified-memory Vulkan)
# 23 allocated_context      (/api/ps)
# 24 mem_available_mib      (/proc/meminfo after the request)
# 25 swap_used_mib          (/proc/meminfo after the request)
# 26 batch_items            (embedding rows only)
# 27 output_dimensions      (embedding rows only)
# 28 embedding_process_duration_s (estimated as total_duration - load_duration)
write_result() {
  local model="$1" label="$2" test="$3" run="$4" status="$5"
  local ec="${6:-}" eds="${7:-}" tps="${8:-}" pec="${9:-}" peds="${10:-}"
  local ptps="${11:-}" tds="${12:-}" lds="${13:-}" wall="${14:-}"
  local ttfc="${15:-}" ttfa="${16:-}" done_reason="${17:-}"
  local server_overhead="${18:-}" client_overhead="${19:-}"
  local resident_size="${20:-}" resident_vram="${21:-}" context="${22:-}"
  local mem_available="${23:-}" swap_used="${24:-}" batch_items="${25:-}" dimensions="${26:-}"
  local embedding_process="${27:-}"

  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$(date --iso-8601=seconds)" "$model" "$label" "$test" "$run" "$status" \
    "$ec" "$eds" "$tps" "$pec" "$peds" "$ptps" "$tds" "$lds" "$wall" \
    "$ttfc" "$ttfa" "$done_reason" "$server_overhead" "$client_overhead" \
    "$resident_size" "$resident_vram" "$context" "$mem_available" "$swap_used" \
    "$batch_items" "$dimensions" "$embedding_process" >> "$RESULTS"
}

write_failed() {
  write_result "$1" "$2" "$3" "$4" "FAILED" "" "" "" "" "" "" "" "" "" "" "" "request_failed"
}

unload_model() {
  local payload
  if command -v ollama >/dev/null 2>&1; then
    OLLAMA_HOST="$OLLAMA" ollama stop "$1" >/dev/null 2>&1 && return 0
  fi
  payload="$(jq -nc --arg model "$1" '{model: $model, keep_alive: 0}')"
  curl -sS "${CURL_TIMEOUT_ARGS[@]}" \
    -H 'Content-Type: application/json' \
    "$OLLAMA/api/generate" -d "$payload" >/dev/null 2>&1 || true
}

wait_until_unloaded() {
  local model="$1" start_seconds="$SECONDS" ps_json loaded

  while (( SECONDS - start_seconds < UNLOAD_TIMEOUT )); do
    if ! ps_json="$(curl -sS "${CURL_TIMEOUT_ARGS[@]}" "$OLLAMA/api/ps" 2>/dev/null)"; then
      # Older/custom servers may not expose /api/ps. Fall back to the configured
      # fixed delay rather than failing the entire benchmark.
      sleep "$COLD_UNLOAD_WAIT"
      return 0
    fi

    loaded="$(jq -r --arg model "$model" '
      [(.models // [])[] | select((.name // .model // "") == $model)] | length
    ' <<< "$ps_json" 2>/dev/null || printf '0')"

    [[ "$loaded" == "0" ]] && return 0
    sleep "$UNLOAD_POLL_INTERVAL"
  done

  echo "    WARNING: model still appears in /api/ps after ${UNLOAD_TIMEOUT}s; cold timing may be partially warm" >&2
  return 1
}

prepare_cold_model() {
  local model="$1"
  unload_model "$model"
  wait_until_unloaded "$model" || true
}

# Non-streaming generate request.
# Output TSV:
#   eval_count eval_s prompt_count prompt_s total_s load_s wall_s TTFC TTFA done_reason
run_once() {
  local model="$1" prompt="$2" np="$3"
  local payload json metrics start_ns finish_ns wall_s attempt
  payload="$(build_generate_payload "$model" "$prompt" "$np")"

  for ((attempt=1; attempt<=MAX_RETRIES; attempt++)); do
    start_ns="$(date +%s%N)"
    if json="$(curl -sS "${CURL_TIMEOUT_ARGS[@]}" \
      -H 'Content-Type: application/json' \
      "$OLLAMA/api/generate" -d "$payload" 2>/dev/null)"; then
      finish_ns="$(date +%s%N)"
      wall_s="$(ns_diff_s "$start_ns" "$finish_ns")"

      if [[ -n "$json" ]] && ! jq -e '.error' >/dev/null 2>&1 <<< "$json"; then
        metrics="$(jq -r '[
          (.eval_count // 0),
          ((.eval_duration // 0)/1e9),
          (.prompt_eval_count // 0),
          ((.prompt_eval_duration // 0)/1e9),
          ((.total_duration // 0)/1e9),
          ((.load_duration // 0)/1e9),
          (.done_reason // "unknown")
        ] | @tsv' <<< "$json" 2>/dev/null || true)"

        if [[ -n "$metrics" ]]; then
          printf '%s\t%s\tNA\tNA\n' "$metrics" "$wall_s" | \
            awk -F '\t' 'BEGIN{OFS="\t"} {print $1,$2,$3,$4,$5,$6,$8,$9,$10,$7}'
          return 0
        fi
      fi
    fi
    sleep 3
  done
  return 1
}

# Streaming /api/chat request.
# TTFC is first reasoning OR answer text. TTFA is first actual answer text.
# Output TSV has the same field order as run_once().
run_streaming_chat_once() {
  local model="$1" prompt="$2" np="$3" force_cold="${4:-0}"
  local payload attempt tmp_dir tmp_stream tmp_err stream_fifo
  local start_ns finish_ns now_ns first_content_ns first_answer_ns
  local line has_content has_answer is_done line_error flags
  local stream_fd stream_pid curl_rc
  local final_json metrics wall_s ttfc_s ttfa_s error_text

  payload="$(build_chat_payload "$model" "$prompt" "$np")"

  for ((attempt=1; attempt<=MAX_RETRIES; attempt++)); do
    # A retry of a cold-start measurement must be cold again; otherwise the
    # failed first request may have silently loaded the model and biased TTFA.
    if (( attempt > 1 )) && [[ "$force_cold" == "1" ]]; then
      prepare_cold_model "$model"
    fi

    tmp_dir="$(mktemp -d)" || return 1
    tmp_stream="$tmp_dir/stream.ndjson"
    tmp_err="$tmp_dir/curl.err"
    stream_fifo="$tmp_dir/stream.fifo"
    mkfifo "$stream_fifo" || { rm -rf "$tmp_dir"; return 1; }

    start_ns="$(date +%s%N)"
    first_content_ns=0
    first_answer_ns=0
    curl_rc=0

    # A normal FIFO is used instead of Bash coproc FDs. Bash may automatically
    # close a coproc FD as soon as the child exits, which caused a harmless but
    # noisy "Bad file descriptor" on the loop's final read.
    curl -sS -N "${CURL_TIMEOUT_ARGS[@]}" \
      -H 'Content-Type: application/json' \
      "$OLLAMA/api/chat" -d "$payload" >"$stream_fifo" 2>"$tmp_err" &
    stream_pid=$!
    exec {stream_fd}<"$stream_fifo"

    final_json=""
    error_text=""
    while IFS= read -r line <&"$stream_fd"; do
      [[ -z "$line" ]] && continue
      printf '%s\n' "$line" >> "$tmp_stream"

      flags="$(jq -r '[
        ((((.message.content // .response // "") | length) > 0)
          or (((.message.thinking // .thinking // "") | length) > 0)),
        (((.message.content // .response // "") | length) > 0),
        (.done == true),
        (.error // "")
      ] | @tsv' <<< "$line" 2>/dev/null || true)"
      [[ -z "$flags" ]] && continue
      IFS=$'\t' read -r has_content has_answer is_done line_error <<< "$flags"

      if { (( first_content_ns == 0 )) && [[ "$has_content" == "true" ]]; } ||
         { (( first_answer_ns == 0 )) && [[ "$has_answer" == "true" ]]; }; then
        now_ns="$(date +%s%N)"
        (( first_content_ns == 0 )) && [[ "$has_content" == "true" ]] && first_content_ns="$now_ns"
        (( first_answer_ns == 0 )) && [[ "$has_answer" == "true" ]] && first_answer_ns="$now_ns"
      fi

      [[ "$is_done" == "true" ]] && final_json="$line"
      [[ -n "$line_error" ]] && error_text="$line_error"
    done
    exec {stream_fd}<&-

    wait "$stream_pid" || curl_rc=$?
    finish_ns="$(date +%s%N)"
    wall_s="$(ns_diff_s "$start_ns" "$finish_ns")"

    if (( first_content_ns > 0 )); then
      ttfc_s="$(ns_diff_s "$start_ns" "$first_content_ns")"
    else
      ttfc_s="NA"
    fi

    if (( first_answer_ns > 0 )); then
      ttfa_s="$(ns_diff_s "$start_ns" "$first_answer_ns")"
    else
      ttfa_s="NA"
    fi

    # Fallback for unusual servers that split or format the final line in a way
    # the incremental parser did not recognize.
    if [[ -z "$final_json" && -s "$tmp_stream" ]]; then
      final_json="$(jq -cs 'map(select(.done == true)) | last // empty' "$tmp_stream" 2>/dev/null || true)"
    fi
    if [[ -z "$error_text" && -s "$tmp_stream" ]]; then
      error_text="$(jq -sr 'map(select(.error != null)) | last.error // empty' "$tmp_stream" 2>/dev/null || true)"
    fi

    if (( curl_rc == 0 )) && [[ -z "$error_text" && -n "$final_json" ]]; then
      metrics="$(jq -r '[
        (.eval_count // 0),
        ((.eval_duration // 0)/1e9),
        (.prompt_eval_count // 0),
        ((.prompt_eval_duration // 0)/1e9),
        ((.total_duration // 0)/1e9),
        ((.load_duration // 0)/1e9),
        (.done_reason // "unknown")
      ] | @tsv' <<< "$final_json" 2>/dev/null || true)"

      rm -rf "$tmp_dir"
      if [[ -n "$metrics" ]]; then
        printf '%s\t%s\t%s\t%s\n' "$metrics" "$wall_s" "$ttfc_s" "$ttfa_s" | \
          awk -F '\t' 'BEGIN{OFS="\t"} {print $1,$2,$3,$4,$5,$6,$8,$9,$10,$7}'
        return 0
      fi
    else
      if [[ -n "$error_text" ]]; then
        echo "    streaming error: $error_text" >&2
      elif [[ -s "$tmp_err" ]]; then
        echo "    curl error: $(tr '\n' ' ' < "$tmp_err")" >&2
      fi
    fi

    rm -rf "$tmp_dir"
    sleep 3
  done
  return 1
}


is_embedding_model() {
  local model="$1" show
  [[ "$model" == embed-* ]] && return 0
  show="$(curl -sS "${CURL_TIMEOUT_ARGS[@]}" "$OLLAMA/api/show" \
    -H 'Content-Type: application/json' \
    -d "$(jq -nc --arg model "$model" '{model: $model}')" 2>/dev/null || true)"
  jq -e '(.capabilities // []) | index("embedding") != null' <<< "$show" >/dev/null 2>&1
}

run_embedding_once() {
  local model="$1" label="$2" test="$3" run="$4"
  local payload json start_ns finish_ns wall_s prompt_count total_s load_s process_s
  local batch_items dimensions embed_tps client_overhead_s attempt
  payload="$(jq -nc --arg model "$model" --argjson input "$EMBED_INPUT_JSON" --arg keep_alive "$KEEP_ALIVE" \
    '{model: $model, input: $input, truncate: false, keep_alive: $keep_alive}')"

  for ((attempt=1; attempt<=MAX_RETRIES; attempt++)); do
    start_ns="$(date +%s%N)"
    if json="$(curl -sS "${CURL_TIMEOUT_ARGS[@]}" \
      -H 'Content-Type: application/json' "$OLLAMA/api/embed" -d "$payload" 2>/dev/null)"; then
      finish_ns="$(date +%s%N)"
      wall_s="$(ns_diff_s "$start_ns" "$finish_ns")"
      if [[ -n "$json" ]] && ! jq -e '.error' >/dev/null 2>&1 <<< "$json"; then
        read -r prompt_count total_s load_s batch_items dimensions < <(jq -r '[
          (.prompt_eval_count // 0),
          ((.total_duration // 0)/1e9),
          ((.load_duration // 0)/1e9),
          ((.embeddings // []) | length),
          (((.embeddings // [])[0] // []) | length)
        ] | @tsv' <<< "$json")
        process_s="$(calc_nonnegative_remainder "$total_s" "$load_s" 0 0)"
        embed_tps="$(calc "$prompt_count" "$process_s")"
        client_overhead_s="$(calc_nonnegative_remainder "$wall_s" "$total_s" 0 0)"
        runtime_state "$model"
        write_result "$model" "$label" "$test" "$run" "ok" \
          "" "" "$embed_tps" "$prompt_count" "" "" \
          "$total_s" "$load_s" "$wall_s" "NA" "NA" "embedding" "" "$client_overhead_s" \
          "$resident_size_bytes" "$resident_vram_bytes" "$allocated_context" \
          "$mem_available_mib" "$swap_used_mib" "$batch_items" "$dimensions" "$process_s"
        printf '    wall %.3fs | load %.3fs | batch=%s | dim=%s | input=%s tok/s\n' \
          "$wall_s" "$load_s" "$batch_items" "$dimensions" "$embed_tps"
        return 0
      fi
    fi
    sleep 3
  done
  write_failed "$model" "$label" "$test" "$run"
  return 1
}

run_embedding_tests() {
  local model="$1" label="$2" r
  echo "  [embedding-cold] unload -> multilingual office batch via /api/embed..."
  prepare_cold_model "$model"
  run_embedding_once "$model" "$label" "embed_cold" 1 || echo "    cold embedding batch failed"
  for ((r=1; r<=EMBED_REPEATS; r++)); do
    echo "  [embedding-warm] run $r/$EMBED_REPEATS..."
    run_embedding_once "$model" "$label" "embed_warm" "$r" || echo "    warm embedding batch failed"
  done
}

parse_metrics() {
  local row="$1"
  IFS=$'\t' read -r ec eds pec peds tds lds wall_s ttfc_s ttfa_s done_reason <<< "$row"
}

record_success() {
  local model="$1" label="$2" test="$3" run="$4" row="$5"
  parse_metrics "$row"
  tps="$(calc "$ec" "$eds")"
  ptps="$(calc "$pec" "$peds")"
  server_overhead_s="$(calc_nonnegative_remainder "$tds" "$lds" "$peds" "$eds")"
  client_overhead_s="$(calc_nonnegative_remainder "$wall_s" "$tds" 0 0)"
  runtime_state "$model"
  write_result "$model" "$label" "$test" "$run" "ok" \
    "$ec" "$eds" "$tps" "$pec" "$peds" "$ptps" "$tds" "$lds" "$wall_s" \
    "$ttfc_s" "$ttfa_s" "$done_reason" "$server_overhead_s" "$client_overhead_s" \
    "$resident_size_bytes" "$resident_vram_bytes" "$allocated_context" \
    "$mem_available_mib" "$swap_used_mib"
}

run_latency_tests() {
  local model="$1" label="$2" row r
  local cold_prompt warm_prompt

  echo "  [cold-chat] unload -> stream $NUM_PREDICT_LATENCY tokens via /api/chat..."
  prepare_cold_model "$model"
  cold_prompt="$(make_unique_prompt "$CHAT_PROMPT")"

  if row="$(run_streaming_chat_once "$model" "$cold_prompt" "$NUM_PREDICT_LATENCY" 1)"; then
    record_success "$model" "$label" "cold_chat" 1 "$row"
    printf '    wall %.3fs | load %.3fs | TTFC %s | TTFA %s | gen %s tok/s\n' \
      "$wall_s" "$lds" "$(format_optional_seconds "$ttfc_s")" \
      "$(format_optional_seconds "$ttfa_s")" "$tps"
    warn_hidden_overhead "$server_overhead_s"
  else
    write_failed "$model" "$label" "cold_chat" 1
    echo "    cold streaming chat failed"
  fi

  for ((r=1; r<=LATENCY_REPEATS; r++)); do
    echo "  [warm-chat] run $r/$LATENCY_REPEATS..."
    warm_prompt="$(make_unique_prompt "$CHAT_PROMPT")"
    if row="$(run_streaming_chat_once "$model" "$warm_prompt" "$NUM_PREDICT_LATENCY")"; then
      record_success "$model" "$label" "warm_chat" "$r" "$row"
      printf '    wall %.3fs | load %.3fs | TTFC %s | TTFA %s | gen %s tok/s\n' \
        "$wall_s" "$lds" "$(format_optional_seconds "$ttfc_s")" \
        "$(format_optional_seconds "$ttfa_s")" "$tps"
      warn_hidden_overhead "$server_overhead_s"
    else
      write_failed "$model" "$label" "warm_chat" "$r"
      echo "    warm streaming chat failed"
    fi
  done
}

run_throttle_test() {
  local model="$1" base_prompt="$2" np="$3" label="$4"
  local window_tokens=$(( np / THROTTLE_WINDOWS ))
  local first_tps="" last_tps="" w row nonced_prompt drop_pct

  for ((w=1; w<=THROTTLE_WINDOWS; w++)); do
    echo "    [throttle-test] window $w/$THROTTLE_WINDOWS (${window_tokens} tok)..."
    nonced_prompt="$(make_unique_prompt "$base_prompt")"
    if ! row="$(run_once "$model" "$nonced_prompt" "$window_tokens")"; then
      echo "    [throttle-test] window $w failed"
      write_failed "$model" "$label" "throttle_w${w}" 1
      continue
    fi

    record_success "$model" "$label" "throttle_w${w}" 1 "$row"
    [[ -z "$first_tps" ]] && first_tps="$tps"
    last_tps="$tps"
    printf '      wall %.2fs | total %.2fs | tok/s=%s\n' "$wall_s" "$tds" "$tps"
    warn_hidden_overhead "$server_overhead_s"
  done

  if [[ -n "$first_tps" && -n "$last_tps" ]]; then
    drop_pct="$(awk -v first="$first_tps" -v last="$last_tps" \
      'BEGIN { if (first>0) printf "%.1f", ((first-last)/first)*100; else print "0.0" }')"
    printf '    first_window=%s tok/s  last_window=%s tok/s  drop=%s%%\n' \
      "$first_tps" "$last_tps" "$drop_pct"
  fi
}

run_ctx_curve() {
  local model="$1" label="$2" n prompt row previous_pec=""
  for n in $CTX_POINTS; do
    echo "  [ctx-curve] ~$((n * 23)) prompt tokens ($n filler sentences)..."
    prompt="$(make_unique_prompt "$(make_filler "$n") Given all of the above context, $QUESTION")"

    if ! row="$(run_once "$model" "$prompt" "$NUM_PREDICT_CONTEXT")"; then
      write_failed "$model" "$label" "ctx_${n}" 1
      echo "    failed"
      continue
    fi

    record_success "$model" "$label" "ctx_${n}" 1 "$row"
    printf '    wall %.2fs | total %.2fs | load %.3fs | gen %s tok/s | prompt %s tok/s | %s prompt tokens\n' \
      "$wall_s" "$tds" "$lds" "$tps" "$ptps" "$pec"
    warn_hidden_overhead "$server_overhead_s"
    warn_early_eos "$ec" "$NUM_PREDICT_CONTEXT"
    if [[ -n "$previous_pec" ]] && (( pec <= previous_pec )); then
      echo "    WARNING: prompt_eval_count stopped growing ($previous_pec -> $pec); likely silent context truncation" >&2
    fi
    if [[ "$allocated_context" =~ ^[0-9]+$ ]] && (( pec + NUM_PREDICT_CONTEXT >= allocated_context )); then
      echo "    NOTE: evaluated prompt plus requested answer reaches the allocated context ($allocated_context); treat this point as a capacity edge." >&2
    fi
    previous_pec="$pec"
  done
}

# --- Discover models ---
TAGS="$(curl -sS "${CURL_TIMEOUT_ARGS[@]}" "$OLLAMA/api/tags" 2>/dev/null || true)"
if [[ "$INCLUDE_EMBEDDINGS" == "1" ]]; then
  mapfile -t ALL < <(printf '%s' "$TAGS" | jq -r '.models[].name' 2>/dev/null | grep -vi 'ocr')
else
  mapfile -t ALL < <(printf '%s' "$TAGS" | jq -r '.models[].name' 2>/dev/null | grep -viE 'embed|ocr')
fi
[[ ${#ALL[@]} -eq 0 ]] && { echo "ERROR: no models from $OLLAMA/api/tags (is Ollama up?)"; exit 1; }

echo "Available models:"
for i in "${!ALL[@]}"; do printf '  %2d) %s\n' "$i" "${ALL[$i]}"; done
read -rp "Indices (e.g. 0,2-4) or Enter for all: " SEL

MODELS=()
if [[ -z "${SEL// }" ]]; then
  MODELS=("${ALL[@]}")
else
  IFS=',' read -ra parts <<< "$SEL"
  for p in "${parts[@]}"; do
    p="${p// }"
    if [[ "$p" =~ ^([0-9]+)-([0-9]+)$ ]]; then
      for ((i=10#${BASH_REMATCH[1]}; i<=10#${BASH_REMATCH[2]}; i++)); do
        [[ -n "${ALL[$i]:-}" ]] && MODELS+=("${ALL[$i]}")
      done
    elif [[ "$p" =~ ^[0-9]+$ ]]; then
      i=$((10#$p))
      [[ -n "${ALL[$i]:-}" ]] && MODELS+=("${ALL[$i]}")
    fi
  done
fi
if ((${#MODELS[@]})); then
  mapfile -t MODELS < <(printf '%s\n' "${MODELS[@]}" | awk 'NF && !seen[$0]++')
fi
[[ ${#MODELS[@]} -eq 0 ]] && { echo "No valid models selected."; exit 1; }

read -rp "Run sustained-load throttle test too? (adds ~$NUM_PREDICT_LONG tokens per model, slow) [y/N]: " DO_LONG
DO_LONG="${DO_LONG,,}"

if [[ "$DEFAULT_CTX" == "y" ]]; then
  read -rp "Run context-capacity curve too? (profile $BENCH_PROFILE; $(wc -w <<<"$CTX_POINTS") points) [Y/n]: " DO_CTX
  DO_CTX="${DO_CTX:-y}"
else
  read -rp "Run context-capacity curve too? (profile $BENCH_PROFILE; $(wc -w <<<"$CTX_POINTS") points) [y/N]: " DO_CTX
  DO_CTX="${DO_CTX:-n}"
fi
DO_CTX="${DO_CTX,,}"

read -rp "Board/cooling/governor note for this run [optional]: " BOARD_NOTE

# Start benchmark timing only after interactive selections are complete, so the
# reported wall duration does not include time spent waiting for user input.
BENCHMARK_START_ISO="$(date --iso-8601=seconds)"
BENCHMARK_START_NS="$(date +%s%N)"

RESULTS="results_$(date +%Y%m%d_%H%M%S).csv"
META_FILE="${RESULTS%.csv}.meta.txt"
OLLAMA_VERSION="$(curl -sS "${CURL_TIMEOUT_ARGS[@]}" "$OLLAMA/api/version" 2>/dev/null | jq -r '.version // "unknown"' 2>/dev/null || printf 'unknown')"

{
  echo "benchmark_started_at: $BENCHMARK_START_ISO"
  echo "host: $(hostname)"
  echo "ollama_url: $OLLAMA"
  echo "ollama_version: ${OLLAMA_VERSION:-unknown}"
  echo "ollama_standard_version: $STANDARD_OLLAMA_VERSION"
  echo "benchmark_profile: $BENCH_PROFILE"
  echo "request_timeout_s: $REQUEST_TIMEOUT"
  echo "unload_timeout_s: $UNLOAD_TIMEOUT"
  echo "unload_poll_interval_s: $UNLOAD_POLL_INTERVAL"
  echo "overhead_warning_threshold_s: $OVERHEAD_WARN_S"
  echo "note: ${BOARD_NOTE:-<none provided>}"
  echo "num_predict_latency: $NUM_PREDICT_LATENCY"
  echo "latency_repeats: $LATENCY_REPEATS"
  echo "run_latency: $RUN_LATENCY"
  echo "chat_system_prompt: $CHAT_SYSTEM_PROMPT"
  echo "chat_prompt: $CHAT_PROMPT"
  echo "think_mode: $THINK_MODE"
  echo "keep_alive: $KEEP_ALIVE"
  echo "num_predict_short: $NUM_PREDICT_SHORT"
  echo "num_predict_prefill: $NUM_PREDICT_PREFILL"
  echo "num_predict_context: $NUM_PREDICT_CONTEXT"
  echo "prefill_sentences: $PREFILL_SENTENCES"
  echo "num_predict_long: $NUM_PREDICT_LONG"
  echo "throttle_windows: $THROTTLE_WINDOWS"
  echo "ctx_points_sentences: $CTX_POINTS (enabled: ${DO_CTX:-n})"
  echo "repeats: $REPEATS"
  echo "embedding_repeats: $EMBED_REPEATS (included: $INCLUDE_EMBEDDINGS)"
  echo "models: ${MODELS[*]}"
  echo "model_details:"
  for m in "${MODELS[@]}"; do
    show_json="$(curl -sS "${CURL_TIMEOUT_ARGS[@]}" "$OLLAMA/api/show" \
      -H 'Content-Type: application/json' \
      -d "$(jq -nc --arg model "$m" '{model: $model}')" 2>/dev/null || true)"
    d="$(jq -r '"family=" + (.details.family // "?") + " params=" + (.details.parameter_size // "?") + " quant=" + (.details.quantization_level // "?")' <<< "$show_json" 2>/dev/null || true)"
    modelfile="$(jq -r '.modelfile // empty' <<< "$show_json" 2>/dev/null || true)"
    if [[ -n "$modelfile" ]]; then
      modelfile_hash="$(printf '%s' "$modelfile" | sha256sum | awk '{print $1}')"
    else
      modelfile_hash="unavailable"
    fi
    echo "  $m: ${d:-unavailable} modelfile_sha256=$modelfile_hash"
  done
} > "$META_FILE"

echo "Metadata written to $META_FILE (ollama $OLLAMA_VERSION)"
if [[ "$OLLAMA_VERSION" != "$STANDARD_OLLAMA_VERSION" ]]; then
  echo "WARNING: package standard is Ollama $STANDARD_OLLAMA_VERSION; results are a runtime-version comparison, not the standard baseline." >&2
fi
echo "timestamp,model,label,test,run,status,eval_count,eval_duration_s,tokens_per_second,prompt_eval_count,prompt_eval_duration_s,prompt_tokens_per_second,total_duration_s,load_duration_s,wall_duration_s,time_to_first_content_s,time_to_first_answer_s,done_reason,server_overhead_s,client_overhead_s,resident_size_bytes,resident_vram_bytes,allocated_context,mem_available_mib,swap_used_mib,batch_items,output_dimensions,embedding_process_duration_s" > "$RESULTS"

ok=0
fail=0

for MODEL in "${MODELS[@]}"; do
  LABEL="$(short "$MODEL")"
  echo
  echo "=== $LABEL  ($MODEL) ==="

  if is_embedding_model "$MODEL"; then
    run_embedding_tests "$MODEL" "$LABEL"
    unload_model "$MODEL"
    sleep 2
    continue
  fi

  if [[ "$RUN_LATENCY" == "1" ]]; then
    run_latency_tests "$MODEL" "$LABEL"
  fi

  # Keeps the v4 measurement regime: timed throughput runs begin with an already
  # resident and warmed model, independent of whether latency tests were enabled.
  echo "  [warmup] loaded-model untimed warmup generation..."
  run_once "$MODEL" "$(make_unique_prompt "$PROMPT_SHORT")" 32 >/dev/null || \
    echo "  [warmup] failed (continuing; run 1 may include startup overhead)"

  tps_list=()
  ptps_list=()
  total_list=()
  wall_list=()

  for ((r=1; r<=REPEATS; r++)); do
    echo "  [short] run $r/$REPEATS..."
    NONCED_SHORT="$(make_unique_prompt "$PROMPT_SHORT")"

    if ! M="$(run_once "$MODEL" "$NONCED_SHORT" "$NUM_PREDICT_SHORT")"; then
      write_failed "$MODEL" "$LABEL" "short" "$r"
      fail=$((fail+1))
      continue
    fi

    record_success "$MODEL" "$LABEL" "short" "$r" "$M"
    tps_list+=("$tps")
    ptps_list+=("$ptps")
    total_list+=("$tds")
    wall_list+=("$wall_s")

    printf '    wall %.2fs | total %.2fs | load %.3fs | gen %s tok/s | prompt %s tok/s | %s tokens\n' \
      "$wall_s" "$tds" "$lds" "$tps" "$ptps" "$ec"
    warn_hidden_overhead "$server_overhead_s"
    warn_early_eos "$ec" "$NUM_PREDICT_SHORT"
    ok=$((ok+1))
  done

  if [[ ${#tps_list[@]} -gt 0 ]]; then
    read -r mean sd <<< "$(mean_stdev "${tps_list[*]}")"
    printf '  [short] generation mean=%s tok/s  stdev=%s (n=%d)\n' "$mean" "$sd" "${#tps_list[@]}"
    read -r pmean psd <<< "$(mean_stdev "${ptps_list[*]}")"
    printf '  [short] prompt-eval mean=%s tok/s  stdev=%s (n=%d)\n' "$pmean" "$psd" "${#ptps_list[@]}"
    read -r total_mean total_sd <<< "$(mean_stdev "${total_list[*]}")"
    printf '  [short] Ollama total mean=%ss  stdev=%ss (n=%d)\n' "$total_mean" "$total_sd" "${#total_list[@]}"
    read -r wall_mean wall_sd <<< "$(mean_stdev "${wall_list[*]}")"
    printf '  [short] client wall mean=%ss  stdev=%ss (n=%d)\n' "$wall_mean" "$wall_sd" "${#wall_list[@]}"
  fi

  echo "  [prefill] document-sized prompt with short answer..."
  NONCED_LONG="$(make_unique_prompt "$PROMPT_LONG")"
  if ML="$(run_once "$MODEL" "$NONCED_LONG" "$NUM_PREDICT_PREFILL")"; then
    record_success "$MODEL" "$LABEL" "prefill" 1 "$ML"
    printf '    wall %.2fs | total %.2fs | load %.3fs | prompt %s tok/s | %s prompt tokens | decode %s tok/s\n' \
      "$wall_s" "$tds" "$lds" "$ptps" "$pec" "$tps"
    warn_hidden_overhead "$server_overhead_s"
  else
    write_failed "$MODEL" "$LABEL" "prefill" 1
  fi

  if [[ "$DO_CTX" == "y" || "$DO_CTX" == "yes" ]]; then
    run_ctx_curve "$MODEL" "$LABEL"
  fi

  if [[ "$DO_LONG" == "y" || "$DO_LONG" == "yes" ]]; then
    run_throttle_test "$MODEL" "$PROMPT_SHORT" "$NUM_PREDICT_LONG" "$LABEL"
  fi

  unload_model "$MODEL"
  sleep 5
done

BENCHMARK_END_ISO="$(date --iso-8601=seconds)"
BENCHMARK_END_NS="$(date +%s%N)"
BENCHMARK_WALL_S="$(ns_diff_s "$BENCHMARK_START_NS" "$BENCHMARK_END_NS")"

{
  echo "benchmark_finished_at: $BENCHMARK_END_ISO"
  echo "benchmark_wall_duration_s: $BENCHMARK_WALL_S"
} >> "$META_FILE"

echo
echo "=== Summary ==="
printf 'Timed short runs ok: %d   failed: %d\n' "$ok" "$fail"
printf 'Benchmark start: %s\n' "$BENCHMARK_START_ISO"
printf 'Benchmark end:   %s\n' "$BENCHMARK_END_ISO"
printf 'Benchmark wall:  %.1f seconds\n' "$BENCHMARK_WALL_S"
echo "Results: $RESULTS"
echo "Meta:    $META_FILE"

if [[ "$RUN_LATENCY" == "1" ]]; then
  echo
  echo "Cold streaming chat latency (closer to first use after model switch):"
  awk -F, '
    $4=="cold_chat" && $6=="ok" {
      ttfc=($16=="NA" ? "n/a" : sprintf("%.3fs",$16))
      ttfa=($17=="NA" ? "n/a" : sprintf("%.3fs",$17))
      rank=($17=="NA" ? $15 : $17)
      printf "%.6f\t  %-22s load=%7.3fs  TTFC=%8s  TTFA=%8s  wall=%7.3fs\n", rank,$3,$14,ttfc,ttfa,$15
    }
  ' "$RESULTS" | sort -n | cut -f2-

  echo
  echo "Mean warm streaming chat latency (resident model):"
  awk -F, '
    $4=="warm_chat" && $6=="ok" {
      wall[$3]+=$15; load[$3]+=$14; n[$3]++
      if ($16!="NA") {ttfc[$3]+=$16; ntfc[$3]++}
      if ($17!="NA") {ttfa[$3]+=$17; ntfa[$3]++}
    }
    END {
      for (m in n) {
        fc=(ntfc[m]>0 ? sprintf("%.3fs",ttfc[m]/ntfc[m]) : "n/a")
        fa=(ntfa[m]>0 ? sprintf("%.3fs",ttfa[m]/ntfa[m]) : "n/a")
        wall_mean=wall[m]/n[m]
        rank=(ntfa[m]>0 ? ttfa[m]/ntfa[m] : wall_mean)
        printf "%.6f\t  %-22s TTFC=%8s  TTFA=%8s  wall=%7.3fs  load=%6.3fs (n=%d)\n", rank,m,fc,fa,wall_mean,load[m]/n[m],n[m]
      }
    }
  ' "$RESULTS" | sort -n | cut -f2-
fi

echo
echo "By mean short-burst generation tok/s:"
awk -F, '
  $4=="short" && $6=="ok" {sum[$3]+=$9; n[$3]++}
  END {for (m in sum) printf "  %-22s %.2f tok/s (n=%d)\n",m,sum[m]/n[m],n[m]}
' "$RESULTS" | sort -k2 -nr

echo
echo "Mean loaded short-request duration:"
awk -F, '
  $4=="short" && $6=="ok" {total[$3]+=$13; wall[$3]+=$15; n[$3]++}
  END {
    for (m in n) {
      wall_mean=wall[m]/n[m]
      printf "%.6f\t  %-22s Ollama=%7.2fs  wall=%7.2fs (n=%d)\n",wall_mean,m,total[m]/n[m],wall_mean,n[m]
    }
  }
' "$RESULTS" | sort -n | cut -f2-


echo
echo "Largest hidden Ollama overhead (total - load - prompt-eval - generation):"
awk -F, '
  $6=="ok" && $19!="" {
    if (!($3 in max) || $19 > max[$3]) {max[$3]=$19; test[$3]=$4; run[$3]=$5}
  }
  END {
    for (m in max)
      printf "%.6f\t  %-22s %7.3fs  test=%s run=%s\n",max[m],m,max[m],test[m],run[m]
  }
' "$RESULTS" | sort -nr | cut -f2-

echo
echo "Document-prefill throughput (synthetic office context; short answer):"
awk -F, '
  $4=="prefill" && $6=="ok" {
    printf "%.6f\t  %-22s %7.2f prompt tok/s  prompt=%6d  wall=%7.2fs\n",-$12,$3,$12,$10,$15
  }
' "$RESULTS" | sort -n | cut -f2-

echo
echo "Loaded allocation and host headroom (last successful row per model):"
awk -F, '
  $6=="ok" && $21!="" {size[$3]=$21; vram[$3]=$22; ctx[$3]=$23; mem[$3]=$24; swap[$3]=$25}
  END {
    for (m in size) {
      sg=size[m]/1073741824; vg=vram[m]/1073741824; pct=(size[m]>0 ? vram[m]/size[m]*100 : 0)
      printf "  %-22s resident=%5.2fGiB  vram-reported=%5.2fGiB (%3.0f%%)  ctx=%6s  MemAvailable=%5.0fMiB  swap=%5.0fMiB\n",m,sg,vg,pct,ctx[m],mem[m],swap[m]
    }
  }
' "$RESULTS" | sort

echo
echo "Embedding cold-load cost (when INCLUDE_EMBEDDINGS=1):"
awk -F, '
  $4=="embed_cold" && $6=="ok" {
    printf "  %-22s load=%6.3fs  wall=%6.3fs  batch=%s  dim=%s\n",$3,$14,$15,$26,$27
  }
' "$RESULTS" | sort

echo
echo "Embedding warm indexing throughput (when INCLUDE_EMBEDDINGS=1):"
awk -F, '
  $4=="embed_warm" && $6=="ok" {sum[$3]+=$9; wall[$3]+=$15; n[$3]++; dim[$3]=$27; items[$3]=$26}
  END {for (m in n) printf "  %-22s %7.2f input tok/s  wall=%6.3fs  batch=%s  dim=%s (n=%d)\n",m,sum[m]/n[m],wall[m]/n[m],items[m],dim[m],n[m]}
' "$RESULTS" | sort -k2 -nr

if [[ "$DO_CTX" == "y" || "$DO_CTX" == "yes" ]]; then
  echo
  echo "Context-length curve (generation tok/s and wall duration):"
  awk -F, '$4 ~ /^ctx_/ && $6=="ok" {
    printf "  %-22s %6d ptok -> %6.2f tok/s  wall=%7.2fs\n",$3,$10,$9,$15
  }' "$RESULTS"
fi

if [[ "$DO_LONG" == "y" || "$DO_LONG" == "yes" ]]; then
  echo
  echo "Throttle check (first window -> last window tok/s):"
  awk -F, -v nwin="$THROTTLE_WINDOWS" '
    $4=="throttle_w1" && $6=="ok" {first[$3]=$9}
    $4=="throttle_w" nwin && $6=="ok" {last[$3]=$9}
    END {
      for (m in first) {
        if (m in last) {
          drop=(first[m]>0) ? (first[m]-last[m])/first[m]*100 : 0
          printf "  %-22s w1=%.2f -> w%s=%.2f  drop=%.1f%%\n",m,first[m],nwin,last[m],drop
        }
      }
    }
  ' "$RESULTS" | sort -t= -k3 -nr
fi
