#!/usr/bin/env bash
# Greenfield reset for the BC-250 LLM appliance.
set -Eeuo pipefail
umask 0022

ASSUME_YES="${BC250_ASSUME_YES:-0}"
FAILURES=0
declare -A MODULE_TARGETS=()
declare -a CONTAINER_IMAGES=()

heading() { printf '\n===== %s =====\n' "$1"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
failed() { warn "$*"; FAILURES=$((FAILURES + 1)); }

usage() {
  cat <<'USAGE'
Usage: sudo bc250-reset [--yes]
       sudo bc250-uninstall [--yes]
       sudo ./uninstall.sh [--yes]

Pre-1.0 greenfield reset. Permanently removes appliance models, Open WebUI data,
containers, BC-250 host profiles, the BC-250 RPM and the separately installed
Ollama binary. Verified stock AMDGPU modules are restored where BC-250 backups
exist. Operator documents under /srv/bc250-documents are preserved.

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

discover_40cu_state() {
  local backup target
  shopt -s nullglob
  for backup in \
      /usr/lib/modules/*/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko.bc250-backup-* \
      /usr/lib/modules/*/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko.xz.bc250-backup-* \
      /usr/lib/modules/*/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko.zst.bc250-backup-*; do
    target="${backup%.bc250-backup-*}"
    MODULE_TARGETS["$target"]=1
  done
  shopt -u nullglob
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

stop_services() {
  heading "1. STOP APPLIANCE SERVICES"
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

module_has_unlock() {
  local target="$1" file="$2"
  case "$target" in
    *.xz) xz --test "$file" >/dev/null 2>&1 || return 2; xz -dc "$file" | LC_ALL=C grep -a bc250_cc_write_mode >/dev/null ;;
    *.zst) zstd --test --quiet "$file" >/dev/null 2>&1 || return 2; zstd -dcq "$file" | LC_ALL=C grep -a bc250_cc_write_mode >/dev/null ;;
    *) LC_ALL=C grep -a bc250_cc_write_mode "$file" >/dev/null ;;
  esac
}

restore_40cu_modules() {
  heading "2. RESTORE VERIFIED STOCK AMDGPU MODULES"
  remove_live_manager_service
  rm -f -- /etc/modprobe.d/bc250-40cu.conf /etc/dracut.conf.d/90-bc250-40cu.conf

  local target backup stock status relative kernel
  local -a backups
  for target in "${!MODULE_TARGETS[@]}"; do
    shopt -s nullglob; backups=( "${target}.bc250-backup-"* ); shopt -u nullglob
    stock=""
    for backup in "${backups[@]}"; do
      if module_has_unlock "$target" "$backup"; then
        continue
      else
        status=$?
        ((status == 1)) && { stock="$backup"; break; }
        warn "cannot verify AMDGPU backup: $backup"
      fi
    done
    if [[ -z "$stock" ]]; then
      failed "no verifiable stock AMDGPU backup for $target; backups were retained"
      continue
    fi
    echo "Restoring stock module: $target"
    cp --preserve=mode,timestamps -- "$stock" "$target" || { failed "could not restore $stock"; continue; }
    rm -f -- "${backups[@]}" "${target}.bc250-new"
    relative="${target#/usr/lib/modules/}"; kernel="${relative%%/*}"
    depmod -a "$kernel" || failed "depmod failed for kernel $kernel"
    dracut --force --kver "$kernel" || failed "initramfs rebuild failed for kernel $kernel"
  done

  shopt -s nullglob
  for target in \
      /usr/lib/modules/*/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko \
      /usr/lib/modules/*/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko.xz \
      /usr/lib/modules/*/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko.zst; do
    if module_has_unlock "$target" "$target"; then
      [[ -n "${MODULE_TARGETS[$target]:-}" ]] || failed "patched AMDGPU module has no stock backup: $target"
    else
      status=$?; ((status == 1)) || failed "could not verify installed AMDGPU module: $target"
    fi
  done
  shopt -u nullglob
  rm -rf -- /tmp/bc250-40cu-build
}

remove_profiles() {
  heading "3. REMOVE APPLIANCE HOST PROFILES"
  BC250_ASSUME_YES=1 bc250-memory-profile remove || failed "memory profile removal failed"
  BC250_ASSUME_YES=1 bc250-swap-profile remove || failed "swap profile removal failed"
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
  echo "Reboot now to load stock GPU, memory and zram state: sudo reboot"
  echo "Fedora upgrades and filesystem growth were not reversed; /srv/bc250-documents was preserved."
  ((FAILURES == 0))
}

main() {
  parse_arguments "$@"
  require_root
  discover_container_images
  discover_40cu_state
  confirm_reset
  stop_services
  restore_40cu_modules
  remove_profiles
  remove_containers
  remove_network_policy
  remove_official_ollama
  remove_main_package || exit 1
  remove_persistent_data
  finish
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
