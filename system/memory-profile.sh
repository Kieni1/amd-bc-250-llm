#!/usr/bin/env bash
set -Eeuo pipefail

FULL_TTM_ARGS="ttm.pages_limit=4194304"
PARAM_NAMES="amdgpu.gttsize ttm.pages_limit ttm.page_pool_size amdgpu.ppfeaturemask"

usage() {
  cat <<'USAGE'
Usage: bc250-memory-profile COMMAND

Commands:
  status       Show active kernel memory settings and available space
  recommend    Print reviewed grubby commands without changing anything
  apply-full   Apply the reviewed 16 GiB TTM limit to all kernels
  apply-safe   Alias for apply-full, retained for existing automation
  remove       Remove current and legacy BC-250 memory arguments

Apply/remove commands require confirmation and never reboot automatically.
USAGE
}

require_root() {
  [[ ${EUID} -eq 0 ]] || { echo "ERROR: run this command with sudo." >&2; exit 1; }
  command -v grubby >/dev/null 2>&1 || { echo "ERROR: grubby is not installed." >&2; exit 1; }
}

read_param() {
  local path="$1"
  [[ -r "$path" ]] && cat "$path" || printf 'not exposed'
}

status() {
  echo "Kernel: $(uname -r)"
  echo "Command line: $(cat /proc/cmdline)"
  echo "amdgpu.gttsize: $(read_param /sys/module/amdgpu/parameters/gttsize)"
  echo "ttm.pages_limit: $(read_param /sys/module/ttm/parameters/pages_limit)"
  echo "ttm.page_pool_size: $(read_param /sys/module/ttm/parameters/page_pool_size)"
  echo
  free -h || true
  echo
  swapon --show || true
  echo
  df -h / /var/llm 2>/dev/null | awk '!seen[$1]++'

  if ! grep -qw 'ttm.pages_limit=4194304' /proc/cmdline; then
    echo
    echo "WARNING: the reviewed 16 GiB TTM pages_limit is not active."
  fi
  for legacy in amdgpu.gttsize ttm.page_pool_size amdgpu.ppfeaturemask; do
    grep -qE "(^| )${legacy}=" /proc/cmdline &&
      echo "WARNING: obsolete argument remains active: $legacy"
  done
}

recommend() {
  cat <<EOF_REC
Reviewed full-TTM profile:
  sudo grubby --update-kernel=ALL --remove-args="$PARAM_NAMES"
  sudo grubby --update-kernel=ALL --args="$FULL_TTM_ARGS"
  sudo reboot

This sets the TTM allocation cap to 4,194,304 pages (16 GiB with 4 KiB pages).
It does not reserve all memory at boot. Verify the active value, swap, model
stability and free host memory after reboot.
EOF_REC
}

confirm() {
  local phrase="$1"
  [[ "${BC250_ASSUME_YES:-0}" == 1 ]] && return 0
  read -r -p "Type $phrase to continue: " answer
  [[ "$answer" == "$phrase" ]] || { echo "Cancelled."; exit 0; }
}

apply_full() {
  require_root
  echo "Arguments: $FULL_TTM_ARGS"
  echo "This changes every installed kernel entry and requires a reboot."
  confirm APPLY-MEMORY-PROFILE
  grubby --update-kernel=ALL --remove-args="$PARAM_NAMES"
  grubby --update-kernel=ALL --args="$FULL_TTM_ARGS"
  echo "Updated all kernel entries. Reboot, then run: sudo bc250-memory-profile status"
}

case "${1:-status}" in
  status) status ;;
  recommend) recommend ;;
  apply-full|apply-safe) apply_full ;;
  remove)
    require_root
    echo "This removes current and legacy BC-250 memory arguments from every kernel entry."
    confirm REMOVE-MEMORY-PROFILE
    grubby --update-kernel=ALL --remove-args="$PARAM_NAMES"
    echo "Arguments removed. Reboot to return to kernel defaults."
    ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 2 ;;
esac
