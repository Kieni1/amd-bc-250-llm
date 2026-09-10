#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/10-candidate-screen.sh" exp-minicpm5-2b-openbmb-q4-k-m "${1:-${BC250_SCREEN_ROUNDS:-3}}"
