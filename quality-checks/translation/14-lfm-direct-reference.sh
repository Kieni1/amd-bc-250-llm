#!/usr/bin/env bash
# Short comparator only: run production LFM through the exact same repaired
# direct translation harness without installing/mutating any production model.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf '%s\n' 'REFUSED: execute this script with bash; do not source it.' >&2
    return 0
fi

set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BC250_ALLOW_PRODUCTION_REFERENCE=1 exec "$HERE/10-direct-candidate-screen.sh" \
  prod-lfm25-8b-a1b-liquidai-q6-k \
  "${1:-${BC250_SCREEN_ROUNDS:-1}}"
