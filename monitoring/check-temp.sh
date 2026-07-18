#!/usr/bin/env bash
set -Eeuo pipefail
PATTERN='Tctl|AMD TSI|Thermistor|edge|PPT|fan2|Composite'
command -v sensors >/dev/null 2>&1 || { echo "ERROR: sensors missing." >&2; exit 1; }
show_temps(){ sensors | grep -E "$PATTERN" || true; }
case "${1:-}" in
  -w|--watch) exec watch -n 1 "sensors | grep -E '$PATTERN'" ;;
  "") show_temps ;;
  -h|--help) echo "Usage: $0 [--watch]" ;;
  *) echo "Unknown option: $1" >&2; exit 2 ;;
esac
