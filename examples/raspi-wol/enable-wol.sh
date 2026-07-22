#!/usr/bin/env bash
set -Eeuo pipefail
CONFIG="${BC250_WOL_CONFIG:-/etc/default/bc250-wol}"
[[ -r "$CONFIG" ]] || { echo "ERROR: missing $CONFIG" >&2; exit 1; }
# shellcheck disable=SC1090
source "$CONFIG"
: "${BC250_NIC:?Set BC250_NIC in $CONFIG}"
[[ -d "/sys/class/net/$BC250_NIC" ]] || { echo "ERROR: NIC not found: $BC250_NIC" >&2; exit 1; }
/usr/sbin/ethtool -s "$BC250_NIC" wol g
/usr/sbin/ethtool "$BC250_NIC" | grep -E 'Supports Wake-on|Wake-on'
