#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/10-direct-candidate-screen.sh" exp-hunyuan-mt-7b-mungert-q4-k-m "${1:-${BC250_SCREEN_ROUNDS:-3}}"
