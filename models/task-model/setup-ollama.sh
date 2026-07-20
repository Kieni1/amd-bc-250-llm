#!/usr/bin/env bash
set -Eeuo pipefail

if [[ -x /usr/libexec/bc250-llm-server/setup-ollama-instance.sh ]]; then
  exec /usr/libexec/bc250-llm-server/setup-ollama-instance.sh task "$@"
fi
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$script_dir/../setup-ollama-instance.sh" task "$@"
