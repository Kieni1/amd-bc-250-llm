#!/usr/bin/env bash
set -Eeuo pipefail

status_helper="${BC250_LIBEXEC:-/usr/libexec/bc250-llm-server}/cu-status.sh"

usage() {
  cat <<'USAGE'
Usage: sudo bc250-40cu status

Configure live CU routing with:
  sudo bc250-cu-live-manager

Verify the saved/live routing state with:
  sudo bc250-40cu status
USAGE
}

case "${1:-}" in
  status)
    [[ -x "$status_helper" ]] || { echo "ERROR: CU status helper is missing: $status_helper" >&2; exit 1; }
    exec "$status_helper"
    ;;
  ""|-h|--help|help)
    usage
    ;;
  *)
    echo "ERROR: unsupported bc250-40cu command: $1" >&2
    usage >&2
    exit 2
    ;;
esac
