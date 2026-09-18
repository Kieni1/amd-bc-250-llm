#!/usr/bin/env bash
# Production Translate-Gemma direct reference through the current repaired harness.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf '%s\n' 'REFUSED: execute this script with bash; do not source it.' >&2
    return 0
fi
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BC250_ALLOW_PRODUCTION_REFERENCE=1 exec "$HERE/10-direct-candidate-screen.sh" \
  prod-translate-gemma4-sub-e4b-17s-q4-k-xl \
  "${1:-${BC250_SCREEN_ROUNDS:-1}}"
