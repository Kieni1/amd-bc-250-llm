#!/usr/bin/env bash
# Append timestamped thermal/power readings during sustained tests.
set -Eeuo pipefail
umask 0027
OUT="${1:?Usage: log_sensors.sh <logfile>}"
INTERVAL="${SENSOR_INTERVAL:-2}"
PATTERN="${SENSOR_PATTERN:-Tctl|AMD TSI|Thermistor|edge|PPT|fan2|Composite}"

[[ "$INTERVAL" =~ ^[0-9]+([.][0-9]+)?$ ]] && \
  awk -v value="$INTERVAL" 'BEGIN { exit !(value > 0) }' || {
  echo "ERROR: SENSOR_INTERVAL must be a positive number." >&2
  exit 2
}
command -v sensors >/dev/null 2>&1 || { echo "ERROR: sensors command missing." >&2; exit 1; }
command -v sleep >/dev/null 2>&1 || { echo "ERROR: sleep command missing." >&2; exit 1; }
install -d -m 0750 "$(dirname -- "$OUT")"
touch -- "$OUT"
chmod 0640 "$OUT"

echo "Logging sensors to $OUT every ${INTERVAL}s; press Ctrl-C to stop." >&2
trap 'echo "Sensor logging stopped." >&2' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
while true; do
  {
    echo "=== $(date --iso-8601=seconds) ==="
    sensors 2>/dev/null | grep -E "$PATTERN" || echo "WARN: no matching sensor rows"
  } >> "$OUT"
  sleep "$INTERVAL"
done
