#!/usr/bin/env bash
# Explicit full purge for the BC-250 LLM appliance setup.
set -Eeuo pipefail
umask 0022

readonly STATE_DIR="/var/lib/bc250-llm-server/install"
readonly FSTAB_BEGIN="# BEGIN bc250-llm-server swap"
readonly FSTAB_END="# END bc250-llm-server swap"
readonly MEMORY_ARGS="amdgpu.gttsize ttm.pages_limit ttm.page_pool_size amdgpu.ppfeaturemask"
ASSUME_YES="${BC250_ASSUME_YES:-0}"
FAILURES=0

declare -A PACKAGES=()
declare -A MODULE_TARGETS=()
declare -a CONTAINER_IMAGES=()

heading() {
  printf '\n===== %s =====\n' "$1"
}

warn() {
  printf 'WARNING: %s\n' "$*" >&2
}

failed() {
  warn "$*"
  FAILURES=$((FAILURES + 1))
}

usage() {
  cat <<'USAGE'
Usage: sudo bc250-uninstall [--yes]
       sudo ./uninstall.sh [--yes]

Permanently remove the BC-250 LLM RPM and setup-created state, including model
weights, Open WebUI data, backups, containers, Ollama instances, host profiles
and persistent 40-CU changes. --yes skips the PURGE-BC250-LLM confirmation.
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

require_root() {
  [[ ${EUID} -eq 0 ]] || {
    echo "ERROR: run this command with sudo." >&2
    exit 1
  }
}

read_state() {
  local name="$1" fallback="$2"
  if [[ -r "$STATE_DIR/$name" ]]; then
    head -n 1 "$STATE_DIR/$name"
  else
    printf '%s\n' "$fallback"
  fi
}

load_package_record() {
  local package
  if [[ -r "$STATE_DIR/packages-added.txt" ]]; then
    while IFS= read -r package; do
      [[ "$package" =~ ^[A-Za-z0-9+_.-]+$ ]] || {
        warn "ignoring invalid package record: $package"
        continue
      }
      [[ "$package" == bc250-llm-server ]] || PACKAGES["$package"]=1
    done < "$STATE_DIR/packages-added.txt"
  fi
}

discover_container_images() {
  local file image
  for file in \
      /usr/share/containers/systemd/open-webui.container \
      /usr/share/containers/systemd/tika.container; do
    [[ -r "$file" ]] || continue
    image="$(sed -n 's/^Image=//p' "$file" | head -n 1)"
    [[ -z "$image" ]] || CONTAINER_IMAGES+=("$image")
  done
}

discover_40cu_state() {
  local backup target relative kernel
  shopt -s nullglob
  for backup in \
      /usr/lib/modules/*/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko.bc250-backup-* \
      /usr/lib/modules/*/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko.xz.bc250-backup-* \
      /usr/lib/modules/*/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko.zst.bc250-backup-*; do
    target="${backup%.bc250-backup-*}"
    MODULE_TARGETS["$target"]=1
    relative="${target#/usr/lib/modules/}"
    kernel="${relative%%/*}"
    rpm -q "kernel-devel-$kernel" >/dev/null 2>&1 && \
      PACKAGES["kernel-devel-$kernel"]=1
  done
  shopt -u nullglob
}

confirm_purge() {
  cat <<'WARNING'
This permanently deletes:
  - all downloaded GGUF files, Ollama models and rendered Modelfiles;
  - Open WebUI accounts, settings, uploads and all appliance backups;
  - task/agent services, containers, caches and appliance configuration;
  - official Ollama installed by this setup and its service account;
  - memory, swap, CU boot routing and verified replacement-module changes;
  - RPM packages recorded as absent before the guided setup installed them.

Filesystem growth and Fedora upgrades cannot be reversed. A reboot is required
after purge to load the restored GPU module and kernel/zram defaults.
WARNING
  if ((${#PACKAGES[@]})); then
    echo
    echo "Recorded setup-added packages that are currently candidates for removal:"
    printf '  %s\n' "${!PACKAGES[@]}" | LC_ALL=C sort
  else
    echo
    echo "No setup-added package record is available; dependency packages will not be guessed."
  fi
  [[ "$ASSUME_YES" == 1 ]] && return
  local answer
  read -r -p "Type PURGE-BC250-LLM to continue: " answer
  [[ "$answer" == PURGE-BC250-LLM ]] || {
    echo "Cancelled."
    exit 0
  }
}

stop_services() {
  heading "1. STOP APPLIANCE SERVICES"
  systemctl disable --now \
    ollama-task.service ollama-agent.service \
    open-webui.service tika.service \
    cyan-skillfish-governor-smu.service \
    bc250-cu-live-manager.service \
    owui-backup-config.timer owui-backup-users.timer \
    owui-prune.timer owui-warmup.timer \
    bc250-night-shutdown.timer bc250-enable-wol.service \
    >/dev/null 2>&1 || true
  systemctl disable --now ollama.service >/dev/null 2>&1 || true
}

remove_live_manager_service() {
  systemctl disable --now bc250-cu-live-manager.service >/dev/null 2>&1 || true
  rm -f -- \
    /etc/systemd/system/bc250-cu-live-manager.service \
    /etc/systemd/system/multi-user.target.wants/bc250-cu-live-manager.service \
    /usr/local/bin/bc250-cu-live-manager \
    /var/usrlocal/bin/bc250-cu-live-manager \
    /etc/bc250-cu-live-manager.conf \
    /etc/udev/rules.d/99-bc250-cu-live-manager.rules
}

module_has_unlock() {
  local target="$1" file="$2"
  case "$target" in
    *.xz)
      xz --test "$file" >/dev/null 2>&1 || return 2
      xz --decompress --stdout "$file" | \
        LC_ALL=C grep -a 'bc250_cc_write_mode' >/dev/null
      ;;
    *.zst)
      zstd --test --quiet "$file" >/dev/null 2>&1 || return 2
      zstd --decompress --stdout --quiet "$file" | \
        LC_ALL=C grep -a 'bc250_cc_write_mode' >/dev/null
      ;;
    *) LC_ALL=C grep -a 'bc250_cc_write_mode' "$file" >/dev/null ;;
  esac
}

restore_40cu_modules() {
  heading "2. REMOVE 40-CU PERSISTENCE AND RESTORE AMDGPU"
  remove_live_manager_service
  rm -f -- \
    /etc/modprobe.d/bc250-40cu.conf \
    /etc/dracut.conf.d/90-bc250-40cu.conf

  local target backup stock status relative kernel
  local -a backups
  for target in "${!MODULE_TARGETS[@]}"; do
    shopt -s nullglob
    backups=( "${target}.bc250-backup-"* )
    shopt -u nullglob
    stock=""
    for backup in "${backups[@]}"; do
      if module_has_unlock "$target" "$backup"; then
        continue
      else
        status=$?
        if ((status == 1)); then
          stock="$backup"
          break
        fi
        warn "cannot verify AMDGPU backup: $backup"
      fi
    done
    if [[ -z "$stock" ]]; then
      failed "no verifiable stock AMDGPU backup for $target; backups were retained"
      continue
    fi

    echo "Restoring stock module: $target"
    if ! cp --preserve=mode,timestamps -- "$stock" "$target"; then
      failed "could not restore $stock to $target; backups were retained"
      continue
    fi
    rm -f -- "${backups[@]}" "${target}.bc250-new"
    relative="${target#/usr/lib/modules/}"
    kernel="${relative%%/*}"
    depmod -a "$kernel" || failed "depmod failed for kernel $kernel"
    dracut --force --kver "$kernel" || failed "initramfs rebuild failed for kernel $kernel"
  done

  shopt -s nullglob
  for target in \
      /usr/lib/modules/*/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko \
      /usr/lib/modules/*/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko.xz \
      /usr/lib/modules/*/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko.zst; do
    if module_has_unlock "$target" "$target"; then
      [[ -n "${MODULE_TARGETS[$target]:-}" ]] || \
        failed "patched AMDGPU module has no stock backup: $target"
    else
      status=$?
      ((status == 1)) || failed "could not verify installed AMDGPU module: $target"
    fi
  done
  shopt -u nullglob
  rm -rf -- /tmp/bc250-40cu-build
}

remove_fstab_swap_block() {
  [[ -f /etc/fstab ]] || return
  local temporary
  temporary="$(mktemp)"
  awk -v begin="$FSTAB_BEGIN" -v end="$FSTAB_END" '
    $0 == begin {skip=1; next}
    $0 == end {skip=0; next}
    !skip {print}
  ' /etc/fstab > "$temporary"
  install -m0644 "$temporary" /etc/fstab
  rm -f -- "$temporary"
}

remove_host_profiles() {
  heading "3. REMOVE MEMORY AND SWAP PROFILES"
  if command -v grubby >/dev/null 2>&1; then
    grubby --update-kernel=ALL --remove-args="$MEMORY_ARGS" || \
      failed "could not remove BC-250 kernel arguments"
  else
    failed "grubby is missing; kernel memory arguments were not removed"
  fi
  swapoff /var/lib/bc250-llm-server/swap/bc250-llm.swap >/dev/null 2>&1 || true
  remove_fstab_swap_block
  rm -f -- \
    /var/lib/bc250-llm-server/swap/bc250-llm.swap \
    /etc/systemd/zram-generator.conf.d/90-bc250-llm-server.conf
  rmdir /etc/systemd/zram-generator.conf.d >/dev/null 2>&1 || true
}

remove_containers() {
  heading "4. REMOVE APPLIANCE CONTAINERS"
  command -v podman >/dev/null 2>&1 || return
  local container image
  for container in open-webui tika; do
    podman container exists "$container" 2>/dev/null || continue
    podman rm --force "$container" || failed "could not remove container $container"
  done
  if podman network exists llm 2>/dev/null; then
    podman network rm llm || failed "could not remove Podman network llm"
  fi
  for image in "${CONTAINER_IMAGES[@]}"; do
    podman image exists "$image" 2>/dev/null || continue
    podman image rm "$image" || failed "could not remove image $image (it may be used elsewhere)"
  done
}

restore_network_policy() {
  heading "5. RESTORE NETWORK POLICY"
  local firewall_before selinux_before
  firewall_before="$(read_state firewall-http-before unknown)"
  selinux_before="$(read_state selinux-httpd-before unknown)"

  if [[ "$firewall_before" != enabled ]] && command -v firewall-cmd >/dev/null 2>&1; then
    if systemctl is-active --quiet firewalld.service; then
      firewall-cmd --quiet --permanent --remove-service=http >/dev/null 2>&1 || true
      firewall-cmd --quiet --reload >/dev/null 2>&1 || \
        failed "firewalld could not reload after removing HTTP access"
    else
      warn "firewalld is inactive; verify that permanent HTTP access is removed"
    fi
  fi
  if [[ "$selinux_before" != on ]] && command -v setsebool >/dev/null 2>&1; then
    setsebool -P httpd_can_network_connect 0 || \
      failed "could not restore the SELinux network boolean"
  fi
}

remove_main_package() {
  heading "6. REMOVE BC-250 RPM"
  rpm -q bc250-llm-server.x86_64 >/dev/null 2>&1 || {
    echo "bc250-llm-server.x86_64 is already absent."
    return 0
  }
  # Normal DNF dependency cleanup removes requirements that are no longer used.
  # Direct setup additions are handled separately from the recorded package set.
  dnf remove -y bc250-llm-server.x86_64
}

remove_recorded_packages() {
  heading "7. REMOVE RECORDED SETUP PACKAGES"
  if rpm -q ollama >/dev/null 2>&1; then
    PACKAGES[ollama]=1
  fi
  local package
  local -a installed=()
  for package in "${!PACKAGES[@]}"; do
    rpm -q "$package" >/dev/null 2>&1 && installed+=("$package")
  done
  if ((${#installed[@]} == 0)); then
    echo "No recorded setup-added RPM remains installed."
    return
  fi
  printf 'Removing recorded package: %s\n' "${installed[@]}"
  dnf remove -y "${installed[@]}" || \
    failed "DNF could not remove every recorded setup-added package"
}

remove_official_ollama() {
  heading "8. REMOVE OFFICIAL OLLAMA"
  local path
  rm -f -- \
    /etc/systemd/system/ollama.service \
    /etc/systemd/system/multi-user.target.wants/ollama.service
  rm -rf -- /etc/systemd/system/ollama.service.d

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

remove_setup_files() {
  heading "9. REMOVE APPLIANCE DATA AND LOCAL FILES"
  systemctl disable --now ollama-task.service ollama-agent.service >/dev/null 2>&1 || true
  rm -f -- \
    /etc/systemd/system/ollama-task.service \
    /etc/systemd/system/ollama-agent.service \
    /etc/systemd/system/multi-user.target.wants/ollama-task.service \
    /etc/systemd/system/multi-user.target.wants/ollama-agent.service \
    /etc/systemd/system/bc250-enable-wol.service \
    /etc/systemd/system/bc250-night-shutdown.service \
    /etc/systemd/system/bc250-night-shutdown.timer \
    /etc/systemd/system/owui-backup-config.timer \
    /etc/systemd/system/owui-backup-users.timer \
    /etc/systemd/system/owui-prune.timer \
    /etc/systemd/system/owui-warmup.service \
    /etc/systemd/system/owui-warmup.timer \
    /etc/systemd/system/owui-maintenance@.service \
    /etc/default/bc250-wol \
    /etc/containers/systemd/open-webui.container \
    /etc/containers/systemd/tika.container \
    /etc/containers/systemd/llm.network \
    /etc/nginx/default.d/bc250-llm-server.conf \
    /etc/nginx/default.d/bc250-llm-server.conf.rpmnew \
    /etc/nginx/default.d/bc250-llm-server.conf.rpmsave \
    /etc/nginx/conf.d/00-bc250-websocket-map.conf \
    /etc/nginx/conf.d/00-bc250-websocket-map.conf.rpmnew \
    /etc/nginx/conf.d/00-bc250-websocket-map.conf.rpmsave \
    /var/log/bc250-llm-install.log
  rm -rf -- \
    /etc/bc250-llm-server \
    /etc/cyan-skillfish-governor-smu \
    /var/lib/bc250-llm-server \
    /var/cache/bc250-llm-server \
    /var/lib/open-webui \
    /var/backups/bc250-llm-server

  loginctl terminate-user ollama >/dev/null 2>&1 || true
  id ollama >/dev/null 2>&1 && userdel ollama || true
  getent group ollama >/dev/null 2>&1 && groupdel ollama || true
}

finish() {
  systemctl daemon-reload
  systemctl reset-failed >/dev/null 2>&1 || true
  command -v nginx >/dev/null 2>&1 && systemctl reload nginx.service >/dev/null 2>&1 || true
  echo
  if ((FAILURES)); then
    echo "Purge completed with $FAILURES warning(s). Review the messages above." >&2
  else
    echo "BC-250 LLM setup and persistent appliance data were removed."
  fi
  echo "Reboot now to load stock GPU, memory and zram state: sudo reboot"
  echo "Root-filesystem growth and Fedora system upgrades were not reversed."
  ((FAILURES == 0))
}

main() {
  parse_arguments "$@"
  require_root
  load_package_record
  discover_container_images
  discover_40cu_state
  confirm_purge
  stop_services
  restore_40cu_modules
  remove_host_profiles
  remove_containers
  restore_network_policy
  remove_main_package || {
    echo "ERROR: the main RPM could not be removed; stopping before deleting its files." >&2
    exit 1
  }
  remove_recorded_packages
  remove_official_ollama
  remove_setup_files
  finish
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
