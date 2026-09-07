#!/usr/bin/env bash
# Public bc250-benchmark dispatcher. Canonical subcommands only.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GENERATION="$SCRIPT_DIR/generation-benchmark.py"
CATEGORY="$SCRIPT_DIR/category-benchmark.py"
RUNTIME="$SCRIPT_DIR/runtime-benchmark.py"
OPENWEBUI="$SCRIPT_DIR/openwebui-benchmark.py"

usage() {
  cat <<'EOF'
Usage:
  bc250-benchmark generation [MODEL ...]
  bc250-benchmark embeddings [MODEL ...]
  bc250-benchmark ocr [MODEL ...]
  bc250-benchmark task [MODEL ...]
  bc250-benchmark agent [MODEL ...]
  bc250-benchmark usecase [MODEL ...]
  bc250-benchmark translation [MODEL ...]
  bc250-benchmark rag-cycle [EMBED_MODEL ANSWER_MODEL]
  bc250-benchmark rag-quality [EMBED_MODEL ANSWER_MODEL]
  bc250-benchmark concurrency MAIN_MODEL EMBED_MODEL
  bc250-benchmark num-batch MODEL [MODEL ...]
  bc250-benchmark owui-rag MODEL --token-file FILE
  bc250-benchmark owui-embedding-batch --token-file FILE
  bc250-benchmark owui-chunk-min MODEL --token-file FILE
  sudo bc250-benchmark owui-system-context MODEL --token-file FILE

Every invocation writes one isolated result directory containing meta.json,
results.jsonl, summary.json, summary.txt, fixtures/, and an optional results.csv
export where the benchmark has a useful tabular view.
EOF
}

command="${1:-}"
case "$command" in
  generation)
    shift
    exec python3 "$GENERATION" "$@"
    ;;
  embeddings|ocr|task|agent|usecase|translation|rag-cycle|rag-quality)
    exec python3 "$CATEGORY" "$@"
    ;;
  concurrency|num-batch)
    exec python3 "$RUNTIME" "$@"
    ;;
  owui-rag|owui-embedding-batch|owui-chunk-min|owui-system-context)
    exec python3 "$OPENWEBUI" "$@"
    ;;
  -h|--help)
    usage
    ;;
  "")
    usage >&2
    exit 2
    ;;
  *)
    echo "ERROR: unknown benchmark subcommand: $command" >&2
    usage >&2
    exit 2
    ;;
esac
