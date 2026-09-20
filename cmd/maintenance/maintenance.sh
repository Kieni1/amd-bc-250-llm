#!/usr/bin/env bash
# Configure and inspect the optional office-appliance maintenance schedule.
set -Eeuo pipefail
umask 0077

CONFIG="${BC250_MAINTENANCE_CONFIG:-/etc/bc250-llm-server/maintenance.env}"
EXAMPLE="${BC250_MAINTENANCE_EXAMPLE:-/usr/share/bc250-llm-server/examples/maintenance.env.example}"
POWER_DROPIN_DIR="${BC250_POWER_DROPIN_DIR:-/etc/systemd/system/bc250-night-shutdown.timer.d}"
POWER_DROPIN="$POWER_DROPIN_DIR/schedule.conf"
CONTRACT_DOC="${BC250_MAINTENANCE_CONTRACT:-/usr/share/doc/bc250-llm-server/docs/MAINTENANCE-CONTRACT.md}"
ACCESS_HELPER="${BC250_MAINTENANCE_ACCESS_HELPER:-/usr/libexec/bc250-llm-server/maintenance-companion.sh}"
SAFE_POWER_HELPER="${BC250_SAFE_POWER_HELPER:-/usr/libexec/bc250-llm-server/safe-power.sh}"
POWER_CONTROL_USER="${BC250_POWER_CONTROL_USER:-bc250-power-control}"

BACKUP_TIMERS=(owui-backup-config.timer owui-backup-users.timer)
OPTIONAL_TIMERS=(owui-prune.timer owui-warmup.timer bc250-night-shutdown.timer)
ALL_TIMERS=("${BACKUP_TIMERS[@]}" "${OPTIONAL_TIMERS[@]}")

usage() {
  cat <<'USAGE'
Usage: sudo bc250-maintenance setup [--defaults]
       sudo bc250-maintenance status
       sudo bc250-maintenance contract
       sudo bc250-maintenance companion status|enable
       sudo bc250-maintenance backup-export status|enable
       sudo bc250-maintenance request-shutdown
       sudo bc250-maintenance run backup|prune|all
       sudo bc250-maintenance clean-cache
       sudo bc250-maintenance disable

Set up and inspect privacy-conscious maintenance for the local office appliance.

  setup             Interactive setup for backups, upload pruning, optional
                    model warm-up and after-hours power saving.
  setup --defaults  Fast safe baseline: enable only verified local backups.
  status            Read-only schedule and backup overview. The API key is
                    never printed; bc250-status shows appliance storage.
  contract          Print the BC-250/Pi maintenance interface contract.
  companion         Inspect or prepare restricted Pi maintenance access over
                    SSH for safe shutdown requests. HTTP remains the office UI.
  backup-export     Inspect or prepare optional read-only rrsync backup export.
  request-shutdown  Ask the package safe-power policy to power off only if idle.
  run backup        Run configuration and identity backups now, in sequence.
  run prune         Run the configured upload-prune policy now.
  run all           Run backups and then pruning.
  clean-cache       Confirm removal of the Hugging Face cache, dangling Podman
                    images and old system-wide journal archives; models/data stay.
  disable           Disable all optional maintenance and power timers. Data and
                    configuration are retained.

Local backups protect against application mistakes, not disk loss. Optional
Pi export can copy them off-device later; it is not required for normal office use.
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
  while true; do
    read -r -p "$prompt $suffix: " answer || {
      echo >&2
      echo "ERROR: interactive input ended before setup was complete." >&2
      exit 1
    }
    answer="${answer,,}"
    [[ -z "$answer" ]] && answer="$default"
    case "$answer" in
      y|yes) return 0 ;;
      n|no) return 1 ;;
      *) echo "Please answer yes or no." >&2 ;;
    esac
  done
}

ask_value() {
  local prompt="$1" default="$2" answer
  read -r -p "$prompt [$default]: " answer || {
    echo >&2
    echo "ERROR: interactive input ended before setup was complete." >&2
    exit 1
  }
  printf '%s' "${answer:-$default}"
}

