#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/10-candidate-screen.sh" exp-qwen3-1.7b-ggml-q4-k-m "${1:-${BC250_SCREEN_ROUNDS:-3}}"
