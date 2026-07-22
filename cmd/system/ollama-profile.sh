#!/usr/bin/env bash
set -Eeuo pipefail

PROFILE_DIR="/usr/share/bc250-llm-server/ollama-profiles"
OVERRIDE_DIR="/etc/systemd/system/ollama.service.d"
OVERRIDE_FILE="$OVERRIDE_DIR/60-bc250-runtime-profile.conf"

usage() {
  cat <<'USAGE'
Usage: bc250-ollama-profile COMMAND

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
  echo "Packaged default: balanced (32K context, q8_0 KV cache)"
  if [[ -f "$OVERRIDE_FILE" ]]; then
    echo "Local override: $OVERRIDE_FILE"
    cat "$OVERRIDE_FILE"
  else
    echo "Local override: none"
  fi
  echo
  if systemctl cat ollama.service >/dev/null 2>&1; then
    systemctl show ollama.service -p Environment --no-pager || true
  else
    echo "Ollama service is not installed."
  fi
}

apply_profile() {
  local profile="$1" source="$PROFILE_DIR/$profile.conf"
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