ask_nonnegative_integer() {
  local prompt="$1" default="$2" answer
  while true; do
    answer="$(ask_value "$prompt" "$default")"
    if [[ "$answer" =~ ^[0-9]+$ ]]; then
      printf '%s' "$answer"
      return 0
    fi
    echo "Please enter a non-negative whole number." >&2
  done
}

ask_model_name() {
  local default="$1" answer
  while true; do
    answer="$(ask_value "Model name" "$default")"
    if [[ "$answer" =~ ^[A-Za-z0-9._:/-]+$ ]]; then
      printf '%s' "$answer"
      return 0
    fi
    echo "Please enter a valid model name." >&2
  done
}

ask_keep_alive() {
  local default="$1" answer
  while true; do
    answer="$(ask_value "Keep model loaded after warm-up (for example 30s, 15m or 1h)" "$default")"
    if [[ "$answer" =~ ^[0-9]+(s|m|h)$ ]]; then
      printf '%s' "$answer"
      return 0
    fi
    echo "Please use a duration such as 30s, 15m or 1h." >&2
  done
}

ask_power_action() {
  local default="$1" default_choice answer
  [[ "$default" == suspend ]] && default_choice=2 || default_choice=1
  while true; do
    echo "Power-saving action:" >&2
    echo "  1) Power off" >&2
    echo "  2) Suspend" >&2
    read -r -p "Choose [1/2] [$default_choice]: " answer || {
      echo >&2
      echo "ERROR: interactive input ended before setup was complete." >&2
      exit 1
    }
    [[ -z "$answer" ]] && answer="$default_choice"
    case "${answer,,}" in
      1|poweroff|'power off') printf '%s' poweroff; return 0 ;;
      2|suspend) printf '%s' suspend; return 0 ;;
      *) echo "Please choose 1 for power off or 2 for suspend." >&2 ;;
    esac
  done
}

