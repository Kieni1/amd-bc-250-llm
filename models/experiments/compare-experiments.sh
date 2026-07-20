#!/usr/bin/env bash
# Compare an Ollama baseline with the running llama.cpp MTP server.
set -Eeuo pipefail

for cmd in curl jq awk; do command -v "$cmd" >/dev/null || { echo "ERROR: missing command: $cmd" >&2; exit 1; }; done
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
MTP_URL="${MTP_URL:-http://127.0.0.1:8090}"
BASELINE_MODEL="${BASELINE_MODEL:-exp-qwen3-4b-lmstudio-q6-k}"
NUM_PREDICT="${NUM_PREDICT:-400}"
PROMPT="${PROMPT:-Write a concise 300-word explanation of how memory bandwidth limits local LLM inference.}"

baseline_json="$(curl -fsS "$OLLAMA_URL/api/generate" -H 'Content-Type: application/json' -d "$(jq -nc \
  --arg model "$BASELINE_MODEL" --arg prompt "$PROMPT" --argjson n "$NUM_PREDICT" \
  '{model:$model,prompt:$prompt,stream:false,think:false,options:{temperature:0,num_predict:$n}}')" 2>/dev/null || true)"
baseline_tps="$(jq -r 'if .error or ((.eval_duration // 0) <= 0) then empty else .eval_count / (.eval_duration / 1e9) end' <<<"$baseline_json" 2>/dev/null || true)"

mtp_json="$(curl -fsS "$MTP_URL/v1/chat/completions" -H 'Content-Type: application/json' -d "$(jq -nc \
  --arg prompt "$PROMPT" --argjson n "$NUM_PREDICT" \
  '{messages:[{role:"user",content:$prompt}],max_tokens:$n,temperature:0}')" 2>/dev/null || true)"
mtp_tps="$(jq -r '.timings.predicted_per_second // empty' <<<"$mtp_json" 2>/dev/null || true)"
accepted="$(jq -r '.timings | if . then "\(.draft_n_accepted // "n/a")/\(.draft_n // "n/a")" else empty end' <<<"$mtp_json" 2>/dev/null || true)"

if [[ -n "$baseline_tps" ]]; then
  printf 'Ollama %-34s %6.1f tok/s\n' "$BASELINE_MODEL" "$baseline_tps"
else
  echo "Ollama baseline failed or returned no timing."
fi
if [[ -n "$mtp_tps" ]]; then
  printf 'llama.cpp MTP                       %6.1f tok/s  (accepted %s)\n' "$mtp_tps" "${accepted:-n/a}"
else
  echo "MTP server failed or returned no timing."
fi
if [[ -n "$baseline_tps" && -n "$mtp_tps" ]]; then
  awk -v b="$baseline_tps" -v m="$mtp_tps" 'BEGIN { printf "Speedup: %.2fx\n", m / b }'
fi
