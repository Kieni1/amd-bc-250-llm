#!/usr/bin/env bash
set -uo pipefail

manager="/usr/bin/bc250-cu-live-manager"
SUMMARY=0

case "${1:-}" in
  "") ;;
  --summary) SUMMARY=1 ;;
  -h|--help)
    echo "Usage: cu-status.sh [--summary]  # internal package helper"
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

echo "BC-250 CU status"
running_kernel="$(uname -r)"
echo "  Running kernel          : $running_kernel"
saved_profile_state="not configured"
saved_masks=""
if saved_raw="$(saved_mask_csv 2>/dev/null)"; then
  if saved_normalized="$(normalize_mask_csv "$saved_raw" 2>/dev/null)"; then
    read -r saved_masks _ <<< "$saved_normalized"
    saved_profile_state="configured"
    echo "  Saved boot profile      : configured ($saved_masks)"
  else
    saved_profile_state="invalid"
    echo "  Saved boot profile      : invalid (/etc/bc250-cu-live-manager.conf)"
  fi
else
  echo "  Saved boot profile      : not configured (optional)"
fi
if systemctl is-enabled --quiet bc250-cu-live-manager.service 2>/dev/null; then
  echo "  Restore profile at boot : enabled"
else
  echo "  Restore profile at boot : not enabled"
fi
if [[ -x "$manager" ]]; then
  echo "  Live routing manager    : $manager"
  if [[ ${EUID} -ne 0 ]]; then
    echo "  Live SPI-routed CUs     : not checked — run sudo bc250-40cu status"
    echo "  Live routing manager    : installed; root access required for routing registers"
  else
    output="$(timeout 30 "$manager" status 2>&1 || true)"
    if ((SUMMARY == 0)); then
      echo "  Live routing dashboard:"
      printf '%s\n' "$output" | grep -vE '^[[:space:]]*amdgpu[[:space:]]*:.*active_cu_number' | sed 's/^/    /'
    fi
    cells="$(routing_cells <<< "$output")"
    live_raw="$(routing_mask_csv <<< "$output")"
    live_masks=""
        if [[ -n "$live_raw" ]] && live_normalized="$(normalize_mask_csv "$live_raw" 2>/dev/null)"; then
      read -r live_masks _ <<< "$live_normalized"
      echo "  Live routing profile    : $live_masks"
    fi
    routed_cus="$(sed -n 's/.*CUs active & routed[[:space:]]*:[[:space:]]*//p' <<< "$output" | tail -1)"
    if [[ -n "$routed_cus" ]]; then
      echo "  Live SPI-routed CUs     : $routed_cus"
    else
      echo "  Live SPI-routed CUs     : not detected — additional CUs may be unlockable"
    fi
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
  echo "  Live SPI-routed CUs     : unavailable — live routing manager not installed"
  echo "  Live routing manager    : not installed"
fi

if ((SUMMARY == 0)); then
  echo "Note: Live SPI-routed CUs are the appliance CU-capacity signal; D! indicates an inconsistent routing cell."
  echo "If no live SPI-routed count is detected, additional CUs may be unlockable with: sudo bc250-cu-live-manager"
fi
