#!/usr/bin/env bash
# Public bc250 advanced benchmark dispatcher. Canonical subcommands only.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GENERATION="$SCRIPT_DIR/generation-benchmark.py"
CATEGORY="$SCRIPT_DIR/category-benchmark.py"
RUNTIME="$SCRIPT_DIR/runtime-benchmark.py"
OPENWEBUI="$SCRIPT_DIR/openwebui-benchmark.py"
PARITY="$SCRIPT_DIR/parity-diagnose.sh"

usage() {
  cat <<'EOF'
Usage:
  bc250 advanced benchmark generation [MODEL ...]
  bc250 advanced benchmark embeddings [MODEL ...]
  bc250 advanced benchmark ocr [MODEL ...]
  bc250 advanced benchmark task [MODEL ...]
  bc250 advanced benchmark agent [MODEL ...]
  bc250 advanced benchmark usecase [MODEL ...]
  bc250 advanced benchmark translation [MODEL ...]
  bc250 advanced benchmark rag-cycle [EMBED_MODEL ANSWER_MODEL]
  bc250 advanced benchmark rag-quality [EMBED_MODEL ANSWER_MODEL]
  bc250 advanced benchmark concurrency MAIN_MODEL EMBED_MODEL
  bc250 advanced benchmark num-batch MODEL [MODEL ...]
  bc250 advanced benchmark owui-translation --token-file FILE
  bc250 advanced benchmark owui-rag MODEL --token-file FILE
  bc250 advanced benchmark owui-embedding-batch --token-file FILE
  bc250 advanced benchmark owui-chunk-min MODEL --token-file FILE
  sudo bc250 advanced benchmark owui-system-context MODEL --token-file FILE
  sudo bc250 advanced benchmark parity [--no-load]

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
  owui-translation|owui-rag|owui-embedding-batch|owui-chunk-min|owui-system-context)
    exec python3 "$OPENWEBUI" "$@"
    ;;
  parity)
    shift
    exec "$PARITY" "$@"
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
