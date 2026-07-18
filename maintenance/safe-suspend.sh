#!/usr/bin/env bash
# Suspend only when no maintenance job and no established UI/inference session exists.
set -Eeuo pipefail
log(){ logger -t bc250-safe-suspend -- "$*"; printf '%s\n' "$*"; }
SAFE_SUSPEND_PORTS="${SAFE_SUSPEND_PORTS:-22 443 3000 11434 11435}"
for port in $SAFE_SUSPEND_PORTS; do
  [[ "$port" =~ ^[0-9]{1,5}$ ]] && ((port >= 1 && port <= 65535)) || {
    log "Refusing suspend: invalid SAFE_SUSPEND_PORTS entry: $port"
    exit 1
  }
done
port_regex="$(tr ' ' '|' <<<"$SAFE_SUSPEND_PORTS")"

for unit in owui-backup-config.service owui-backup-users.service owui-prune.service; do
  if systemctl is-active --quiet "$unit"; then
    log "Deferring suspend: $unit is active."
    exit 0
  fi
done

if command -v ss >/dev/null 2>&1; then
  connections="$(ss -Htn state established | awk -v re=":(${port_regex})$" '
    $4 ~ re || $5 ~ re {print}
  ')"
  if [[ -n "$connections" ]]; then
    log "Deferring suspend: active UI or Ollama TCP session detected."
    exit 0
  fi
fi

if [[ -x /usr/libexec/bc250-llm-server/enable-wol.sh ]]; then
  /usr/libexec/bc250-llm-server/enable-wol.sh
fi
log "No active requests or maintenance jobs; suspending."
exec systemctl suspend
