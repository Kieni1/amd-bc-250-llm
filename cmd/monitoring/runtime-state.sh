#!/usr/bin/env bash
# Shared read-only runtime-state helpers for BC-250 monitoring commands.
# This file is sourced by verify/status tooling and intentionally performs no
# actions when loaded.

bc250_active_swap_names() {
  local output
  output="$(swapon --show --noheadings --output NAME 2>/dev/null)" || return $?
  printf '%s\n' "$output"
}

bc250_active_zram_swap_names() {
  local swap_names
  swap_names="$(bc250_active_swap_names)" || return $?
  awk '$1 ~ /^\/dev\/zram[0-9]+$/ {print $1}' <<< "$swap_names"
}

bc250_failed_systemd_units() {
  local output rc
  output="$(systemctl list-units --state=failed --no-legend --plain --no-pager 2>/dev/null)"
  rc=$?
  ((rc == 0)) || return "$rc"
  awk 'NF {print $1}' <<< "$output"
}
