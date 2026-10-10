#!/usr/bin/env bash
# Greenfield reset for the BC-250 LLM appliance.
set -Eeuo pipefail
umask 0022

ASSUME_YES="${BC250_ASSUME_YES:-0}"
FAILURES=0
LIBEXEC_DIR="${BC250_LIBEXEC:-/usr/libexec/bc250-llm-server}"
MEMORY_PROFILE="$LIBEXEC_DIR/memory-profile.sh"
SWAP_PROFILE="$LIBEXEC_DIR/swap-profile.sh"
GFX1013="$LIBEXEC_DIR/gfx1013.sh"
declare -a CONTAINER_IMAGES=()

heading() { printf '\n===== %s =====\n' "$1"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
failed() { warn "$*"; FAILURES=$((FAILURES + 1)); }

usage() {
  cat <<'USAGE'
Usage: sudo bc250 reset [--yes]
       sudo ./uninstall.sh [--yes]

Factory-style reset for the pre-1.0 appliance. Permanently removes appliance models, Open WebUI data,
containers, BC-250 host profiles, the BC-250 RPM and the separately installed
Ollama binary. Operator documents under /srv/bc250-documents are preserved.

--yes skips the PURGE-BC250-LLM confirmation.
USAGE
}

parse_arguments() {
  while (($#)); do
    case "$1" in
      --yes) ASSUME_YES=1 ;;
      -h|--help) usage; exit 0 ;;
      *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
  done
}

require_root() { [[ ${EUID} -eq 0 ]] || { echo "ERROR: run this command with sudo." >&2; exit 1; }; }

discover_container_images() {
  local file image
  for file in /usr/share/containers/systemd/open-webui.container /usr/share/containers/systemd/tika.container; do
    [[ -r "$file" ]] || continue
    image="$(sed -n 's/^Image=//p' "$file" | head -n 1)"
    [[ -z "$image" ]] || CONTAINER_IMAGES+=("$image")
  done
}


confirm_reset() {
  cat <<'WARNING'
This permanently deletes the BC-250 appliance runtime:
  - downloaded GGUF files and Ollama registrations;
  - Open WebUI accounts, settings, uploads and appliance backups;
  - BC-250 caches, containers, memory/swap settings and CU persistence;
  - the BC-250 RPM and separately installed official Ollama binary.

The reset also removes the appliance-owned firewalld HTTP rule and SELinux
httpd_can_network_connect setting. Fedora upgrades, filesystem growth and
operator documents under /srv/bc250-documents are not rolled back or deleted.
A reboot is required after reset.
WARNING
  [[ "$ASSUME_YES" == 1 ]] && return
  local answer
  read -r -p "Type PURGE-BC250-LLM to continue: " answer
  [[ "$answer" == PURGE-BC250-LLM ]] || { echo "Cancelled."; exit 0; }
}

gfx1013_risk_present() {
  [[ -e /var/lib/bc250-llm-server/gfx1013/active.env || \
     -e /etc/systemd/system/ollama.service.d/70-bc250-gfx1013.conf || \
     -d /opt/bc250-gfx1013 ]] && return 0
  find /boot/loader/entries -maxdepth 1 -type f -name '*-bc250-gfx1013-v33.conf' -print -quit 2>/dev/null | grep -q .
}

restore_gfx1013_stock_boot() {
  heading "1. RESTORE OPTIONAL GFX1013 STOCK BOOT"
  if [[ -x "$GFX1013" ]]; then
    "$GFX1013" reset || {
      echo "ERROR: reset is fail-closed until the stock boot path is restored and verified." >&2
      exit 1
    }
  elif gfx1013_risk_present; then
    echo "ERROR: GFX1013 artifacts exist but the package lifecycle helper is unavailable; refusing reset." >&2
    exit 1
  else
    echo "GFX1013 profile is not staged."
  fi
}

stop_services() {
  heading "2. STOP APPLIANCE SERVICES"
  systemctl disable --now \
    open-webui.service tika.service \
    ollama.service ollama-task.service ollama-embedding.service ollama-agent.service \
    cyan-skillfish-governor-smu.service bc250-cu-live-manager.service \
    owui-backup-config.timer owui-backup-users.timer owui-prune.timer owui-warmup.timer \
    bc250-night-shutdown.timer bc250-enable-wol.service \
    >/dev/null 2>&1 || true
}

remove_live_manager_service() {
  systemctl disable --now bc250-cu-live-manager.service >/dev/null 2>&1 || true
  rm -f -- \
    /etc/systemd/system/bc250-cu-live-manager.service \
    /etc/systemd/system/multi-user.target.wants/bc250-cu-live-manager.service \
    /usr/local/bin/bc250-cu-live-manager /var/usrlocal/bin/bc250-cu-live-manager \
    /etc/bc250-cu-live-manager.conf /etc/udev/rules.d/99-bc250-cu-live-manager.rules
}


remove_profiles() {
  heading "3. REMOVE APPLIANCE HOST PROFILES"
  BC250_ASSUME_YES=1 "$MEMORY_PROFILE" remove || failed "memory profile removal failed"
  BC250_ASSUME_YES=1 "$SWAP_PROFILE" remove || failed "swap profile removal failed"
}

remove_containers() {
  heading "4. REMOVE APPLIANCE CONTAINERS"
  command -v podman >/dev/null 2>&1 || return
  local container image
  for container in open-webui tika; do
    podman container exists "$container" 2>/dev/null || continue
    podman rm --force "$container" || failed "could not remove container $container"
  done
  podman network exists llm 2>/dev/null && podman network rm llm || true
  for image in "${CONTAINER_IMAGES[@]}"; do
    podman image exists "$image" 2>/dev/null || continue
    podman image rm "$image" || warn "preserving image still used elsewhere: $image"
  done
}

remove_network_policy() {
  heading "5. REMOVE APPLIANCE NETWORK POLICY"
  if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld.service; then
    firewall-cmd --quiet --permanent --remove-service=http >/dev/null 2>&1 || true
    firewall-cmd --quiet --reload >/dev/null 2>&1 || failed "firewalld reload failed"
  fi
  command -v setsebool >/dev/null 2>&1 && setsebool -P httpd_can_network_connect 0 || true
}

remove_official_ollama() {
  heading "6. REMOVE SEPARATELY INSTALLED OLLAMA"
  local path
  for path in /usr/local/bin/ollama /usr/bin/ollama; do
    [[ -e "$path" || -L "$path" ]] || continue
    if rpm -qf "$path" >/dev/null 2>&1; then
      warn "preserving RPM-owned Ollama binary: $path"
    else
      rm -f -- "$path"
    fi
  done
  for path in /usr/local/lib/ollama /usr/lib/ollama; do
    [[ -d "$path" ]] || continue
    if rpm -qf "$path" >/dev/null 2>&1; then
      warn "preserving RPM-owned Ollama library directory: $path"
    else
      rm -rf -- "$path"
    fi
  done
  rm -rf -- /usr/share/ollama /var/lib/ollama
}

remove_main_package() {
  heading "7. REMOVE BC-250 RPM"
  rpm -q bc250-llm-server.x86_64 >/dev/null 2>&1 || { echo "bc250-llm-server.x86_64 is already absent."; return; }
  dnf remove -y bc250-llm-server.x86_64 || { echo "ERROR: RPM removal failed; persistent data was retained." >&2; return 1; }
}

remove_persistent_data() {
  heading "8. REMOVE APPLIANCE DATA"
  rm -rf -- \
    /etc/containers/systemd/open-webui.container.d \
    /etc/bc250-llm-server /etc/cyan-skillfish-governor-smu \
    /var/lib/bc250-llm-server /var/cache/bc250-llm-server \
    /var/lib/open-webui /var/backups/bc250-llm-server
  rm -f -- \
    /etc/default/bc250-wol \
    /etc/nginx/default.d/bc250-llm-server.conf{,.rpmnew,.rpmsave} \
    /etc/nginx/conf.d/00-bc250-websocket-map.conf{,.rpmnew,.rpmsave} \
    /var/log/bc250-llm-install.log
  loginctl terminate-user ollama >/dev/null 2>&1 || true
  id ollama >/dev/null 2>&1 && userdel ollama || true
  getent group ollama >/dev/null 2>&1 && groupdel ollama || true
}

finish() {
  systemctl daemon-reload
  systemctl reset-failed >/dev/null 2>&1 || true
  echo
  ((FAILURES == 0)) || { echo "Reset completed with $FAILURES warning(s)." >&2; }
  echo "BC-250 appliance reset completed."
  echo "Reboot now to load normal memory and zram state: sudo reboot"
  echo "Fedora upgrades and filesystem growth were not reversed; /srv/bc250-documents was preserved."
  ((FAILURES == 0))
}

main() {
  parse_arguments "$@"
  require_root
  discover_container_images
  confirm_reset
  restore_gfx1013_stock_boot
  stop_services
  remove_live_manager_service
  remove_profiles
  remove_containers
  remove_network_policy
  remove_official_ollama
  remove_main_package || exit 1
  remove_persistent_data
  finish
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