ask_power_time() {
  local default="$1" answer
  while true; do
    answer="$(ask_value "First weekday power-saving attempt, HH:MM (four more attempts follow every 15 minutes)" "$default")"
    if [[ "$answer" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
      printf '%s' "$answer"
      return 0
    fi
    echo "Please use 24-hour HH:MM, for example 18:30." >&2
  done
}

default_route_interface() {
  ip route show default 2>/dev/null | awk 'NR==1 {for (i=1; i<=NF; i++) if ($i == "dev") {print $(i+1); exit}}'
}

interface_ipv4_address() {
  local nic="$1"
  ip -4 -o addr show dev "$nic" 2>/dev/null | awk 'NR==1 {split($4, a, "/"); print a[1]}'
}

network_interface_exists() {
  [[ "$1" =~ ^[A-Za-z0-9_.:-]+$ && -d "/sys/class/net/$1" ]]
}

ask_wol_interface() {
  local detected address answer
  detected="$(default_route_interface)"
  if [[ -n "$detected" ]] && network_interface_exists "$detected"; then
    address="$(interface_ipv4_address "$detected")"
    echo "Wake-on-LAN network interface:" >&2
    echo "  detected: $detected" >&2
    echo "  address:  ${address:-not assigned}" >&2
    if ask_yes_no "Use the detected interface" yes; then
      printf '%s' "$detected"
      return 0
    fi
  fi

  while true; do
    read -r -p "Linux interface name (for example enp0s16f0u1): " answer || {
      echo >&2
      echo "ERROR: interactive input ended before setup was complete." >&2
      exit 1
    }
    if [[ "$answer" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
      echo "That looks like an IP address. Wake-on-LAN needs the Linux interface name, for example enp0s16f0u1." >&2
      continue
    fi
    if network_interface_exists "$answer"; then
      printf '%s' "$answer"
      return 0
    fi
    echo "Network interface not found: ${answer:-<empty>}. Enter a Linux interface name." >&2
  done
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
  local token age ceiling prompt
  if ! ask_yes_no "Configure upload pruning policy? It starts in DRY-RUN and will not delete anything yet" no; then
    disable_units owui-prune.timer
    return
  fi

  token="$(get_setting OWUI_API_KEY '')"
  if [[ -z "$token" || "$token" == REPLACE_WITH_ADMIN_API_KEY ]]; then
    prompt="Open WebUI administrator API key"
    token=''
  elif [[ ! "$token" =~ ^[A-Za-z0-9._~+/=-]+$ ]]; then
    echo "The stored Open WebUI API key contains unsupported characters; enter a replacement." >&2
    prompt="New Open WebUI administrator API key"
    token=''
  elif ask_yes_no "Keep the existing stored Open WebUI API key" yes; then
    prompt=''
  else
    prompt="New Open WebUI administrator API key"
    token=''
  fi
  while [[ -n "$prompt" ]]; do
    read -r -s -p "$prompt: " token || {
      echo >&2
      echo "ERROR: interactive input ended before setup was complete." >&2
      exit 1
    }
    echo
    if [[ "$token" =~ ^[A-Za-z0-9._~+/=-]+$ ]]; then
      break
    fi
    echo "The API key is empty or contains unsupported characters; please enter it again." >&2
  done

  while true; do
    age="$(ask_nonnegative_integer "Age threshold in days (0 disables age-based pruning)" "$(get_setting MAX_AGE_DAYS 90)")"
    ceiling="$(ask_nonnegative_integer "Storage ceiling for known uploads in GiB (0 disables size-based pruning)" "$(get_setting MAX_TOTAL_GB 20)")"
    ((age > 0 || ceiling > 0)) && break
    echo "At least one pruning rule must be enabled; set an age threshold or storage ceiling above zero." >&2
  done

  set_setting OWUI_API_KEY "$token"
  set_setting MAX_AGE_DAYS "$age"
  set_setting MAX_TOTAL_GB "$ceiling"
  set_setting DRY_RUN 1
  enable_units owui-prune.timer
  echo "Upload pruning is enabled in DRY_RUN=1 mode. No uploads will be deleted until you review a manual run and explicitly set DRY_RUN=0."
}

setup_warmup() {
  local model keep
  if ! ask_yes_no "Enable model warm-up before work? This uses extra electricity" no; then
    disable_units owui-warmup.timer
    return
  fi
  model="$(ask_model_name "$(get_setting WARMUP_MODEL prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl)")"
  keep="$(ask_keep_alive "$(get_setting WARMUP_KEEP_ALIVE 15m)")"
  set_setting WARMUP_MODEL "$model"
  set_setting WARMUP_KEEP_ALIVE "$keep"
  enable_units owui-warmup.timer
}

setup_power() {
  local action time nic wol_tmp
  if ! ask_yes_no "Enable automatic weekday after-hours power saving" no; then
    disable_units bc250-night-shutdown.timer
    return
  fi
  action="$(ask_power_action "$(get_setting NIGHT_POWER_ACTION poweroff)")"
  time="$(ask_power_time "18:30")"
  write_power_schedule "$time"
  set_setting NIGHT_POWER_ACTION "$action"

  if ask_yes_no "Configure Wake-on-LAN so an external companion can wake this host" yes; then
    nic="$(ask_wol_interface)"
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
  cat <<'SETUP_INTRO'
BC-250 local maintenance policy

This configures maintenance performed by the BC-250 itself:
  - verified local backups
  - optional upload pruning
  - optional model warm-up
  - optional after-hours shutdown or suspend
  - Wake-on-LAN for this host

Raspberry Pi SSH access and remote backup export are configured separately after this step.
Changes are applied as each section completes. This setup is safe to rerun.
SETUP_INTRO
  if ask_yes_no "Enable daily verified local Open WebUI backups on this BC-250" yes; then
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
  local api_state='not configured' warmup_state='disabled' power_state='disabled'
  if [[ -e "$CONFIG" && ! -r "$CONFIG" ]]; then
    echo "ERROR: maintenance configuration is private; run status with sudo." >&2
    return 1
  fi
  [[ -r "$CONFIG" ]] || {
    echo "Maintenance is not initialized. Run: sudo bc250-maintenance setup --defaults"
    return 0
  }
  [[ "$(get_setting OWUI_API_KEY '')" != REPLACE_WITH_ADMIN_API_KEY && -n "$(get_setting OWUI_API_KEY '')" ]] && api_state=configured
  if systemctl is-enabled --quiet owui-warmup.timer 2>/dev/null; then warmup_state=enabled; fi
  if systemctl is-enabled --quiet bc250-night-shutdown.timer 2>/dev/null; then power_state=enabled; fi

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
  if [[ "$warmup_state" == enabled ]]; then
    printf '  Warm-up:            enabled model=%s keep_alive=%s\n' \
      "$(get_setting WARMUP_MODEL prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl)" \
      "$(get_setting WARMUP_KEEP_ALIVE 15m)"
  else
    printf '  Warm-up:            disabled (configured model=%s keep_alive=%s)\n' \
      "$(get_setting WARMUP_MODEL prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl)" \
      "$(get_setting WARMUP_KEEP_ALIVE 15m)"
  fi
  if [[ "$power_state" == enabled ]]; then
    printf '  Night power:        enabled action=%s\n' "$(get_setting NIGHT_POWER_ACTION poweroff)"
  else
    printf '  Night power:        disabled (configured action=%s)\n' "$(get_setting NIGHT_POWER_ACTION poweroff)"
  fi

  echo
  echo "Storage overview: sudo bc250-status"

  echo
  echo "Backups"
  backup_summary "Configuration" "$(get_setting CFG_OUT_DIR /var/backups/bc250-llm-server/config)" 'owui-config-*.tar.gz'
  backup_summary "Identity" "$(get_setting USERS_OUT_DIR /var/backups/bc250-llm-server/users)" 'owui-users-*.sql.gz'
  echo "  Local backups contain private office data and do not protect against failure of this disk."
}

run_unit() {
  local label="$1" unit="$2" invocation since rc=0
  systemd_available || { echo "ERROR: systemd is not available." >&2; exit 1; }
  echo "Running $label..."
  since="@$(date +%s.%N)"
  systemctl start "$unit" || rc=$?
  invocation="$(systemctl show "$unit" -p InvocationID --value 2>/dev/null || true)"
  if [[ -n "$invocation" ]]; then
    journalctl _SYSTEMD_INVOCATION_ID="$invocation" --no-pager -o cat || true
  else
    journalctl -u "$unit" --since "$since" --no-pager -o cat || true
  fi
  return "$rc"
}

run_task() { run_unit "$1" "owui-maintenance@$1.service"; }

preflight_prune() {
  local key
  key="$(get_setting OWUI_API_KEY '')"
  [[ -n "$key" && "$key" != REPLACE_WITH_ADMIN_API_KEY ]] && return 0
  printf '%s\n' \
    'Upload pruning cannot run.' \
    '' \
    'Reason: Open WebUI API key is not configured.' \
    '' \
    "Current policy: age=$(get_setting MAX_AGE_DAYS 90)d ceiling=$(get_setting MAX_TOTAL_GB 20)GiB dry_run=$(get_setting DRY_RUN 1)" \
    'Configure the protected Open WebUI credential and retry.' \
    'No uploads were changed.' >&2
  return 1
}

run_selected() {
  require_root
  ensure_config
  case "${1:-}" in
    backup)
      run_task backup-config
      run_task backup-users
      ;;
    prune) preflight_prune && run_task prune-uploads ;;
    all)
      run_task backup-config
      run_task backup-users
      preflight_prune && run_task prune-uploads
      ;;
    *) echo "ERROR: run requires backup, prune or all." >&2; usage >&2; exit 2 ;;
  esac
}

