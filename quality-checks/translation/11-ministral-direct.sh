#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/10-direct-candidate-screen.sh" exp-ministral3-8b-unsloth-ud-q5-k-xl "${1:-${BC250_SCREEN_ROUNDS:-3}}"
