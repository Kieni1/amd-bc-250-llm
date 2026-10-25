#!/usr/bin/env bash
set -Eeuo pipefail

PROFILE_DIR="/usr/share/bc250-llm-server/ollama-profiles"
OVERRIDE_DIR="/etc/systemd/system/ollama.service.d"
OVERRIDE_FILE="$OVERRIDE_DIR/60-bc250-runtime-profile.conf"

usage() {
  cat <<'USAGE'
Usage: bc250 advanced ollama-profile COMMAND

Commands:
  status        Show the effective Ollama runtime profile
  balanced      Use 32K context with q8_0 KV cache
  max-context   Use 64K context with q4_0 KV cache
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

apply_profile() {
  local profile="$1" source
  source="$PROFILE_DIR/$profile.conf"
  require_root
  [[ -r "$source" ]] || { echo "ERROR: missing profile $source" >&2; exit 1; }
  install -d -m0755 "$OVERRIDE_DIR"
  install -m0644 "$source" "$OVERRIDE_FILE"
  systemctl daemon-reload
  if systemctl cat ollama.service >/dev/null 2>&1; then
    systemctl restart ollama.service
  fi
  echo "Applied Ollama profile: $profile"
  show_status
}

case "${1:-status}" in
  status) show_status ;;
  balanced) apply_profile balanced ;;
  max-context) apply_profile max-context ;;
  reset)
    require_root
    rm -f "$OVERRIDE_FILE"
    systemctl daemon-reload
    if systemctl cat ollama.service >/dev/null 2>&1; then
      systemctl restart ollama.service
    fi
    echo "Removed the local override; the packaged balanced profile is active."
    ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 2 ;;
esac
