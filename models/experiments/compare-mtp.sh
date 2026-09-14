#!/usr/bin/env bash
# Quick integrity/speed comparison between an Ollama baseline and a running llama.cpp MTP server.
# For model-quality/correctness comparisons use bc250-benchmark instead.
set -Eeuo pipefail

for cmd in curl jq awk grep; do command -v "$cmd" >/dev/null || { echo "ERROR: missing command: $cmd" >&2; exit 1; }; done
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
MTP_URL="${MTP_URL:-http://127.0.0.1:8090}"
BASELINE_MODEL="${BASELINE_MODEL:-exp-qwen35-4b-unsloth-q6-k}"
NUM_PREDICT="${NUM_PREDICT:-400}"
PROMPT="${PROMPT:-Write a concise 300-word explanation of how memory bandwidth limits local LLM inference.}"

has_reserved_token_run() {
  local text="$1"
  grep -Eq '(<(unused|reserved)[_-]?[0-9]+>[[:space:]]*){8,}' <<< "$text"
}

has_usable_text() {
  local text="$1"
  grep -Eq '[^[:space:]]' <<< "$text"
}

integrity_failed=0

baseline_json="$(curl -fsS "$OLLAMA_URL/api/generate" -H 'Content-Type: application/json' -d "$(jq -nc \
  --arg model "$BASELINE_MODEL" --arg prompt "$PROMPT" --argjson n "$NUM_PREDICT" \
  '{model:$model,prompt:$prompt,stream:false,options:{temperature:0,num_predict:$n}}')" 2>/dev/null || true)"
baseline_done="$(jq -r '.done // false' <<<"$baseline_json" 2>/dev/null || true)"
baseline_text="$(jq -r '.response // ""' <<<"$baseline_json" 2>/dev/null || true)"
baseline_reserved_run=no
baseline_usable=no
if has_reserved_token_run "$baseline_text"; then
  baseline_reserved_run=yes
fi
if has_usable_text "$baseline_text"; then
  baseline_usable=yes
fi
baseline_tps=""
if [[ "$baseline_done" == true && "$baseline_reserved_run" == no && "$baseline_usable" == yes ]]; then
  baseline_tps="$(jq -r 'if .error or ((.eval_duration // 0) <= 0) then empty else .eval_count / (.eval_duration / 1e9) end' <<<"$baseline_json" 2>/dev/null || true)"
else
  integrity_failed=1
fi

mtp_json="$(curl -fsS "$MTP_URL/v1/chat/completions" -H 'Content-Type: application/json' -d "$(jq -nc \
  --arg prompt "$PROMPT" --argjson n "$NUM_PREDICT" \
  '{messages:[{role:"user",content:$prompt}],max_tokens:$n,temperature:0}')" 2>/dev/null || true)"
mtp_finish="$(jq -r '.choices[0].finish_reason // empty' <<<"$mtp_json" 2>/dev/null || true)"
mtp_text="$(jq -r '[.choices[0].message.content, .choices[0].message.reasoning_content, .choices[0].message.reasoning] | map(select(type == "string" and length > 0)) | join("\n")' <<<"$mtp_json" 2>/dev/null || true)"
mtp_reserved_run=no
mtp_usable=no
if has_reserved_token_run "$mtp_text"; then
  mtp_reserved_run=yes
fi
if has_usable_text "$mtp_text"; then
  mtp_usable=yes
fi
mtp_tps=""
if [[ -n "$mtp_finish" && "$mtp_reserved_run" == no && "$mtp_usable" == yes ]]; then
  mtp_tps="$(jq -r '.timings.predicted_per_second // empty' <<<"$mtp_json" 2>/dev/null || true)"
else
  integrity_failed=1
fi
accepted="$(jq -r '.timings.draft_n_accepted // empty' <<<"$mtp_json" 2>/dev/null || true)"
proposed="$(jq -r '.timings.draft_n // empty' <<<"$mtp_json" 2>/dev/null || true)"
acceptance_rate=""
if [[ "$accepted" =~ ^[0-9]+$ && "$proposed" =~ ^[1-9][0-9]*$ ]]; then
  acceptance_rate="$(awk -v a="$accepted" -v p="$proposed" 'BEGIN { printf "%.1f", a / p * 100 }')"
fi

if [[ "$baseline_done" == true && "$baseline_reserved_run" == no && "$baseline_usable" == yes ]]; then
  if [[ -n "$baseline_tps" ]]; then
    printf 'Ollama %-34s %6.1f tok/s  (done=true, reserved-run=no, usable=yes)\n' "$BASELINE_MODEL" "$baseline_tps"
  else
    printf 'Ollama baseline completion integrity passed but timing was unavailable.\n'
  fi
else
  printf 'Ollama baseline failed completion integrity (done=%s, reserved-run=%s, usable=%s).\n' \
    "${baseline_done:-n/a}" "$baseline_reserved_run" "$baseline_usable"
fi
if [[ -n "$mtp_finish" && "$mtp_reserved_run" == no && "$mtp_usable" == yes ]]; then
  if [[ -n "$mtp_tps" ]]; then
    printf 'llama.cpp MTP                       %6.1f tok/s  (finish=%s, reserved-run=no, usable=yes)\n' "$mtp_tps" "$mtp_finish"
  else
    printf 'MTP completion integrity passed but timing was unavailable (finish=%s).\n' "$mtp_finish"
  fi
else
  printf 'MTP server failed completion integrity (finish=%s, reserved-run=%s, usable=%s).\n' \
    "${mtp_finish:-n/a}" "$mtp_reserved_run" "$mtp_usable"
fi
if [[ -n "$accepted" || -n "$proposed" ]]; then
  printf 'MTP draft acceptance: %s/%s%s\n' "${accepted:-n/a}" "${proposed:-n/a}" \
    "${acceptance_rate:+ (${acceptance_rate}%)}"
else
  echo 'MTP draft acceptance: unavailable (inference may be valid, but MTP qualification evidence is insufficient).'
fi
if [[ -n "$baseline_tps" && -n "$mtp_tps" ]]; then
  awk -v b="$baseline_tps" -v m="$mtp_tps" 'BEGIN { printf "Speedup: %.2fx\n", m / b }'
fi

if (( integrity_failed != 0 )); then
  exit 1
fi
