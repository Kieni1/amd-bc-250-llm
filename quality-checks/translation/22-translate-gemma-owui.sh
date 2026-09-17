#!/usr/bin/env bash
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf '%s\n' 'REFUSED: execute this script with bash; do not source it.' >&2
    return 0
fi

set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/20-owui-candidate-screen.sh" \
  exp-translate-gemma4-sub-e4b-17s-q4-k-xl \
  "$HERE/prompts/auto-direction-translate-gemma.txt" \
  "${1:-${BC250_SCREEN_ROUNDS:-3}}"
