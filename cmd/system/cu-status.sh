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

routing_mask_csv() {
  awk -F '|' '
    $2 ~ /^[[:space:]]*SE[0-9]+\.SH[0-9]+[[:space:]]*$/ {
      value = $8
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      if (value !~ /^0x[0-9a-fA-F]+$/) bad=1
      masks[rows++] = value
    }
    END {
      if (!bad && rows == 4) printf "%s,%s,%s,%s", masks[0], masks[1], masks[2], masks[3]
    }
  '
}

normalize_mask_csv() {
  local csv="$1" idx item value bit total=0 joined
  local -a raw normalized
  IFS=',' read -r -a raw <<< "$csv"
  ((${#raw[@]} == 4)) || return 1
  for idx in 0 1 2 3; do
    item="${raw[$idx]}"
    [[ "$item" =~ ^(0x[0-9a-fA-F]+|[0-9]+)$ ]] || return 1
    value=$((item))
    ((value >= 0 && value <= 31)) || return 1
    normalized+=("$(printf '0x%02x' "$value")")
    for bit in 0 1 2 3 4; do
      ((value & (1 << bit))) && total=$((total + 2))
    done
  done
  joined="$(IFS=,; printf '%s' "${normalized[*]}")"
  printf '%s %d' "$joined" "$total"
}

saved_mask_csv() {
  local conf="/etc/bc250-cu-live-manager.conf"
  [[ -r "$conf" ]] || return 1
  sed -n 's/^BC250_WGP_MASKS=//p' "$conf" | head -1
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
  echo "  CU-routing-capable module : $prepared_state"
elif ((EUID != 0)) && [[ -d /var/lib/bc250-llm-server ]] && [[ ! -x /var/lib/bc250-llm-server ]]; then
  echo "  CU-routing-capable module : protected; run with sudo for package state"
else
  echo "  CU-routing-capable module : not prepared"
fi
echo "  Kernel diagnostic active_cu_number : $(read_param /sys/module/amdgpu/parameters/active_cu_number) (not live-routing authority)"
echo "  Kernel cc_write_mode    : $(read_param /sys/module/amdgpu/parameters/bc250_cc_write_mode)"
if grep -qo 'amdgpu.bc250_cc_write_mode=[^ ]*' /proc/cmdline 2>/dev/null; then
  echo "  Boot parameter          : $(grep -o 'amdgpu.bc250_cc_write_mode=[^ ]*' /proc/cmdline | head -1)"
else
  echo "  Boot parameter          : not present"
fi
saved_profile_state="not configured"
saved_masks=""
saved_cus=""
if saved_raw="$(saved_mask_csv 2>/dev/null)"; then
  if saved_normalized="$(normalize_mask_csv "$saved_raw" 2>/dev/null)"; then
    read -r saved_masks saved_cus <<< "$saved_normalized"
    saved_profile_state="configured"
    echo "  Saved live profile      : $saved_masks"
    echo "  Configured live profile : ${saved_cus}/40"
  else
    saved_profile_state="invalid"
    echo "  Saved live profile      : invalid (/etc/bc250-cu-live-manager.conf)"
    echo "  Configured live profile : invalid"
  fi
else
  echo "  Saved live profile      : not configured"
  echo "  Configured live profile : NOT CONFIGURED (optional)"
fi
if systemctl is-enabled --quiet bc250-cu-live-manager.service 2>/dev/null; then
  echo "  Restore profile at boot : enabled"
else
  echo "  Restore profile at boot : not enabled"
fi
if [[ -f /etc/modprobe.d/bc250-40cu.conf ]]; then
  echo "  Persistent patched-module activation : configured"
else
  echo "  Persistent patched-module activation : not configured (optional)"
fi

if [[ -x "$manager" ]]; then
  echo "  Live routing manager    : $manager"
  if [[ ${EUID} -ne 0 ]]; then
    echo "  Live routing manager    : installed; run with sudo for register access"
  else
    output="$(timeout 30 "$manager" status 2>&1 || true)"
    if ((SUMMARY == 0)); then
      echo "  Live routing dashboard:"
      printf '%s\n' "$output" | sed 's/^/    /'
    fi
    cells="$(routing_cells <<< "$output")"
    live_raw="$(routing_mask_csv <<< "$output")"
    live_masks=""
    live_cus=""
    if [[ -n "$live_raw" ]] && live_normalized="$(normalize_mask_csv "$live_raw" 2>/dev/null)"; then
      read -r live_masks live_cus <<< "$live_normalized"
      echo "  Live routing profile    : ${live_cus}/40 ($live_masks)"
    fi
    routed_cus="$(sed -n 's/.*CUs active & routed[[:space:]]*:[[:space:]]*//p' <<< "$output" | tail -1)"
    [[ -n "$routed_cus" ]] && echo "  Live routed CUs         : $routed_cus"
    if [[ -n "$cells" ]]; then
      read -r spi driver driver_off off <<< "$cells"
      problems=$driver_off
      ((SUMMARY)) || echo "  Live routing cells      : S+=$spi D+=$driver D!=$driver_off --=$off"
      echo "  Problem cells           : $problems"
      if [[ -z "$live_masks" ]]; then
        echo "  Routing profile match   : unavailable"
        echo "  Live routing status     : routing layout could not be parsed"
      elif [[ "$saved_profile_state" == "invalid" ]]; then
        echo "  Routing profile match   : invalid saved profile"
        echo "  Live routing status     : saved profile is invalid; rewrite it with the live manager"
      elif [[ "$saved_profile_state" == "not configured" ]]; then
        echo "  Routing profile match   : not configured"
        if ((problems == 0)); then
          echo "  Live routing status     : live layout parsed; no saved profile configured (optional)"
        else
          echo "  Live routing status     : unexpected/inconsistent cells present ($problems)"
        fi
      elif [[ "$live_masks" == "$saved_masks" ]]; then
        echo "  Routing profile match   : exact"
        if ((problems == 0)); then
          echo "  Live routing status     : configured profile routed exactly"
        else
          echo "  Live routing status     : configured masks match, but D! cells are inconsistent ($problems)"
        fi
      else
        echo "  Routing profile match   : mismatch"
        echo "  Live routing status     : live layout differs from saved profile"
      fi
    else
      echo "  Routing profile match   : unavailable"
      echo "  Live routing status     : routing table could not be parsed"
    fi
  fi
else
  echo "  Live routing manager    : not installed"
fi

if command -v vulkaninfo >/dev/null 2>&1; then
  num_cu="$(RADV_DEBUG=info vulkaninfo --summary 2>&1 | grep -m1 -E 'num_cu[[:space:]]*=' | sed 's/^[[:space:]]*//' || true)"
  [[ -n "$num_cu" ]] && echo "  RADV-reported CU count   : ${num_cu#*=} (diagnostic only; not live-routing authority)" || echo "  RADV-reported CU count   : not exposed (diagnostic only; not live-routing authority)"
fi

if ((SUMMARY == 0)); then
  echo "Note: D+/S+ are active/routed, -- is intentionally disabled/not selected, and D! is unexpected/inconsistent."
  echo "Stable CU count/layout varies by device; kernel/RADV counts are diagnostic only."
fi
