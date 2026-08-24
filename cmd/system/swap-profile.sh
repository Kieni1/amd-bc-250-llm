#!/usr/bin/env bash
set -Eeuo pipefail

SWAP_GIB="${SWAP_GIB:-16}"
ZRAM_MIB="${ZRAM_MIB:-2048}"
SWAPPINESS="${SWAPPINESS:-}"
SWAP_DIR="/var/lib/bc250-llm-server/swap"
SWAP_FILE="$SWAP_DIR/bc250-llm.swap"
ZRAM_CONF="/etc/systemd/zram-generator.conf.d/90-bc250-llm-server.conf"
SWAPPINESS_CONF="/etc/sysctl.d/90-bc250-llm-server-swap.conf"
SWAPPINESS_STATE="$SWAP_DIR/swappiness.previous"
FSTAB_BEGIN="# BEGIN bc250-llm-server swap"
FSTAB_END="# END bc250-llm-server swap"

usage() {
  cat <<'USAGE'
Usage: bc250-swap-profile COMMAND

Commands:
  status   Show zram and disk swap
  apply    Configure 2 GiB zram after reboot and a 16 GiB NVMe swap file now
  remove   Remove the package-managed zram override and disk swap file

Override sizes with SWAP_GIB and ZRAM_MIB. Optionally set SWAPPINESS to an
integer from 0 through 200; if unset, the active system policy is left alone.
USAGE
}

require_root() {
  [[ ${EUID} -eq 0 ]] || { echo "ERROR: run this command with sudo." >&2; exit 1; }
}

confirm() {
  local phrase="$1"
  [[ "${BC250_ASSUME_YES:-0}" == 1 ]] && return 0
  read -r -p "Type $phrase to continue: " answer
  [[ "$answer" == "$phrase" ]] || { echo "Cancelled."; exit 0; }
}

status() {
  echo "Configured zram override:"
  if [[ -r "$ZRAM_CONF" ]]; then cat "$ZRAM_CONF"; else echo "  none"; fi
  echo
  zramctl 2>/dev/null || true
  echo
  swapon --show || true
  echo
  free -h || true
  [[ -e "$SWAP_FILE" ]] && ls -lh "$SWAP_FILE" || true
  echo
  printf 'Active vm.swappiness: %s\n' \
    "$(sysctl -n vm.swappiness 2>/dev/null || printf 'unknown')"
  echo "Package-managed swappiness override:"
  if [[ -r "$SWAPPINESS_CONF" ]]; then
    sed 's/^/  /' "$SWAPPINESS_CONF"
  else
    echo "  none"
  fi
}

remove_fstab_block() {
  local tmp
  tmp="$(mktemp)"
  awk -v begin="$FSTAB_BEGIN" -v end="$FSTAB_END" '
    $0 == begin {skip=1; next}
    $0 == end {skip=0; next}
    !skip {print}
  ' /etc/fstab > "$tmp"
  install -m0644 "$tmp" /etc/fstab
  rm -f "$tmp"
}

create_swapfile() {
  install -d -m0755 "$SWAP_DIR"
  local fstype
  fstype="$(findmnt -no FSTYPE --target "$SWAP_DIR")"

  if [[ "$fstype" == btrfs ]]; then
    command -v btrfs >/dev/null 2>&1 || {
      echo "ERROR: btrfs-progs is required for a Btrfs swap file." >&2
      exit 1
    }
    btrfs filesystem mkswapfile --size "${SWAP_GIB}G" "$SWAP_FILE"
  else
    fallocate -l "${SWAP_GIB}G" "$SWAP_FILE"
    chmod 0600 "$SWAP_FILE"
    mkswap "$SWAP_FILE" >/dev/null
  fi
}

