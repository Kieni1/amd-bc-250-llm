#!/usr/bin/env bash
set -uo pipefail

manager="/usr/bin/bc250-cu-live-manager"
SUMMARY=0

case "${1:-}" in
  "") ;;
  --summary) SUMMARY=1 ;;
  -h|--help)
    echo "Usage: bc250-cu-status [--summary]"
    exit 0
    ;;
  *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
esac

routing_cells() {
  awk -F '|' '
    $2 ~ /^[[:space:]]*SE[0-9]+\.SH[0-9]+[[:space:]]*$/ {
      rows++
      for (i = 1; i <= NF; i++) {
        value = $i
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        if (value == "S+") spi++
        else if (value == "D+") driver++
        else if (value == "D!") driver_off++
        else if (value == "--") off++
      }
    }
    END {
      if (rows > 0) printf "%d %d %d %d", spi, driver, driver_off, off
    }
  '
}

read_param() {
  local path="$1"
  [[ -r "$path" ]] && cat "$path" || printf 'not exposed'
}

echo "BC-250 CU status"
running_kernel="$(uname -r)"
echo "  Running kernel          : $running_kernel"
prepared_file=/var/lib/bc250-llm-server/40cu/prepared
if [[ -r "$prepared_file" ]]; then
  prepared_kernel="$(sed -n 's/^kernel=//p' "$prepared_file" | head -1)"
  [[ "$prepared_kernel" == "$running_kernel" ]] && prepared_state="ready for running kernel" || \
    prepared_state="stale: prepared for ${prepared_kernel:-unknown}; rerun sudo bc250-40cu prepare"
  echo "  Prepared module state   : $prepared_state"
else
  echo "  Prepared module state   : not recorded"
fi
echo "  Kernel active_cu_number : $(read_param /sys/module/amdgpu/parameters/active_cu_number) (diagnostic counter)"
echo "  Kernel cc_write_mode    : $(read_param /sys/module/amdgpu/parameters/bc250_cc_write_mode)"
if grep -qo 'amdgpu.bc250_cc_write_mode=[^ ]*' /proc/cmdline 2>/dev/null; then
  echo "  Boot parameter          : $(grep -o 'amdgpu.bc250_cc_write_mode=[^ ]*' /proc/cmdline | head -1)"
else
  echo "  Boot parameter          : not present"
fi

if [[ -x "$manager" ]]; then
  echo "  Live manager            : $manager"
  if [[ ${EUID} -ne 0 ]]; then
    echo "  Live manager report     : run this command with sudo for register access"
  else
    output="$(timeout 30 "$manager" status 2>&1 || true)"
    if ((SUMMARY == 0)); then
      echo "  Live routing dashboard:"
      printf '%s\n' "$output" | sed 's/^/    /'
    fi
    cells="$(routing_cells <<< "$output")"
    routed_cus="$(sed -n 's/.*CUs active & routed[[:space:]]*:[[:space:]]*//p' <<< "$output" | tail -1)"
    [[ -n "$routed_cus" ]] && echo "  Live routed CUs         : $routed_cus"
    if [[ -n "$cells" ]]; then
      read -r spi driver driver_off off <<< "$cells"
      routed=$((spi + driver))
      problems=$((driver_off + off))
      ((SUMMARY)) || echo "  Live routing cells      : S+=$spi D+=$driver D!=$driver_off --=$off"
      if ((routed == 0)); then
        echo "  Live routing status     : no routed cells parsed"
      elif ((problems == 0)); then
        echo "  Live routing status     : routed entries present; no off/problem cells (healthy)"
      else
        echo "  Live routing status     : routed entries present; off/problem cells present ($problems)"
      fi
    else
      echo "  Live routing status     : routing table could not be parsed"
    fi
  fi
else
  echo "  Live manager            : not installed"
fi

if command -v vulkaninfo >/dev/null 2>&1; then
  num_cu="$(RADV_DEBUG=info vulkaninfo --summary 2>&1 | grep -m1 -E 'num_cu[[:space:]]*=' | sed 's/^[[:space:]]*//' || true)"
  [[ -n "$num_cu" ]] && echo "  RADV report              : $num_cu (diagnostic counter)" || echo "  RADV report              : num_cu not exposed by this build (diagnostic counter)"
fi

if ((SUMMARY == 0)); then
  echo "Note: kernel/RADV CU counts are diagnostic; judge live routing from the table"
  echo "and investigate D!/-- cells instead of requiring one universal CU total."
fi
