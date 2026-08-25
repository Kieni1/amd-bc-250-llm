#!/usr/bin/env bash
set -Eeuo pipefail
PATTERN='Tctl|AMD TSI|Thermistor|edge|PPT|fan2|Composite'
arg="${1:-}"
if [[ "$arg" == -h || "$arg" == --help ]]; then
  echo "Usage: bc250-check-temp [--once]  # continuous watch is the default"
  exit 0
fi
command -v sensors >/dev/null 2>&1 || { echo "ERROR: sensors missing." >&2; exit 1; }
show_temps(){ sensors | grep -E "$PATTERN" || true; }
case "$arg" in
  ""|-w|--watch) exec watch -n 1 "sensors | grep -E '$PATTERN'" ;;
  --once) show_temps ;;
  *) echo "Unknown option: $arg" >&2; exit 2 ;;
esac
