#!/usr/bin/env bash
set -Eeuo pipefail

OVERRIDE_DIR="/etc/systemd/system/ollama.service.d"
OVERRIDE_FILE="$OVERRIDE_DIR/60-bc250-runtime-profile.conf"

usage() {
  cat <<'USAGE'
Usage: bc250 advanced ollama-profile COMMAND

Commands:
  status        Show the effective Ollama runtime profile
  balanced      Return to the packaged main-lane profile (same as reset)
  reset         Remove the local override and return to the packaged profile
USAGE
}

require_root() {
  [[ ${EUID} -eq 0 ]] || { echo "ERROR: run this command with sudo." >&2; exit 1; }
}

show_status() {
  echo "Ollama profile"
  echo "  Packaged default: balanced (32K context, q8_0 KV cache)"
  if [[ -f "$OVERRIDE_FILE" ]]; then
    echo "  Local override:   $OVERRIDE_FILE"
  else
    echo "  Local override:   none"
  fi
  if ! systemctl cat ollama.service >/dev/null 2>&1; then
    echo "  Service:          not installed"
    return 0
  fi

  local environment key value
  environment="$(systemctl show ollama.service -p Environment --value --no-pager 2>/dev/null || true)"
  for key in OLLAMA_CONTEXT_LENGTH OLLAMA_KV_CACHE_TYPE OLLAMA_MAX_LOADED_MODELS OLLAMA_NUM_PARALLEL OLLAMA_KEEP_ALIVE; do
    value="$(printf '%s\n' "$environment" | tr ' ' '\n' | sed -n "s/^${key}=//p" | tail -n1)"
    case "$key" in
      OLLAMA_CONTEXT_LENGTH) label="Context" ;;
      OLLAMA_KV_CACHE_TYPE) label="KV cache" ;;
      OLLAMA_MAX_LOADED_MODELS) label="Max models" ;;
      OLLAMA_NUM_PARALLEL) label="Parallel" ;;
      OLLAMA_KEEP_ALIVE) label="Keep alive" ;;
    esac
    printf '  %-16s %s\n' "$label:" "${value:-not set}"
  done
}

reset_profile() {
  require_root
  rm -f "$OVERRIDE_FILE"
  systemctl daemon-reload
  if systemctl cat ollama.service >/dev/null 2>&1; then
    # try-restart never starts an inactive main lane; starting it in Agent mode
    # would stop the Agent lane via systemd Conflicts= and degrade topology.
    systemctl try-restart ollama.service
  fi
  echo "Using package-owned balanced profile; per-model context remains in Modelfiles."
  show_status
}

case "${1:-status}" in
  status) show_status ;;
  balanced|reset) reset_profile ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 2 ;;
esac
