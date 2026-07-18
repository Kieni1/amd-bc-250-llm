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
