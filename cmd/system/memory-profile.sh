#!/usr/bin/env bash
set -Eeuo pipefail

FULL_MEMORY_ARGS="ttm.pages_limit=4194304 ttm.page_pool_size=4194304"
PARAM_NAMES="amdgpu.gttsize ttm.pages_limit ttm.page_pool_size amdgpu.ppfeaturemask"
LEGACY_ARG_PREFIXES="amdgpu.gttsize= amdgpu.ppfeaturemask="

usage() {
  cat <<'USAGE'
Usage: bc250-memory-profile COMMAND [--quiet]

Commands:
  status       Show/verify the active BC-250 TTM profile
  ensure       Idempotently configure the reviewed profile on all kernel entries
  recommend    Print the equivalent grubby commands
  apply-full   Confirm, then configure the reviewed profile on all kernel entries
  remove       Remove BC-250 memory/GPU arguments from all kernel entries

Configuration changes never reboot automatically.
USAGE
}

require_root() {
  [[ ${EUID} -eq 0 ]] || { echo "ERROR: run this command with sudo." >&2; exit 1; }
  command -v grubby >/dev/null 2>&1 || { echo "ERROR: grubby is not installed." >&2; exit 1; }
}

read_param() { local path="$1"; [[ -r "$path" ]] && cat "$path" || printf 'not exposed'; }
has_cmdline() { tr ' ' '\n' < /proc/cmdline | grep -Fxq -- "$1"; }

configured() {
  command -v grubby >/dev/null 2>&1 || return 1
  local args token seen=0
  while IFS= read -r args; do
    [[ -n "$args" ]] || return 1
    seen=1
    for token in $FULL_MEMORY_ARGS; do
      case " $args " in *" $token "*) ;; *) return 1 ;; esac
    done
    case " $args " in
      *" amdgpu.gttsize="*|*" amdgpu.ppfeaturemask="*) return 1 ;;
    esac
  done < <(grubby --info=ALL 2>/dev/null | sed -n 's/^args="\(.*\)"$/\1/p')
  ((seen))
}

status() {
  local quiet="${1:-}" bad=0 token
  for token in $FULL_MEMORY_ARGS; do has_cmdline "$token" || bad=1; done
  for token in $LEGACY_ARG_PREFIXES; do
    grep -qE "(^| )${token//./\.}[^ ]*( |$)" /proc/cmdline && bad=1
  done
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
    echo; echo "WARNING: the reviewed BC-250 TTM profile is not active or legacy overrides remain."
    echo "Expected: $FULL_MEMORY_ARGS"
  fi
  has_cmdline amd_iommu=on && echo "WARNING: amd_iommu=on is unsafe on BC-250 community configurations."
  has_cmdline nomodeset && echo "WARNING: nomodeset disables normal GPU acceleration after installation."
  return "$bad"
}

set_profile() {
  grubby --update-kernel=ALL --remove-args="$PARAM_NAMES"
  grubby --update-kernel=ALL --args="$FULL_MEMORY_ARGS"
}

ensure_profile() {
  require_root
  if configured; then
    echo "BC-250 TTM profile is already configured on all kernel entries."
  else
    set_profile
    echo "Configured the BC-250 TTM profile on all kernel entries."
  fi
  status --quiet || echo "Profile is configured but requires a reboot to become active."
}

recommend() {
  cat <<EOF_REC
Reviewed BC-250 LLM profile:
  sudo grubby --update-kernel=ALL --remove-args="$PARAM_NAMES"
  sudo grubby --update-kernel=ALL --args="$FULL_MEMORY_ARGS"
  sudo reboot

Fedora 44/kernel 7.1 BC-250 revalidation kept the TTM-only profile; deprecated
amdgpu.gttsize and explicit amdgpu.ppfeaturemask overrides are not defaults.
Do not add amd_iommu=on. Remove nomodeset after installation.
EOF_REC
}

confirm() {
  local phrase="$1" answer
  [[ "${BC250_ASSUME_YES:-0}" == 1 ]] && return 0
  read -r -p "Type $phrase to continue: " answer
  [[ "$answer" == "$phrase" ]] || { echo "Cancelled."; exit 0; }
}

command="${1:-status}"; shift || true
case "$command" in
  status) status "${1:-}" ;;
  ensure) ensure_profile ;;
  recommend) recommend ;;
  apply-full)
    require_root
    echo "This configures every installed kernel entry and requires a reboot."
    confirm APPLY-MEMORY-PROFILE
    ensure_profile
    ;;
  remove)
    require_root
    echo "This removes the BC-250 memory/GPU arguments from every kernel entry."
    confirm REMOVE-MEMORY-PROFILE
    grubby --update-kernel=ALL --remove-args="$PARAM_NAMES"
    echo "Arguments removed. Reboot to return to kernel defaults."
    ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 2 ;;
esac
