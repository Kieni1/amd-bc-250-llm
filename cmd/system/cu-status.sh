#!/usr/bin/env bash
set -uo pipefail

manager="/usr/bin/bc250-cu-live-manager"

sum_live_manager_cus() {
  awk -F '|' '
    $2 ~ /^[[:space:]]*SE[0-9]+\.SH[0-9]+[[:space:]]*$/ {
      value = $10
      gsub(/[[:space:]]/, "", value)
      if (value ~ /^[0-9]+\/[0-9]+$/) {
        split(value, count, "/")
        active += count[1]
        total += count[2]
        rows++
      }
    }
    END {
      if (rows > 0)
        printf "%d/%d", active, total
    }
  '
}

read_param() {
  local path="$1"
  [[ -r "$path" ]] && cat "$path" || printf 'not exposed'
}

echo "BC-250 CU status"
echo "  Kernel active_cu_number : $(read_param /sys/module/amdgpu/parameters/active_cu_number)"
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
    routed="$(sum_live_manager_cus <<< "$output")"
    if [[ -n "$routed" ]]; then
      echo "  Live manager report     : CUs active & routed : $routed (summed from routing table)"
    else
      routed="$(grep -E 'CUs active[[:space:]]*& routed[[:space:]]*:' <<< "$output" | tail -1 | sed 's/^[[:space:]]*//')"
      [[ -z "$routed" ]] || echo "  Live manager report     : $routed"
    fi
    [[ -n "$routed" ]] || {
      echo "  Live manager report     : status could not be parsed"
      printf '%s\n' "$output" | tail -10 | sed 's/^/    /'
    }
  fi
else
  echo "  Live manager            : not installed"
fi

if command -v vulkaninfo >/dev/null 2>&1; then
  num_cu="$(RADV_DEBUG=info vulkaninfo --summary 2>&1 | grep -m1 -E 'num_cu[[:space:]]*=' | sed 's/^[[:space:]]*//' || true)"
  [[ -n "$num_cu" ]] && echo "  RADV report              : $num_cu" || echo "  RADV report              : num_cu not exposed by this build"
fi

echo "Note: a live-manager 40/40 routing report can coexist with a 24-CU kernel/RADV"
echo "enumeration. Validate with repeated compute benchmarks and correctness tests."
