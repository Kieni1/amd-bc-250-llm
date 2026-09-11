#!/usr/bin/env bash
# Short comparator only: run production LFM through the exact same repaired
# direct translation harness without installing/mutating any production model.
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BC250_ALLOW_PRODUCTION_REFERENCE=1 exec "$HERE/10-direct-candidate-screen.sh" \
  prod-lfm25-8b-a1b-liquidai-q6-k \
  "${1:-${BC250_SCREEN_ROUNDS:-3}}"
