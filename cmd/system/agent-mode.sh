#!/usr/bin/env bash
# Switch the BC-250 between normal LLM services and the exclusive coding-agent lane.
set -Eeuo pipefail

NORMAL_UNITS=(ollama.service ollama-task.service ollama-embedding.service)
AGENT_UNIT=ollama-agent.service

usage() {
  cat <<'USAGE'
Usage: sudo bc250-agent-mode enter|leave|status

enter   Stop main/task/embedding Ollama services and start the exclusive agent.
leave   Stop the agent and restore installed normal Ollama services.
status  Show which runtime mode is active.
USAGE
}

need_root() {
  [[ ${EUID:-$(id -u)} -eq 0 ]] || {
    echo "ERROR: run this command with sudo." >&2
    exit 1
  }
}

unit_exists() {
  systemctl cat "$1" >/dev/null 2>&1
}

is_active() {
  systemctl is-active --quiet "$1" 2>/dev/null
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
  local unit
  for unit in "${NORMAL_UNITS[@]}"; do
    unit_exists "$unit" || continue
    systemctl start "$unit"
  done
}

enter_agent() {
  local restore=1
  unit_exists "$AGENT_UNIT" || {
    echo "ERROR: $AGENT_UNIT is not installed. Run sudo bc250-setup-coding-agent first." >&2
    exit 1
  }
  trap 'rc=$?; if (( restore )); then systemctl stop "$AGENT_UNIT" >/dev/null 2>&1 || true; start_normal >/dev/null 2>&1 || true; fi; exit "$rc"' ERR
  systemctl stop "${NORMAL_UNITS[@]}" >/dev/null 2>&1 || true
  systemctl start "$AGENT_UNIT"
  wait_api 11436 || {
    systemctl status "$AGENT_UNIT" --no-pager -l || true
    echo "ERROR: agent Ollama did not become ready on 11436; normal mode will be restored." >&2
    return 1
  }
  restore=0
  trap - ERR
  echo "Agent mode active: 11436 is exclusive; main/task/embedding are stopped."
}

leave_agent() {
  systemctl stop "$AGENT_UNIT" >/dev/null 2>&1 || true
  start_normal
  echo "Normal mode restored: main/task/embedding services started where installed."
}

status_agent() {
  local active_normal=0 unit state
  printf 'mode='
  if is_active "$AGENT_UNIT"; then
    echo agent
  else
    for unit in "${NORMAL_UNITS[@]}"; do
      is_active "$unit" && active_normal=1
    done
    ((active_normal)) && echo normal || echo stopped
  fi
  for unit in "${NORMAL_UNITS[@]}" "$AGENT_UNIT"; do
    if unit_exists "$unit"; then
      state="$(systemctl is-active "$unit" 2>/dev/null || true)"
      printf '%-25s %s\n' "$unit" "${state:-unknown}"
    else
      printf '%-25s not-installed\n' "$unit"
    fi
  done
}

case "${1:-}" in
  enter) need_root; enter_agent ;;
  leave) need_root; leave_agent ;;
  status) status_agent ;;
  help|-h|--help|'') usage ;;
  *) usage >&2; exit 2 ;;
esac
