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

# Internal companion requests may exempt exactly the SSH connection that carries
# the forced command. Any other protected connection must still defer poweroff.
companion_ssh="${BC250_SAFE_POWER_EXEMPT_SSH:-}"
companion_client=''
companion_server=''
if [[ -n "$companion_ssh" ]]; then
  read -r companion_client_ip companion_client_port companion_server_ip companion_server_port extra <<< "$companion_ssh"
  [[ -z "${extra:-}" && -n "${companion_client_ip:-}" && -n "${companion_server_ip:-}" && \
     "${companion_client_port:-}" =~ ^[0-9]{1,5}$ && "${companion_server_port:-}" =~ ^[0-9]{1,5}$ && \
     "$companion_client_port" -ge 1 && "$companion_client_port" -le 65535 && \
     "$companion_server_port" -eq 22 ]] || {
    log "Refusing power action: invalid companion SSH exemption."
    exit 1
  }
  companion_client="${companion_client_ip}:${companion_client_port}"
  companion_server="${companion_server_ip}:${companion_server_port}"
fi

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

if ! command -v ss >/dev/null 2>&1; then
  log "Deferring $NIGHT_POWER_ACTION: TCP activity inspection is unavailable."
  exit 0
fi

if ! ss_output="$(ss -Htn state established)"; then
  log "Deferring $NIGHT_POWER_ACTION: TCP activity inspection failed."
  exit 0
fi

# `ss -Htn` prefixes the endpoints with Recv-Q/Send-Q, so inspect the final
# two fields instead of assuming fixed endpoint columns. Match both endpoints
# deliberately: inbound appliance sessions and selected outbound activity both
# defer safe power.
connections=''
protected_local_port=''
companion_matches=0
while IFS= read -r line; do
  [[ -n "$line" ]] || continue
  read -ra fields <<< "$line"
  ((${#fields[@]} >= 2)) || continue
  local_endpoint="${fields[${#fields[@]}-2]}"
  peer_endpoint="${fields[${#fields[@]}-1]}"
  local_endpoint="${local_endpoint//\[/}"
  local_endpoint="${local_endpoint//\]/}"
  peer_endpoint="${peer_endpoint//\[/}"
  peer_endpoint="${peer_endpoint//\]/}"

  if [[ -n "$companion_ssh" ]] && \
     { [[ "$local_endpoint" == "$companion_server" && "$peer_endpoint" == "$companion_client" ]] ||
       [[ "$local_endpoint" == "$companion_client" && "$peer_endpoint" == "$companion_server" ]]; }; then
    ((companion_matches+=1))
    continue
  fi
  if [[ "$local_endpoint" =~ :(${port_regex})$ ]]; then
    [[ -n "$protected_local_port" ]] || protected_local_port="${BASH_REMATCH[1]}"
    connections+="${line}"$'\n'
  elif [[ "$peer_endpoint" =~ :(${port_regex})$ ]]; then
    connections+="${line}"$'\n'
  fi
done <<< "$ss_output"

if [[ -n "$companion_ssh" ]]; then
  if ((companion_matches != 1)); then
    log "Refusing power action: authenticated companion SSH connection was not found exactly once."
    exit 1
  fi
  log "Ignoring only the authenticated companion control SSH connection for this request."
fi
if [[ -n "$connections" ]]; then
  if [[ -n "$protected_local_port" ]]; then
    case "$protected_local_port" in
      22) protected_label="SSH connection" ;;
      80) protected_label="HTTP connection" ;;
      443) protected_label="HTTPS connection" ;;
      3000) protected_label="Open WebUI connection" ;;
      11434) protected_label="main Ollama connection" ;;
      11435) protected_label="task Ollama connection" ;;
      11436) protected_label="agent Ollama connection" ;;
      11437) protected_label="embedding Ollama connection" ;;
      *) protected_label="TCP connection" ;;
    esac
    log "Deferring $NIGHT_POWER_ACTION: active protected $protected_label detected on local port $protected_local_port."
  else
    log "Deferring $NIGHT_POWER_ACTION: protected TCP activity detected on a configured remote endpoint."
  fi
  exit 0
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
# Do not block this oneshot service on the system power transaction it starts.
# Blocking here can let shutdown tear down the caller before systemd completes
# the decision unit, producing a canceled service despite a valid request.
systemctl --no-block "$NIGHT_POWER_ACTION"
