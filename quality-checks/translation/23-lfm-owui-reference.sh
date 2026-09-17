#!/usr/bin/env bash
# Re-run the best historical LFM auto-direction configuration through the current
# repaired OWUI harness, then restore the original production preset exactly.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf '%s\n' 'REFUSED: execute this script with bash; do not source it.' >&2
    return 0
fi

set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BC250_ALLOW_PRODUCTION_REFERENCE=1 exec "$HERE/20-owui-candidate-screen.sh" \
  prod-lfm25-8b-a1b-liquidai-q6-k \
  "$HERE/prompts/auto-direction-minimal.txt" \
  "${1:-${BC250_SCREEN_ROUNDS:-3}}"
