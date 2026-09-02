#!/usr/bin/env bash
set -Eeuo pipefail
exec "${BC250_SETUP_INSTANCE:-/usr/libexec/bc250-llm-server/setup-ollama-instance.sh}" embedding "$@"