case "${1:-status}" in
  status) status ;;
  apply)
    require_root
    [[ "$SWAP_GIB" =~ ^[1-9][0-9]*$ && "$ZRAM_MIB" =~ ^[1-9][0-9]*$ ]] || {
      echo "ERROR: SWAP_GIB and ZRAM_MIB must be positive integers." >&2
      exit 2
    }
    [[ -z "$SWAPPINESS" || \
       ( "$SWAPPINESS" =~ ^[0-9]+$ && "$SWAPPINESS" -le 200 ) ]] || {
      echo "ERROR: SWAPPINESS must be an integer from 0 through 200." >&2
      exit 2
    }
    [[ -x /usr/lib/systemd/system-generators/zram-generator || \
       -x /usr/libexec/systemd/system-generators/zram-generator ]] || {
      echo "ERROR: systemd zram-generator is not installed." >&2
      exit 1
    }
    available_kib="$(df --output=avail -k "$SWAP_DIR" 2>/dev/null | tail -1 || df --output=avail -k /var | tail -1)"
    required_kib=$((SWAP_GIB * 1024 * 1024 + 1024 * 1024))
    if [[ "$available_kib" =~ ^[0-9]+$ ]] && ((available_kib < required_kib)); then
      echo "ERROR: not enough free storage for a ${SWAP_GIB} GiB swap file plus headroom." >&2
      if [[ "$(findmnt -no FSTYPE --target / 2>/dev/null)" == xfs ]]; then
        echo "If the root device was already enlarged, run: sudo xfs_growfs /" >&2
      fi
      exit 1
    fi
    cat <<EOF_WARN
This creates $SWAP_FILE (${SWAP_GIB} GiB), enables it immediately and writes a
${ZRAM_MIB} MiB zram-generator override that takes effect after reboot.
Disk swap is a safety margin, not fast model memory, and increases NVMe writes.
EOF_WARN
    confirm APPLY-SWAP-PROFILE
    swapoff "$SWAP_FILE" 2>/dev/null || true
    rm -f "$SWAP_FILE"
    create_swapfile
    remove_fstab_block
    cat >> /etc/fstab <<EOF_FSTAB
$FSTAB_BEGIN
$SWAP_FILE none swap defaults,pri=10 0 0
$FSTAB_END
EOF_FSTAB
    swapon "$SWAP_FILE"
    install -d -m0755 "$(dirname "$ZRAM_CONF")"
    cat > "$ZRAM_CONF" <<EOF_ZRAM
[zram0]
zram-size = $ZRAM_MIB
compression-algorithm = zstd
swap-priority = 100
EOF_ZRAM
    if [[ -n "$SWAPPINESS" ]]; then
      if [[ ! -e "$SWAPPINESS_CONF" && ! -e "$SWAPPINESS_STATE" ]]; then
        sysctl -n vm.swappiness > "$SWAPPINESS_STATE"
        chmod 0600 "$SWAPPINESS_STATE"
      fi
      install -d -m0755 "$(dirname "$SWAPPINESS_CONF")"
      cat > "$SWAPPINESS_CONF" <<EOF_SWAPPINESS
# Managed by bc250-swap-profile; remove the profile to delete this override.
vm.swappiness = $SWAPPINESS
EOF_SWAPPINESS
      sysctl --write "vm.swappiness=$SWAPPINESS"
    elif [[ -r "$SWAPPINESS_CONF" ]]; then
      echo "Existing package-managed swappiness override was preserved."
    else
      echo "vm.swappiness was left at the current system value."
    fi
    echo "Swap profile applied. Reboot to resize zram, then run bc250-swap-profile status."
    ;;
  remove)
    require_root
    echo "This disables and deletes $SWAP_FILE and removes the zram and swappiness overrides."
    confirm REMOVE-SWAP-PROFILE
    previous_swappiness=""
    [[ -r "$SWAPPINESS_STATE" ]] && \
      previous_swappiness="$(head -n 1 "$SWAPPINESS_STATE")"
    swapoff "$SWAP_FILE" 2>/dev/null || true
    remove_fstab_block
    rm -f "$SWAP_FILE" "$ZRAM_CONF" "$SWAPPINESS_CONF" "$SWAPPINESS_STATE"
    if [[ "$previous_swappiness" =~ ^[0-9]+$ && "$previous_swappiness" -le 200 ]]; then
      sysctl --write "vm.swappiness=$previous_swappiness"
    else
      sysctl --system >/dev/null
    fi
    echo "Swap profile removed. Reboot to restore Fedora's default zram configuration."
    ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 2 ;;
esac
