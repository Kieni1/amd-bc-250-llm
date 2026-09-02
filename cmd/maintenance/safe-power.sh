#!/usr/bin/env bash
# Apply the selected power action only when the appliance is idle.
set -Eeuo pipefail

log(){ logger -t bc250-safe-power -- "$*"; printf '%s\n' "$*"; }
SAFE_POWER_PORTS="${SAFE_POWER_PORTS:-${SAFE_SUSPEND_PORTS:-22 80 443 3000 11434 11435 11436 11437}}"
NIGHT_POWER_ACTION="${NIGHT_POWER_ACTION:-poweroff}"
REQUIRE_WOL="${REQUIRE_WOL:-0}"

[[ "$NIGHT_POWER_ACTION" == poweroff || "$NIGHT_POWER_ACTION" == suspend ]] || {
  log "Refusing power action: NIGHT_POWER_ACTION must be poweroff or suspend."
  exit 1
}
[[ "$REQUIRE_WOL" == 0 || "$REQUIRE_WOL" == 1 ]] || {
  log "Refusing power action: REQUIRE_WOL must be 0 or 1."
  exit 1
}
for port in $SAFE_POWER_PORTS; do
  [[ "$port" =~ ^[0-9]{1,5}$ ]] && ((port >= 1 && port <= 65535)) || {
    log "Refusing power action: invalid SAFE_POWER_PORTS entry: $port"
    exit 1
  }
done
port_regex="$(tr ' ' '|' <<<"$SAFE_POWER_PORTS")"

for unit in \
  owui-maintenance@backup-config.service \
  owui-maintenance@backup-users.service \
  owui-maintenance@prune-uploads.service \
  owui-warmup.service; do
  if systemctl is-active --quiet "$unit"; then
    log "Deferring $NIGHT_POWER_ACTION: $unit is active."
    exit 0
  fi
done

if command -v ss >/dev/null 2>&1; then
  connections="$(ss -Htn state established | awk -v re=":(${port_regex})$" '
    $4 ~ re || $5 ~ re {print}
  ')"
  if [[ -n "$connections" ]]; then
    log "Deferring $NIGHT_POWER_ACTION: active SSH, UI or Ollama TCP session detected."
    exit 0
  fi
fi

if [[ -r /etc/default/bc250-wol && -x /usr/libexec/bc250-llm-server/enable-wol.sh ]]; then
  if ! /usr/libexec/bc250-llm-server/enable-wol.sh; then
    if [[ "$REQUIRE_WOL" == 1 ]]; then
      log "Refusing $NIGHT_POWER_ACTION: required Wake-on-LAN setup failed."
      exit 1
    fi
    log "WARNING: Wake-on-LAN setup failed; continuing because REQUIRE_WOL=0."
  fi
elif [[ "$REQUIRE_WOL" == 1 ]]; then
  log "Refusing $NIGHT_POWER_ACTION: required Wake-on-LAN configuration is missing."
  exit 1
fi

log "No active requests or maintenance jobs; requesting $NIGHT_POWER_ACTION."
exec systemctl "$NIGHT_POWER_ACTION"
