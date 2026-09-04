#!/usr/bin/env bash
# Switch between the package-defined normal Ollama topology and the exclusive agent lane.
set -Eeuo pipefail

NORMAL_UNITS=(ollama.service ollama-task.service ollama-embedding.service)
AGENT_UNIT=ollama-agent.service

usage() {
  cat <<'USAGE'
Usage: sudo bc250-agent-mode enter|leave|status

enter   Start the exclusive agent; systemd conflicts stop all normal Ollama lanes.
leave   Stop the agent and restore main + task + embedding normal mode.
status  Show the four package-defined lane states.
USAGE
}

need_root() {
  [[ ${EUID:-$(id -u)} -eq 0 ]] || {
    echo "ERROR: run this command with sudo." >&2
    exit 1
  }
}

require_units() {
  local unit
  for unit in "${NORMAL_UNITS[@]}" "$AGENT_UNIT"; do
    systemctl cat "$unit" >/dev/null 2>&1 || {
      echo "ERROR: required package unit is missing: $unit" >&2
      return 1
    }
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

start_normal() {
  systemctl stop "$AGENT_UNIT" >/dev/null 2>&1 || true
  systemctl start "${NORMAL_UNITS[@]}"
  wait_api 11434 && wait_api 11435 && wait_api 11437 || {
    echo "ERROR: normal Ollama topology did not become ready on 11434/11435/11437." >&2
    return 1
  }
}

enter_agent() {
  local rc=0
  require_units
  systemctl start "$AGENT_UNIT" || rc=$?
  ((rc != 0)) || wait_api 11436 || rc=$?
  if ((rc == 0)); then
    echo "Agent mode active: 11436 only; main/task/embedding are stopped by unit conflicts."
    return 0
  fi
  systemctl status "$AGENT_UNIT" --no-pager -l || true
  echo "ERROR: agent Ollama did not become ready; restoring normal mode." >&2
  start_normal || echo "WARNING: normal mode restoration also failed." >&2
  return "$rc"
}

leave_agent() {
  require_units
  start_normal
  echo "Normal mode active: main/task/embedding are ready; agent is stopped."
}

status_agent() {
  local unit state normal_active=0 normal_inactive=0
  for unit in "${NORMAL_UNITS[@]}" "$AGENT_UNIT"; do
    if systemctl cat "$unit" >/dev/null 2>&1; then
      state="$(systemctl is-active "$unit" 2>/dev/null || true)"
      printf '%-25s %s\n' "$unit" "${state:-unknown}"
    else
      printf '%-25s missing\n' "$unit"
    fi
  done
  systemctl is-active --quiet "$AGENT_UNIT" 2>/dev/null && { echo 'mode=agent'; return; }
  for unit in "${NORMAL_UNITS[@]}"; do
    if systemctl is-active --quiet "$unit" 2>/dev/null; then
      normal_active=$((normal_active + 1))
    else
      normal_inactive=$((normal_inactive + 1))
    fi
  done
  if ((normal_active == 3 && normal_inactive == 0)); then
    echo 'mode=normal'
  elif ((normal_active == 0)); then
    echo 'mode=stopped'
  else
    echo 'mode=degraded'
  fi
}

case "${1:-}" in
  enter) need_root; enter_agent ;;
  leave) need_root; leave_agent ;;
  status) status_agent ;;
  help|-h|--help|'') usage ;;
  *) usage >&2; exit 2 ;;
esac
