#!/usr/bin/env bash
# Configure and inspect the optional office-appliance maintenance schedule.
set -Eeuo pipefail
umask 0077

CONFIG="${BC250_MAINTENANCE_CONFIG:-/etc/bc250-llm-server/maintenance.env}"
EXAMPLE="${BC250_MAINTENANCE_EXAMPLE:-/usr/share/bc250-llm-server/examples/maintenance.env.example}"
POWER_DROPIN_DIR="${BC250_POWER_DROPIN_DIR:-/etc/systemd/system/bc250-night-shutdown.timer.d}"
POWER_DROPIN="$POWER_DROPIN_DIR/schedule.conf"

BACKUP_TIMERS=(owui-backup-config.timer owui-backup-users.timer)
OPTIONAL_TIMERS=(owui-prune.timer owui-warmup.timer bc250-night-shutdown.timer)
ALL_TIMERS=("${BACKUP_TIMERS[@]}" "${OPTIONAL_TIMERS[@]}")

usage() {
  cat <<'USAGE'
Usage: sudo bc250-maintenance setup [--defaults]
       sudo bc250-maintenance status
       sudo bc250-maintenance run backup|prune|all
       sudo bc250-maintenance disable

Set up and inspect privacy-conscious maintenance for the local office appliance.

  setup             Interactive setup for backups, upload pruning, optional
                    model warm-up and after-hours power saving.
  setup --defaults  Fast safe baseline: enable only verified local backups.
  status            Read-only schedule, storage and backup overview. The API
                    key is never printed.
  run backup        Run configuration and identity backups now, in sequence.
  run prune         Run the configured upload-prune policy now.
  run all           Run backups and then pruning.
  disable           Disable all optional maintenance and power timers. Data and
                    configuration are retained.

Local backups protect against application mistakes, not disk loss. Copy them
to encrypted storage controlled by the office for disaster recovery.
USAGE
}

require_root() {
  [[ ${EUID} -eq 0 ]] || {
    echo "ERROR: run this command with sudo." >&2
    exit 1
  }
}

