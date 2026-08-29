#!/usr/bin/env bash
# Stable bc250-benchmark entry point. Heavy logic is stdlib-only Python so
# request policy, telemetry and category scoring remain testable.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GEN="$SCRIPT_DIR/generation-benchmark.py"
CATEGORY="$SCRIPT_DIR/category-benchmark.py"

case "${1:-}" in
  embeddings|embedding|ocr|task)
    exec python3 "$CATEGORY" "$@"
    ;;
  generation)
    shift
    exec python3 "$GEN" "$@"
    ;;
  -h|--help)
    cat <<'EOF'
Usage:
  bc250-benchmark [generation] [MODEL ...]
  bc250-benchmark embeddings [MODEL ...]
  bc250-benchmark ocr [MODEL ...]
  bc250-benchmark task [MODEL ...]

Generation defaults to BENCH_MODE=neutral: one per-request neutral SYSTEM
and deterministic sampling for comparable model/runtime measurements.
BENCH_MODE=production preserves the registered Modelfile SYSTEM and sampling.

Category suites:
  embeddings  DE/FR/EN retrieval quality (Recall@1/@3, MRR) + throughput
  ocr         office-page extraction quality + runtime
  task        Open WebUI 0.11-style title/tag/retrieval-query tasks

All lanes record peak temperature, GPU clocks/utilization, AMDGPU VRAM/GTT
counters, minimum MemAvailable, maximum swap use, model allocation and digest.
Ollama 0.32.15 is the package benchmark standard.

Useful environment overrides:
  OLLAMA_URL, BENCH_MODE, THINK_MODE, BENCH_PROFILE, RUN_LATENCY,
  RUN_CONTEXT, RUN_THERMAL, TELEMETRY_INTERVAL, REPEATS, KEEP_ALIVE.
EOF
    ;;
  *)
    exec python3 "$GEN" "$@"
    ;;
esac
