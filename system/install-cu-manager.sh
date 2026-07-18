#!/usr/bin/env bash
# Compatibility command: the pinned live manager is now part of the RPM.
set -Eeuo pipefail

manager="/usr/bin/bc250-cu-live-manager"
[[ -x "$manager" ]] || {
  echo "ERROR: $manager is missing; reinstall or upgrade bc250-llm-server." >&2
  exit 1
}
command -v umr >/dev/null 2>&1 || {
  echo "ERROR: umr is missing; run: sudo dnf install umr" >&2
  exit 1
}
echo "The pinned CU live manager is already installed by bc250-llm-server."
echo "Run: sudo bc250-40cu"
