#!/usr/bin/env bash
# Switch the fixed package topology between normal and exclusive agent mode.
set -Eeuo pipefail

NORMAL_UNITS=(ollama.service ollama-task.service ollama-embedding.service)
AGENT_UNIT=ollama-agent.service

usage() {
  cat <<'USAGE'
Usage: sudo bc250-agent-mode enter|leave|normal|status

enter   Start exclusive agent mode; systemd conflicts stop normal lanes.
leave   Leave exclusive agent mode and restore normal topology.
normal  Converge to normal main/task/embedding topology (same action as leave).
status  Show package lane states and the derived appliance mode.
USAGE
}

need_root() { [[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "ERROR: run this command with sudo." >&2; exit 1; }; }

require_units() {
  local unit
  for unit in "${NORMAL_UNITS[@]}" "$AGENT_UNIT"; do
    systemctl cat "$unit" >/dev/null 2>&1 || { echo "ERROR: required package unit is missing: $unit" >&2; return 1; }
  done
}

wait_api() {
  local port="$1" attempt
  for attempt in {1..30}; do
    curl -fsS --connect-timeout 2 --max-time 3 "http://127.0.0.1:${port}/api/tags" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

agent_units_exclusive() {
  local unit
  systemctl is-active --quiet "$AGENT_UNIT" 2>/dev/null || return 1
  for unit in "${NORMAL_UNITS[@]}"; do
    systemctl is-active --quiet "$unit" 2>/dev/null && return 1
  done
  return 0
}

normal_units_exclusive() {
  local unit
  systemctl is-active --quiet "$AGENT_UNIT" 2>/dev/null && return 1
  for unit in "${NORMAL_UNITS[@]}"; do
    systemctl is-active --quiet "$unit" 2>/dev/null || return 1
  done
  return 0
}

start_normal() {
  systemctl start "${NORMAL_UNITS[@]}"
  wait_api 11434 && wait_api 11435 && wait_api 11437 || {
    echo "ERROR: normal Ollama topology did not become ready on 11434/11435/11437." >&2
    return 1
  }
  normal_units_exclusive || {
    echo "ERROR: normal Ollama services are not exclusive; expected main/task/embedding active and agent inactive." >&2
    return 1
  }
}

enter_agent() {
  require_units
  if systemctl start "$AGENT_UNIT" && wait_api 11436 && agent_units_exclusive; then
    echo "Agent mode active."
    echo "Agent API: 127.0.0.1:11436"
    echo "Normal main/task/embedding lanes are temporarily stopped."
    echo "Open WebUI remains reachable; normal office roles may stay listed but are unavailable in agent mode."
    echo "Return to normal mode with: sudo bc250-agent-mode normal"
    return 0
  fi
  systemctl status "$AGENT_UNIT" --no-pager -l || true
  echo "ERROR: agent mode failed; restoring normal mode." >&2
  start_normal || echo "WARNING: normal mode restoration also failed." >&2
  return 1
}

leave_agent() {
  require_units
  start_normal
  echo "Normal runtime topology restored."
  echo "Main:      :11434 active"
  echo "Task:      :11435 active"
  echo "Embedding: :11437 active"
  echo "Agent:     intentionally inactive"
}

status_agent() {
  local unit state normal_active=0
  for unit in "${NORMAL_UNITS[@]}" "$AGENT_UNIT"; do
    state="$(systemctl is-active "$unit" 2>/dev/null || true)"
    printf '%-25s %s\n' "$unit" "${state:-unknown}"
  done
  systemctl is-active --quiet "$AGENT_UNIT" 2>/dev/null && { echo mode=agent; return; }
  for unit in "${NORMAL_UNITS[@]}"; do
    systemctl is-active --quiet "$unit" 2>/dev/null && normal_active=$((normal_active + 1))
  done
  case "$normal_active" in
    3) echo mode=normal ;;
    0) echo mode=stopped ;;
    *) echo mode=degraded ;;
  esac
}

case "${1:-}" in
  enter) need_root; enter_agent ;;
  leave|normal) need_root; leave_agent ;;
  status) status_agent ;;
  help|-h|--help|'') usage ;;
  *) usage >&2; exit 2 ;;
esac