show_contract() {
  [[ -r "$CONTRACT_DOC" ]] || {
    echo "ERROR: maintenance contract is missing: $CONTRACT_DOC" >&2
    return 1
  }
  cat "$CONTRACT_DOC"
}

run_access() {
  [[ -x "$ACCESS_HELPER" ]] || { echo "ERROR: maintenance companion helper is missing: $ACCESS_HELPER" >&2; return 1; }
  "$ACCESS_HELPER" "$@"
}

request_shutdown() {
  require_root
  run_unit "safe shutdown request" bc250-night-shutdown.service
}

request_companion_shutdown() {
  local safe_power_ports night_power_action require_wol
  require_root
  [[ "${SUDO_USER:-}" == "$POWER_CONTROL_USER" && -n "${SSH_CONNECTION:-}" ]] || {
    echo "ERROR: companion shutdown is restricted to the forced SSH power-control identity." >&2
    return 1
  }
  [[ -x "$SAFE_POWER_HELPER" ]] || {
    echo "ERROR: safe-power helper is missing: $SAFE_POWER_HELPER" >&2
    return 1
  }

  # The systemd timer loads these values from maintenance.env. The companion
  # path calls the same helper directly so it can carry one exact SSH exemption;
  # copy only the safe-power settings instead of sourcing the private config as
  # shell code or leaking unrelated values such as the Open WebUI API key.
  safe_power_ports="$(get_setting SAFE_POWER_PORTS '22 80 443 3000 11434 11435 11436 11437')"
  night_power_action="$(get_setting NIGHT_POWER_ACTION poweroff)"
  require_wol="$(get_setting REQUIRE_WOL 0)"

  # Exempt only the authenticated forced-command SSH connection carrying this
  # request. All other protected TCP activity remains a shutdown deferral.
  BC250_SAFE_POWER_EXEMPT_SSH="$SSH_CONNECTION" \
    SAFE_POWER_PORTS="$safe_power_ports" \
    NIGHT_POWER_ACTION="$night_power_action" \
    REQUIRE_WOL="$require_wol" \
    "$SAFE_POWER_HELPER"
}