systemd_available() {
  [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null 2>&1
}

ensure_config() {
  [[ -f "$CONFIG" ]] && return
  [[ -r "$EXAMPLE" ]] || {
    echo "ERROR: maintenance example is missing: $EXAMPLE" >&2
    exit 1
  }
  install -D -m0600 -- "$EXAMPLE" "$CONFIG"
}

get_setting() {
  local key="$1" fallback="${2:-}" value
  value="$(sed -n "s/^${key}=//p" "$CONFIG" 2>/dev/null | tail -n 1)"
  value="${value%\"}"
  value="${value#\"}"
  [[ -n "$value" ]] && printf '%s' "$value" || printf '%s' "$fallback"
}

set_setting() {
  local key="$1" value="$2" temporary
  [[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || {
    echo "ERROR: invalid setting name: $key" >&2
    exit 1
  }
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || {
    echo "ERROR: setting values cannot contain newlines." >&2
    exit 1
  }
  temporary="$(mktemp "${CONFIG}.XXXXXX")"
  awk -v key="$key" -v value="$value" '
    BEGIN { written=0 }
    $0 ~ "^" key "=" {
      if (!written) { print key "=" value; written=1 }
      next
    }
    { print }
    END { if (!written) print key "=" value }
  ' "$CONFIG" > "$temporary"
  install -m0600 -- "$temporary" "$CONFIG"
  rm -f -- "$temporary"
}

ask_yes_no() {
  local prompt="$1" default="$2" answer suffix
  if [[ "$default" == yes ]]; then suffix='[Y/n]'; else suffix='[y/N]'; fi
  read -r -p "$prompt $suffix: " answer
  answer="${answer,,}"
  [[ -z "$answer" ]] && answer="$default"
  [[ "$answer" == y || "$answer" == yes ]]
}

ask_value() {
  local prompt="$1" default="$2" answer
  read -r -p "$prompt [$default]: " answer
  printf '%s' "${answer:-$default}"
}

enable_units() {
  systemd_available || {
    echo "ERROR: systemd is not available on this host." >&2
    exit 1
  }
  systemctl enable --now "$@"
}

disable_units() {
  systemd_available || return 0
  systemctl disable --now "$@" >/dev/null 2>&1 || true
}

write_power_schedule() {
  local first="$1"
  [[ "$first" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || {
    echo "ERROR: power time must use 24-hour HH:MM." >&2
    exit 1
  }
  install -d -m0755 "$POWER_DROPIN_DIR"
  python3 - "$first" > "${POWER_DROPIN}.tmp" <<'PY_SCHEDULE'
import datetime
import sys

start = datetime.datetime.strptime(sys.argv[1], "%H:%M")
print("[Timer]")
print("OnCalendar=")
for offset in range(0, 61, 15):
    current = start + datetime.timedelta(minutes=offset)
    print(f"OnCalendar=Mon..Fri {current:%H:%M}:00")
PY_SCHEDULE
  install -m0644 "${POWER_DROPIN}.tmp" "$POWER_DROPIN"
  rm -f -- "${POWER_DROPIN}.tmp"
}

setup_pruning() {
  local token age ceiling
  if ! ask_yes_no "Configure upload pruning (starts in dry-run mode)" no; then
    disable_units owui-prune.timer
    return
  fi

  token="$(get_setting OWUI_API_KEY '')"
  if [[ -z "$token" || "$token" == REPLACE_WITH_ADMIN_API_KEY ]]; then
    read -r -s -p "Open WebUI administrator API key: " token
    echo
  elif ! ask_yes_no "Keep the existing stored Open WebUI API key" yes; then
    read -r -s -p "New Open WebUI administrator API key: " token
    echo
  fi
  [[ "$token" =~ ^[A-Za-z0-9._~+/=-]+$ ]] || {
    echo "ERROR: the API key is empty or contains unsupported characters." >&2
    exit 1
  }

  age="$(ask_value "Delete uploads older than this many days (0 disables age rule)" "$(get_setting MAX_AGE_DAYS 90)")"
  ceiling="$(ask_value "Maximum known upload storage in GiB (0 disables size rule)" "$(get_setting MAX_TOTAL_GB 20)")"
  [[ "$age" =~ ^[0-9]+$ && "$ceiling" =~ ^[0-9]+$ ]] || {
    echo "ERROR: pruning limits must be non-negative integers." >&2
    exit 1
  }
  ((age > 0 || ceiling > 0)) || {
    echo "ERROR: at least one pruning rule must be enabled." >&2
    exit 1
  }

  set_setting OWUI_API_KEY "$token"
  set_setting MAX_AGE_DAYS "$age"
  set_setting MAX_TOTAL_GB "$ceiling"
  set_setting DRY_RUN 1
  enable_units owui-prune.timer
  echo "Upload pruning is enabled in DRY_RUN=1 mode. Review a manual run before setting DRY_RUN=0."
}

setup_warmup() {
  local model keep
  if ! ask_yes_no "Warm a model before work (uses extra electricity)" no; then
    disable_units owui-warmup.timer
    return
  fi
  model="$(ask_value "Model name" "$(get_setting WARMUP_MODEL prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl)")"
  keep="$(ask_value "Keep model loaded after warm-up" "$(get_setting WARMUP_KEEP_ALIVE 15m)")"
  [[ "$model" =~ ^[A-Za-z0-9._:/-]+$ ]] || { echo "ERROR: invalid model name." >&2; exit 1; }
  [[ "$keep" =~ ^[0-9]+(s|m|h)$ ]] || { echo "ERROR: keep-alive must look like 30s, 15m or 1h." >&2; exit 1; }
  set_setting WARMUP_MODEL "$model"
  set_setting WARMUP_KEEP_ALIVE "$keep"
  enable_units owui-warmup.timer
}

setup_power() {
  local action time nic wol_tmp
  if ! ask_yes_no "Enable automatic after-hours power saving" no; then
    disable_units bc250-night-shutdown.timer
    return
  fi
  action="$(ask_value "Power action: poweroff or suspend" "$(get_setting NIGHT_POWER_ACTION poweroff)")"
  [[ "$action" == poweroff || "$action" == suspend ]] || {
    echo "ERROR: power action must be poweroff or suspend." >&2
    exit 1
  }
  time="$(ask_value "First weekday attempt (four retries follow at 15-minute intervals)" "18:30")"
  write_power_schedule "$time"
  set_setting NIGHT_POWER_ACTION "$action"

  if ask_yes_no "Configure Wake-on-LAN for this host" no; then
    nic="$(ip route show default 2>/dev/null | awk 'NR==1 {print $5}')"
    nic="$(ask_value "Network interface" "${nic:-enp4s0}")"
    [[ "$nic" =~ ^[A-Za-z0-9_.:-]+$ && -d "/sys/class/net/$nic" ]] || {
      echo "ERROR: network interface not found: $nic" >&2
      exit 1
    }
    wol_tmp="$(mktemp)"
    printf 'BC250_NIC=%s\n' "$nic" > "$wol_tmp"
    install -D -m0600 "$wol_tmp" /etc/default/bc250-wol
    rm -f -- "$wol_tmp"
    set_setting REQUIRE_WOL 1
    enable_units bc250-enable-wol.service
  else
    set_setting REQUIRE_WOL 0
    disable_units bc250-enable-wol.service
    echo "WARNING: arrange a manual, firmware-timed or external restart before relying on automatic $action."
  fi
  systemctl daemon-reload
  enable_units bc250-night-shutdown.timer
}

setup_interactive() {
  require_root
  ensure_config
  echo "BC-250 office maintenance setup"
  echo "The safe baseline keeps data local, does not auto-delete uploads and does not warm a model."
  if ask_yes_no "Enable daily verified local backups" yes; then
    enable_units "${BACKUP_TIMERS[@]}"
  else
    disable_units "${BACKUP_TIMERS[@]}"
  fi
  setup_pruning
  setup_warmup
  setup_power
  echo
  show_status
}

setup_defaults() {
  require_root
  ensure_config
  set_setting DRY_RUN 1
  disable_units "${OPTIONAL_TIMERS[@]}" bc250-enable-wol.service
  enable_units "${BACKUP_TIMERS[@]}"
  echo "Enabled verified local backups. Pruning, warm-up and automatic power actions remain disabled."
  show_status
}

timer_line() {
  local unit="$1" enabled active next last
  if ! systemd_available; then
    printf '  %-36s systemd unavailable\n' "$unit"
    return
  fi
  enabled="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
  active="$(systemctl is-active "$unit" 2>/dev/null || true)"
  next="$(systemctl show "$unit" -p NextElapseUSecRealtime --value 2>/dev/null || true)"
  last="$(systemctl show "$unit" -p LastTriggerUSec --value 2>/dev/null || true)"
  printf '  %-36s %-8s %-8s next=%s last=%s\n' "$unit" \
    "${enabled:-unknown}" "${active:-unknown}" "${next:-n/a}" "${last:-n/a}"
}

tree_usage() {
  local label="$1" path="$2" usage='missing'
  [[ -e "$path" ]] && usage="$(du -sh -- "$path" 2>/dev/null | awk '{print $1}' || printf '?')"
  printf '  %-20s %8s  %s\n' "$label" "$usage" "$path"
}

backup_summary() {
  local label="$1" directory="$2" pattern="$3" count=0 newest='none'
  if [[ -d "$directory" ]]; then
    count="$(find "$directory" -maxdepth 1 -type f -name "$pattern" -printf . 2>/dev/null | wc -c)"
    newest="$(find "$directory" -maxdepth 1 -type f -name "$pattern" -printf '%T@ %f\n' 2>/dev/null | sort -nr | head -n1 | cut -d' ' -f2- || true)"
    [[ -n "$newest" ]] || newest=none
  fi
  printf '  %-20s count=%-3s newest=%s\n' "$label" "$count" "$newest"
}

show_status() {
  local api_state='not configured' free_gb='unknown' min_free storage_probe
  if [[ -e "$CONFIG" && ! -r "$CONFIG" ]]; then
    echo "ERROR: maintenance configuration is private; run status with sudo." >&2
    return 1
  fi
  [[ -r "$CONFIG" ]] || {
    echo "Maintenance is not initialized. Run: sudo bc250-maintenance setup --defaults"
    return 0
  }
  [[ "$(get_setting OWUI_API_KEY '')" != REPLACE_WITH_ADMIN_API_KEY && -n "$(get_setting OWUI_API_KEY '')" ]] && api_state=configured
  min_free="$(get_setting MIN_FREE_GB 20)"

  echo "BC-250 maintenance status"
  echo
  echo "Schedules"
  for unit in "${ALL_TIMERS[@]}"; do timer_line "$unit"; done
  echo
  echo "Policy (API key redacted)"
  printf '  Backups kept:       config=%s users=%s\n' "$(get_setting KEEP_CONFIG 7)" "$(get_setting KEEP_USERS 14)"
  printf '  Upload pruning:     age=%sd ceiling=%sGiB dry_run=%s API_key=%s\n' \
    "$(get_setting MAX_AGE_DAYS 90)" "$(get_setting MAX_TOTAL_GB 20)" \
    "$(get_setting DRY_RUN 1)" "$api_state"
  printf '  Warm-up:            model=%s keep_alive=%s\n' \
    "$(get_setting WARMUP_MODEL prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl)" \
    "$(get_setting WARMUP_KEEP_ALIVE 15m)"
  printf '  Night power action: %s\n' "$(get_setting NIGHT_POWER_ACTION poweroff)"

  echo
  echo "Storage"
  df -h / 2>/dev/null | sed 's/^/  /'
  if [[ "$(get_setting MIN_FREE_GB 20)" =~ ^[0-9]+$ ]]; then
    storage_probe=/var/lib/bc250-llm-server
    [[ -d "$storage_probe" ]] || storage_probe=/
    free_gb="$(df -B1G --output=avail "$storage_probe" 2>/dev/null | awk 'NR==2 {gsub(/ /,""); print $1}')"
    if [[ "$free_gb" =~ ^[0-9]+$ && "$free_gb" -lt "$min_free" ]]; then
      printf '  WARNING: free storage is %sGiB; configured warning threshold is %sGiB.\n' "$free_gb" "$min_free"
    fi
  fi
  tree_usage "GGUF sources" /var/lib/bc250-llm-server/gguf
  tree_usage "Ollama stores" /var/lib/bc250-llm-server/ollama
  tree_usage "Hugging Face cache" /var/cache/bc250-llm-server/huggingface
  tree_usage "Open WebUI" /var/lib/open-webui
  tree_usage "Local backups" /var/backups/bc250-llm-server

  echo
  echo "Backups"
  backup_summary "Configuration" "$(get_setting CFG_OUT_DIR /var/backups/bc250-llm-server/config)" 'owui-config-*.tar.gz'
  backup_summary "Identity" "$(get_setting USERS_OUT_DIR /var/backups/bc250-llm-server/users)" 'owui-users-*.sql.gz'
  echo "  Local backups contain private office data and do not protect against failure of this disk."
}

run_task() {
  local instance="$1"
  systemd_available || { echo "ERROR: systemd is not available." >&2; exit 1; }
  echo "Running $instance..."
  if ! systemctl start "owui-maintenance@${instance}.service"; then
    journalctl -u "owui-maintenance@${instance}.service" -n 20 --no-pager || true
    return 1
  fi
  journalctl -u "owui-maintenance@${instance}.service" -n 20 --no-pager
}

run_selected() {
  require_root
  ensure_config
  case "${1:-}" in
    backup)
      run_task backup-config
      run_task backup-users
      ;;
    prune) run_task prune-uploads ;;
    all)
      run_task backup-config
      run_task backup-users
      run_task prune-uploads
      ;;
    *) echo "ERROR: run requires backup, prune or all." >&2; usage >&2; exit 2 ;;
  esac
}

disable_all() {
  require_root
  disable_units "${ALL_TIMERS[@]}" bc250-enable-wol.service
  echo "Disabled maintenance, warm-up, power and Wake-on-LAN schedules. Configuration and data were retained."
}

main() {
  case "${1:-status}" in
    setup)
      (($# <= 2)) || { usage >&2; exit 2; }
      case "${2:-}" in
        '') setup_interactive ;;
        --defaults) setup_defaults ;;
        -h|--help) usage ;;
        *) echo "ERROR: unknown setup option: $2" >&2; usage >&2; exit 2 ;;
      esac
      ;;
    status) (($# <= 1)) || { usage >&2; exit 2; }; show_status ;;
    run) (($# == 2)) || { usage >&2; exit 2; }; run_selected "$2" ;;
    disable) (($# == 1)) || { usage >&2; exit 2; }; disable_all ;;
    -h|--help|help) usage ;;
    *) echo "ERROR: unknown command: $1" >&2; usage >&2; exit 2 ;;
  esac
}

main "$@"
