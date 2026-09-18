#!/usr/bin/env bash
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf '%s\n' 'REFUSED: execute this script with bash; do not source it.' >&2
    return 0
fi

set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/20-owui-candidate-screen.sh" \
  exp-hunyuan-mt-7b-mungert-q4-k-m \
  "$HERE/prompts/auto-direction-minimal.txt" \
  "${1:-${BC250_SCREEN_ROUNDS:-3}}"
