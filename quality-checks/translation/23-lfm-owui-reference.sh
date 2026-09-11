#!/usr/bin/env bash
# Re-run the best historical LFM auto-direction configuration through the current
# repaired OWUI harness, then restore the original production preset exactly.
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BC250_ALLOW_PRODUCTION_REFERENCE=1 exec "$HERE/20-owui-candidate-screen.sh" \
  prod-lfm25-8b-a1b-liquidai-q6-k \
  "$HERE/prompts/auto-direction-minimal.txt" \
  "${1:-${BC250_SCREEN_ROUNDS:-3}}"
