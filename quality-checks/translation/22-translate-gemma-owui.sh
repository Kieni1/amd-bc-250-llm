#!/usr/bin/env bash
# Re-run production Translate-Gemma through the generic restoring OWUI comparator.
# The package-owned direction roles remain the authoritative production product path.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf '%s\n' 'REFUSED: execute this script with bash; do not source it.' >&2
    return 0
fi
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BC250_ALLOW_PRODUCTION_REFERENCE=1 exec "$HERE/20-owui-candidate-screen.sh" \
  prod-translate-gemma4-sub-e4b-17s-q4-k-xl \
  "$HERE/prompts/auto-direction-translate-gemma.txt" \
  "${1:-${BC250_SCREEN_ROUNDS:-3}}"
