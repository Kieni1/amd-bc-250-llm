#!/usr/bin/env bash
# Thin convenience wrapper around the shared experimental-model manager.
set -Eeuo pipefail

LIBEXEC="${BC250_LIBEXEC:-/usr/libexec/bc250-llm-server}"
MANAGER="${MODEL_MANAGER:-$LIBEXEC/modelctl}"
[[ -x "$MANAGER" ]] || MANAGER="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/modelctl.py"
ENDPOINT="${OLLAMA_URL:-${OLLAMA_HOST:-http://127.0.0.1:11434}}"

usage() {
  cat <<'EOF_USAGE'
Usage:
  bc250-ocr list
  sudo bc250-ocr install glm|dots|ovis|chandra
  bc250-ocr show glm|dots|ovis|chandra
  bc250-ocr test glm|dots|ovis|chandra IMAGE

OCR is experimental. Test real German/French/English office pages before use.
EOF_USAGE
}

model_name() {
  case "$1" in
    glm) echo exp-glm-ocr-ggml-q8-0 ;;
    dots) echo exp-dots-ocr-ggml-q8-0 ;;
    ovis) echo exp-ovisocr2-abiray-q8-0 ;;
    chandra) echo exp-chandra-ocr2-prithivmlmods-q4-k-m ;;
    *) echo "ERROR: OCR model must be glm, dots, ovis or chandra." >&2; exit 2 ;;
  esac
}

run_ollama() {
  command -v ollama >/dev/null 2>&1 || { echo "ERROR: ollama is not installed." >&2; exit 1; }
  OLLAMA_HOST="$ENDPOINT" ollama "$@"
}

case "${1:-}" in
  list)
    "$MANAGER" list experiments | awk 'NR==1 || /exp-(glm-ocr|dots-ocr|ovisocr2|chandra-ocr2)-/'
    ;;
  install)
    [[ $# -eq 2 ]] || { usage >&2; exit 2; }
    model="$(model_name "$2")"
    "$MANAGER" install experiments "$model"
    ;;
  show)
    [[ $# -eq 2 ]] || { usage >&2; exit 2; }
    model="$(model_name "$2")"
    run_ollama show "$model"
    ;;
  test)
    [[ $# -eq 3 ]] || { usage >&2; exit 2; }
    model="$(model_name "$2")"
    image="$(realpath -e -- "$3")"
    [[ -f "$image" ]] || { echo "ERROR: image is not a regular file: $image" >&2; exit 1; }
    if [[ "$2" == glm ]]; then
      prompt='Text Recognition:'
    else
      prompt='Extract all readable content in natural reading order as Markdown. Preserve the original text without translation or commentary.'
    fi
    run_ollama run "$model" "$image" "$prompt"
    ;;
  -h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
