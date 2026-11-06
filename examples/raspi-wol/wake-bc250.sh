#!/usr/bin/env bash
set -Eeuo pipefail
CONFIG="${BC250_WAKE_CONFIG:-/etc/default/bc250-wake}"
[[ -r "$CONFIG" ]] || { echo "ERROR: missing $CONFIG" >&2; exit 1; }
# shellcheck disable=SC1090
source "$CONFIG"
: "${BC250_MAC:?Set BC250_MAC in $CONFIG}"
: "${BC250_BROADCAST:?Set BC250_BROADCAST in $CONFIG}"
[[ "$BC250_MAC" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]] || { echo "ERROR: invalid MAC." >&2; exit 1; }
/usr/bin/wakeonlan -i "$BC250_BROADCAST" "$BC250_MAC"
logger -t wake-bc250 "magic packet sent to ${BC250_MAC} via ${BC250_BROADCAST}"

# Optional readiness contract: HTTP :80, not internal Open WebUI :3000.
if [[ -n "${BC250_READINESS_URL:-}" ]]; then
  [[ "$BC250_READINESS_URL" =~ ^http://[A-Za-z0-9.:-]+/?$ ]] || {
    echo "ERROR: BC250_READINESS_URL must be a plain trusted HTTP :80 URL." >&2
    exit 1
  }
  command -v curl >/dev/null 2>&1 || { echo "ERROR: curl is required for BC250_READINESS_URL checks." >&2; exit 1; }
  for _ in {1..18}; do
    if curl --fail --silent --output /dev/null --connect-timeout 3 --max-time 5 "$BC250_READINESS_URL"; then
      logger -t wake-bc250 "BC-250 HTTP readiness confirmed after WOL"
      exit 0
    fi
    sleep 10
  done
  echo "ERROR: BC-250 did not become HTTP-ready after WOL." >&2
  exit 1
else
  echo "WOL packet sent; HTTP readiness unverified. Set BC250_READINESS_URL to enable checking." >&2
fi
