#!/usr/bin/env bash
# Former production LFM retained as an experimental rollback/reference comparator.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf '%s\n' 'REFUSED: execute this script with bash; do not source it.' >&2
    return 0
fi
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/10-direct-candidate-screen.sh" \
  exp-lfm25-8b-a1b-liquidai-q6-k \
  "${1:-${BC250_SCREEN_ROUNDS:-1}}"
