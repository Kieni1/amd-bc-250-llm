#!/usr/bin/env bash
# Run a local coding task through the Ollama coding-agent model.
set -Eeuo pipefail
umask 0077

usage() {
  cat <<'EOF'
Usage:
  bc250-code MODE INPUT [OUTPUT] [TASK...]

MODE:
  generate  Generate a complete file from the task and optional input
  refactor  Refactor the input while preserving behavior
  review    Review the input and return Markdown findings
  document  Produce documentation for the input
  test      Generate tests for the input
  commit    Generate a structured commit message from a staged diff

INPUT may be a file path or '-' for stdin. OUTPUT may be '-' or omitted for
stdout. Add '--' before a task beginning with '-'.

Examples:
  bc250-code review app.py review.md
  bc250-code refactor app.py app.refactored.py "Reduce duplication"
  printf '%s\n' 'Create a small Flask health endpoint' |
    bc250-code generate - health.py
EOF
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }
[[ $# -ge 2 ]] || { usage >&2; exit 2; }
mode="$1"
input="$2"
shift 2

output="-"
if [[ $# -gt 0 && "$1" != "--" ]]; then
  output="$1"
  shift
fi
[[ "${1:-}" == "--" ]] && shift
task="$*"

case "$mode" in
  generate|refactor|review|document|test|commit) ;;
  *) echo "ERROR: unknown mode: $mode" >&2; usage >&2; exit 2 ;;
esac

MODEL="${CODING_AGENT_MODEL:-coding-ministral3-8b-unsloth-ud-q5-k-xl}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
OLLAMA_URL="${OLLAMA_URL%/}"
MAX_INPUT_BYTES="${CODING_AGENT_MAX_INPUT_BYTES:-60000}"

for cmd in curl jq mktemp; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $cmd" >&2
    exit 1
  }
done

input_file="$(mktemp)"
response_file="$(mktemp)"
prompt_file="$(mktemp)"
trap 'rm -f "$input_file" "$response_file" "$prompt_file" "${tmp_out:-}"' EXIT

if [[ "$input" == "-" ]]; then
  cat > "$input_file"
else
  [[ -f "$input" && -r "$input" ]] || {
    echo "ERROR: input file is missing or unreadable: $input" >&2
    exit 1
  }
  cp -- "$input" "$input_file"
fi

size="$(wc -c < "$input_file")"
(( size <= MAX_INPUT_BYTES )) || {
  echo "ERROR: input is ${size} bytes; limit is ${MAX_INPUT_BYTES}." >&2
  exit 1
}

case "$mode" in
  generate)
    instruction="Generate a complete usable file. Return only the file content, without Markdown fences."
    ;;
  refactor)
    instruction="Refactor the supplied file while preserving externally visible behavior. Return only the complete replacement file, without Markdown fences."
    ;;
  review)
    instruction="Review the supplied content. Return Markdown with a short verdict, prioritized findings, and suggested tests. Do not invent line numbers."
    ;;
  document)
    instruction="Write concise developer documentation for the supplied content. Return Markdown."
    ;;
  test)
    instruction="Generate focused tests for the supplied content. Return only the complete test file, without Markdown fences."
    ;;
  commit)
    instruction="Create a Git commit message for the supplied staged diff. Return exactly two sections: SUBJECT: followed by one imperative subject no longer than 72 characters, then BODY: followed by an optional concise explanation. Do not use Markdown fences and do not claim tests were run unless the diff contains their output."
    ;;
esac

{
  printf '%s\n\n' "$instruction"
  [[ -n "$task" ]] && printf 'Additional task:\n%s\n\n' "$task"
  printf 'Input name: %s\n\n--- BEGIN UNTRUSTED INPUT ---\n' "$input"
  cat "$input_file"
  printf '\n--- END UNTRUSTED INPUT ---\n'
} > "$prompt_file"

payload="$(jq -n \
  --arg model "$MODEL" \
  --rawfile prompt "$prompt_file" \
  '{model:$model,prompt:$prompt,stream:false}')"

curl --fail --silent --show-error \
  --connect-timeout 5 --max-time 3600 \
  -H 'Content-Type: application/json' \
  -d "$payload" "${OLLAMA_URL}/api/generate" |
  jq -er '.response' > "$response_file"

if [[ "$output" == "-" ]]; then
  cat "$response_file"
else
  out_dir="$(dirname -- "$output")"
  [[ -d "$out_dir" ]] || {
    echo "ERROR: output directory does not exist: $out_dir" >&2
    exit 1
  }
  output_mode="0644"
  if [[ -f "$output" ]]; then
    output_mode="$(stat -c '%a' -- "$output")"
  fi
  tmp_out="$(mktemp --tmpdir="$out_dir" .bc250-code.XXXXXX)"
  cat "$response_file" > "$tmp_out"
  chmod "$output_mode" "$tmp_out"
  mv -f -- "$tmp_out" "$output"
  unset tmp_out
  echo "Wrote $output"
fi
