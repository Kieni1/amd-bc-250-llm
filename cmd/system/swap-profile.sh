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
  ensure   Idempotently ensure the reviewed zram + disk-swap profile
  apply    Confirm, then ensure the reviewed profile
  remove   Remove the package-managed zram override and disk swap file

Override sizes with SWAP_GIB and ZRAM_MIB. Optionally set SWAPPINESS to 0..200;
when unset, active swappiness policy is left alone.
USAGE
}

require_root() { [[ ${EUID} -eq 0 ]] || { echo "ERROR: run this command with sudo." >&2; exit 1; }; }
confirm() {
  local phrase="$1" answer
  [[ "${BC250_ASSUME_YES:-0}" == 1 ]] && return 0
  read -r -p "Type $phrase to continue: " answer
  [[ "$answer" == "$phrase" ]] || { echo "Cancelled."; exit 0; }
}

validate_settings() {
  [[ "$SWAP_GIB" =~ ^[1-9][0-9]*$ && "$ZRAM_MIB" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: SWAP_GIB and ZRAM_MIB must be positive integers." >&2; exit 2; }
  [[ -z "$SWAPPINESS" || ( "$SWAPPINESS" =~ ^[0-9]+$ && "$SWAPPINESS" -le 200 ) ]] || {
    echo "ERROR: SWAPPINESS must be an integer from 0 through 200." >&2; exit 2; }
  [[ -x /usr/lib/systemd/system-generators/zram-generator || \
     -x /usr/libexec/systemd/system-generators/zram-generator ]] || {
    echo "ERROR: systemd zram-generator is not installed." >&2; exit 1; }
}

profile_current() {
  local wanted_bytes
  wanted_bytes=$((SWAP_GIB * 1024 * 1024 * 1024))
  [[ -f "$SWAP_FILE" && "$(stat -c '%s' "$SWAP_FILE" 2>/dev/null || echo 0)" == "$wanted_bytes" ]] || return 1
  grep -Fxq "$FSTAB_BEGIN" /etc/fstab 2>/dev/null &&
    grep -Fxq "$SWAP_FILE none swap defaults,pri=10 0 0" /etc/fstab 2>/dev/null || return 1
  grep -Fxq "zram-size = $ZRAM_MIB" "$ZRAM_CONF" 2>/dev/null || return 1
  grep -Fxq "compression-algorithm = zstd" "$ZRAM_CONF" 2>/dev/null || return 1
  grep -Fxq "swap-priority = 100" "$ZRAM_CONF" 2>/dev/null || return 1
  if [[ -n "$SWAPPINESS" ]]; then
    grep -Fxq "vm.swappiness = $SWAPPINESS" "$SWAPPINESS_CONF" 2>/dev/null || return 1
    [[ "$(sysctl -n vm.swappiness 2>/dev/null || true)" == "$SWAPPINESS" ]] || return 1
  fi
  swapon --show=NAME --noheadings 2>/dev/null | grep -Fxq "$SWAP_FILE"
}

status() {
  [[ "${1:-}" == --quiet ]] && { profile_current; return; }
  echo "Configured zram override:"
  [[ -r "$ZRAM_CONF" ]] && cat "$ZRAM_CONF" || echo "  none"
  echo; zramctl 2>/dev/null || true
  echo; swapon --show || true
  echo; free -h || true
  [[ -e "$SWAP_FILE" ]] && { echo; ls -lh "$SWAP_FILE"; }
  echo; printf 'Active vm.swappiness: %s\n' "$(sysctl -n vm.swappiness 2>/dev/null || printf unknown)"
}

remove_fstab_block() {
  [[ -f /etc/fstab ]] || return 0
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

write_fstab_block() {
  remove_fstab_block
  cat >> /etc/fstab <<EOF_FSTAB
$FSTAB_BEGIN
$SWAP_FILE none swap defaults,pri=10 0 0
$FSTAB_END
EOF_FSTAB
}

write_zram() {
  install -d -m0755 "$(dirname "$ZRAM_CONF")"
  cat > "$ZRAM_CONF" <<EOF_ZRAM
[zram0]
zram-size = $ZRAM_MIB
compression-algorithm = zstd
swap-priority = 100
EOF_ZRAM
}

create_swapfile() {
  install -d -m0755 "$SWAP_DIR"
  local fstype
  fstype="$(findmnt -no FSTYPE --target "$SWAP_DIR")"
  if [[ "$fstype" == btrfs ]]; then
    command -v btrfs >/dev/null 2>&1 || { echo "ERROR: btrfs-progs is required for a Btrfs swap file." >&2; exit 1; }
    btrfs filesystem mkswapfile --size "${SWAP_GIB}G" "$SWAP_FILE"
  else
    fallocate -l "${SWAP_GIB}G" "$SWAP_FILE"
    chmod 0600 "$SWAP_FILE"
    mkswap "$SWAP_FILE" >/dev/null
  fi
}

ensure_capacity() {
  local available_kib required_kib
  available_kib="$(df --output=avail -k "$SWAP_DIR" 2>/dev/null | tail -1 || df --output=avail -k /var | tail -1)"
  required_kib=$((SWAP_GIB * 1024 * 1024 + 1024 * 1024))
  if [[ "$available_kib" =~ ^[0-9]+$ ]] && ((available_kib < required_kib)); then
    echo "ERROR: not enough free storage for a ${SWAP_GIB} GiB swap file plus headroom." >&2
    exit 1
  fi
}

ensure_swappiness() {
  [[ -n "$SWAPPINESS" ]] || return 0
  if [[ ! -e "$SWAPPINESS_CONF" && ! -e "$SWAPPINESS_STATE" ]]; then
    sysctl -n vm.swappiness > "$SWAPPINESS_STATE"
    chmod 0600 "$SWAPPINESS_STATE"
  fi
  install -d -m0755 "$(dirname "$SWAPPINESS_CONF")"
  printf '# Managed by bc250-swap-profile.\nvm.swappiness = %s\n' "$SWAPPINESS" > "$SWAPPINESS_CONF"
  sysctl --write "vm.swappiness=$SWAPPINESS" >/dev/null
}

ensure_profile() {
  require_root
  validate_settings
  install -d -m0755 "$SWAP_DIR"
  local wanted_bytes actual_bytes=0
  wanted_bytes=$((SWAP_GIB * 1024 * 1024 * 1024))
  [[ -f "$SWAP_FILE" ]] && actual_bytes="$(stat -c '%s' "$SWAP_FILE" 2>/dev/null || echo 0)"
  if [[ "$actual_bytes" != "$wanted_bytes" ]]; then
    ensure_capacity
    swapoff "$SWAP_FILE" 2>/dev/null || true
    rm -f "$SWAP_FILE"
    create_swapfile
  fi
  write_fstab_block
  if ! swapon --show=NAME --noheadings 2>/dev/null | grep -Fxq "$SWAP_FILE"; then
    if ! swapon "$SWAP_FILE"; then
      echo "Existing swap file is invalid; recreating it." >&2
      ensure_capacity
      rm -f "$SWAP_FILE"
      create_swapfile
      swapon "$SWAP_FILE"
    fi
  fi
  write_zram
  ensure_swappiness
  [[ -n "$SWAPPINESS" ]] || echo "vm.swappiness was left at the current system value."
  echo "Swap profile is configured; reboot if the zram size changed."
}

remove_profile() {
  require_root
  local previous_swappiness=""
  [[ -r "$SWAPPINESS_STATE" ]] && previous_swappiness="$(head -n 1 "$SWAPPINESS_STATE")"
  swapoff "$SWAP_FILE" 2>/dev/null || true
  remove_fstab_block
  rm -f "$SWAP_FILE" "$ZRAM_CONF" "$SWAPPINESS_CONF" "$SWAPPINESS_STATE"
  if [[ "$previous_swappiness" =~ ^[0-9]+$ && "$previous_swappiness" -le 200 ]]; then
    sysctl --write "vm.swappiness=$previous_swappiness" >/dev/null
  else
    sysctl --system >/dev/null
  fi
  echo "Swap profile removed. Reboot to restore Fedora's default zram configuration."
}

case "${1:-status}" in
  status) status "${2:-}" ;;
  ensure) ensure_profile ;;
  apply)
    require_root
    echo "This ensures a ${SWAP_GIB} GiB disk swap and ${ZRAM_MIB} MiB zram profile."
    confirm APPLY-SWAP-PROFILE
    ensure_profile
    ;;
  remove)
    require_root
    echo "This removes the package-managed disk swap and zram override."
    confirm REMOVE-SWAP-PROFILE
    remove_profile
    ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 2 ;;
esac
