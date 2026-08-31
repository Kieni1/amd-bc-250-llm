#!/usr/bin/env bash
set -Eeuo pipefail

FULL_MEMORY_ARGS="amdgpu.gttsize=14750 ttm.pages_limit=4194304 ttm.page_pool_size=4194304 amdgpu.ppfeaturemask=0xffffffff"
PARAM_NAMES="amdgpu.gttsize ttm.pages_limit ttm.page_pool_size amdgpu.ppfeaturemask"

usage() {
  cat <<'USAGE'
Usage: bc250-memory-profile COMMAND [--quiet]

Commands:
  status       Show/verify active BC-250 memory and AMDGPU settings
  recommend    Print reviewed grubby commands without changing anything
  apply-full   Apply the reviewed BC-250 LLM memory/GPU profile to all kernels
  remove       Remove the BC-250 memory/GPU arguments from all kernels

Apply/remove commands require confirmation and never reboot automatically.
USAGE
}

require_root() {
  [[ ${EUID} -eq 0 ]] || { echo "ERROR: run this command with sudo." >&2; exit 1; }
  command -v grubby >/dev/null 2>&1 || { echo "ERROR: grubby is not installed." >&2; exit 1; }
}
read_param() { local path="$1"; [[ -r "$path" ]] && cat "$path" || printf 'not exposed'; }
has_cmdline() { tr " " "\n" < /proc/cmdline | grep -Fxq -- "$1"; }

status() {
  local quiet="${1:-}" bad=0 token
  for token in $FULL_MEMORY_ARGS; do has_cmdline "$token" || bad=1; done
  if [[ "$quiet" == --quiet ]]; then return "$bad"; fi
  echo "Kernel: $(uname -r)"
  echo "Command line: $(cat /proc/cmdline)"
  echo "amdgpu.gttsize: $(read_param /sys/module/amdgpu/parameters/gttsize)"
  echo "amdgpu.ppfeaturemask: $(read_param /sys/module/amdgpu/parameters/ppfeaturemask)"
  echo "ttm.pages_limit: $(read_param /sys/module/ttm/parameters/pages_limit)"
  echo "ttm.page_pool_size: $(read_param /sys/module/ttm/parameters/page_pool_size)"
  echo
  free -h || true; echo; swapon --show || true; echo
  df -h / /var/lib/bc250-llm-server 2>/dev/null | awk '!seen[$1]++'
  if ((bad)); then
    echo; echo "WARNING: the full reviewed BC-250 memory/GPU kernel profile is not active."
    echo "Expected: $FULL_MEMORY_ARGS"
  fi
  has_cmdline 'amd_iommu=on' && echo "WARNING: amd_iommu=on is unsafe on BC-250 community configurations."
  has_cmdline 'nomodeset' && echo "WARNING: nomodeset disables normal GPU acceleration after installation."
  return "$bad"
}

recommend() {
  cat <<EOF_REC
Reviewed BC-250 LLM profile:
  sudo grubby --update-kernel=ALL --remove-args="$PARAM_NAMES"
  sudo grubby --update-kernel=ALL --args="$FULL_MEMORY_ARGS"
  sudo reboot

The 14,750 MiB GTT value follows current BC-250 community guidance. The package
keeps its already-tested 4,194,304-page (16 GiB at 4 KiB/page) TTM limit/pool and
enables the full AMDGPU power-feature mask used by the governor tooling. These
parameters cap/address allocation; they do not reserve all 16 GiB at boot.
Do not add amd_iommu=on. Remove nomodeset after the installation phase.
EOF_REC
}
confirm() { local phrase="$1" answer; [[ "${BC250_ASSUME_YES:-0}" == 1 ]] && return 0; read -r -p "Type $phrase to continue: " answer; [[ "$answer" == "$phrase" ]] || { echo "Cancelled."; exit 0; }; }
apply_full() {
  require_root
  echo "Arguments: $FULL_MEMORY_ARGS"
  echo "This changes every installed kernel entry and requires a reboot."
  confirm APPLY-MEMORY-PROFILE
  grubby --update-kernel=ALL --remove-args="$PARAM_NAMES"
  grubby --update-kernel=ALL --args="$FULL_MEMORY_ARGS"
  echo "Updated all kernel entries. Reboot, then run: sudo bc250-memory-profile status"
}

command="${1:-status}"; shift || true
case "$command" in
  status) status "${1:-}" ;;
  recommend) recommend ;;
  apply-full) apply_full ;;
  remove)
    require_root; echo "This removes the BC-250 memory/GPU arguments from every kernel entry."
    confirm REMOVE-MEMORY-PROFILE
    grubby --update-kernel=ALL --remove-args="$PARAM_NAMES"
    echo "Arguments removed. Reboot to return to kernel defaults." ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 2 ;;
esac
