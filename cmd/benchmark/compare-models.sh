#!/usr/bin/env bash
# Stable bc250-benchmark entry point. Heavy logic is stdlib-only Python so
# request policy, telemetry and category scoring remain testable.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GEN="$SCRIPT_DIR/generation-benchmark.py"
CATEGORY="$SCRIPT_DIR/category-benchmark.py"

case "${1:-}" in
  embeddings|embedding|ocr|task|agent|coding|usecase|acceptance|translation|translate|rag|rag-cycle|rag-quality|rag-acceptance)
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
  bc250-benchmark agent [MODEL ...]
  bc250-benchmark usecase [MODEL ...]
  bc250-benchmark translation [MODEL ...]
  bc250-benchmark rag [EMBED_MODEL ANSWER_MODEL]
  bc250-benchmark rag-quality [EMBED_MODEL ANSWER_MODEL]

Generation defaults to BENCH_MODE=neutral: one per-request neutral SYSTEM
and deterministic sampling for comparable model/runtime measurements.
BENCH_MODE=production preserves the registered Modelfile SYSTEM and sampling
for the same generic generation workload (production-configuration comparison).

Category suites:
  embeddings  DE/FR/EN retrieval quality (Recall@1/@3, MRR) + throughput
  ocr         office-page extraction quality + runtime
  task        Open WebUI 0.11.3-compatible title/tag/retrieval-query tasks
  agent       syntax/structure correctness for coding/agent output (port 11436)
  usecase     five small role-acceptance checks for the production model set
  translation DE<->FR office translation preservation/acceptance checks
  rag         dedicated embedding + warm answer-model coexistence cycle
  rag-quality retrieval ranking plus grounded-answer acceptance on office facts

Generation, embedding and OCR lanes record the full resource set; task and agent
lanes intentionally keep a smaller latency/correctness-oriented telemetry set.
Ollama 0.33.3 is the package benchmark standard.

Useful environment overrides:
  OLLAMA_URL, BENCH_MODE, THINK_MODE, BENCH_PROFILE, RUN_LATENCY,
  RUN_CONTEXT, RUN_THERMAL, RUN_WARM_PREFIX, TELEMETRY_INTERVAL,
  BC250_DRM_CARD, REPEATS, KEEP_ALIVE, RAG_QUALITY_TOP_K.
EOF
    ;;
  *)
    exec python3 "$GEN" "$@"
    ;;
esac
