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
    case "$2" in
      glm)
        prompt='Text Recognition:'
        ;;
      dots)
        prompt='Extract the document text in natural reading order. Preserve the original text without translation. Keep headings and lists as Markdown; render tables as HTML and formulas as LaTeX when present.'
        ;;
      ovis)
        prompt='Extract all readable content in natural human reading order and output one Markdown document. Format formulas as LaTeX and tables as HTML. Preserve the original text without translation or paraphrasing.'
        ;;
      chandra)
        prompt='Convert this office document image to structured Markdown. Preserve the original language, reading order, headings, tables, form fields, names, dates, numbers and reference identifiers. Do not translate or summarize.'
        ;;
    esac
    run_ollama run "$model" "$image" "$prompt"
    ;;
  -h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
