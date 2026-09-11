#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/20-owui-candidate-screen.sh" \
  exp-translate-gemma4-sub-e4b-17s-q4-k-xl \
  "$HERE/prompts/auto-direction-translate-gemma.txt" \
  "${1:-${BC250_SCREEN_ROUNDS:-3}}"