clean_cache() {
  local cache
  require_root
  echo "This removes rebuildable caches and old system-wide journal archives; GGUFs, Ollama models and Open WebUI data are retained."
  ask_yes_no "Clean appliance cache, dangling images and old system-wide journal archives" no || { echo "Cleanup cancelled."; return; }
  cache=/var/cache/bc250-llm-server/huggingface
  [[ ! -d "$cache" ]] || find "$cache" -mindepth 1 -delete
  command -v podman >/dev/null 2>&1 && podman image prune -f
  command -v journalctl >/dev/null 2>&1 && journalctl --vacuum-size=512M
  echo "Cleanup completed; persistent models and office data were retained."
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
    contract) (($# == 1)) || { usage >&2; exit 2; }; show_contract ;;
    companion)
      (($# == 2)) || { usage >&2; exit 2; }
      case "$2" in status) run_access companion-status ;; enable) run_access companion-enable ;; *) usage >&2; exit 2 ;; esac
      ;;
    backup-export)
      (($# == 2)) || { usage >&2; exit 2; }
      case "$2" in status) run_access backup-status ;; enable) run_access backup-enable ;; *) usage >&2; exit 2 ;; esac
      ;;
    request-shutdown) (($# == 1)) || { usage >&2; exit 2; }; request_shutdown ;;
    request-shutdown-companion) (($# == 1)) || { usage >&2; exit 2; }; request_companion_shutdown ;;
    run) (($# == 2)) || { usage >&2; exit 2; }; run_selected "$2" ;;
    clean-cache) (($# == 1)) || { usage >&2; exit 2; }; clean_cache ;;
    disable) (($# == 1)) || { usage >&2; exit 2; }; disable_all ;;
    -h|--help|help) usage ;;
    *) echo "ERROR: unknown command: $1" >&2; usage >&2; exit 2 ;;
  esac
}

main "$@"
