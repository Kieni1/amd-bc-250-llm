#!/usr/bin/env bash
# Concise, read-only appliance status. Use bc250-verify for pass/fail checks.
set -uo pipefail

section() {
  printf '\n=== %s ===\n' "$1"
}

value_or_unknown() {
  local value="${1:-}"
  [[ -n "$value" ]] && printf '%s' "$value" || printf 'unknown'
}

unit_state() {
  [[ -d /run/systemd/system ]] || {
    printf 'unknown'
    return
  }
  systemctl is-active --quiet "$1" >/dev/null 2>&1 && \
    printf 'active' || printf 'inactive'
}

unit_enablement() {
  [[ -d /run/systemd/system ]] || {
    printf 'unknown'
    return
  }
  systemctl is-enabled --quiet "$1" >/dev/null 2>&1 && \
    printf 'enabled' || printf 'disabled'
}

service_status() {
  local unit="$1" state enabled
  state="$(unit_state "$unit")"
  enabled="$(unit_enablement "$unit")"
  printf '  %-38s %s, %s\n' "$unit" \
    "$(value_or_unknown "$state")" "$(value_or_unknown "$enabled")"
}

ollama_status() {
  local label="$1" unit="$2" port="$3" state models response
  state="$(unit_state "$unit")"
  response="$(curl --fail --silent --connect-timeout 1 --max-time 3 \
    "http://127.0.0.1:${port}/api/tags" 2>/dev/null || true)"
  if [[ -n "$response" ]]; then
    models="$(jq -r '.models | length' <<< "$response" 2>/dev/null || printf '?')"
    printf '  %-9s port %-5s %-8s API ready, %s model(s)\n' \
      "$label" "$port" "$(value_or_unknown "$state")" "$models"
  else
    printf '  %-9s port %-5s %-8s API unavailable\n' \
      "$label" "$port" "$(value_or_unknown "$state")"
  fi
}

directory_usage() {
  local label="$1" path="$2" usage
  [[ -e "$path" ]] || return 0
  usage="$(du -sh -- "$path" 2>/dev/null | awk '{print $1}' || true)"
  printf '  %-22s %8s  %s\n' "$label" "$(value_or_unknown "$usage")" "$path"
}

if [[ "${1:-}" == -h || "${1:-}" == --help ]]; then
  cat <<'USAGE'
Usage: bc250-status

Print a concise, read-only summary of the BC-250 appliance. Run with sudo for
complete live-CU and storage information. Use bc250-verify for pass/fail checks.
USAGE
  exit 0
elif (($#)); then
  echo "ERROR: bc250-status does not accept arguments." >&2
  exit 2
fi

echo "BC-250 appliance status"

section "Platform"
printf '  Kernel:       %s\n' "$(uname -r)"
printf '  Command line: %s\n' "$(cat /proc/cmdline 2>/dev/null || printf 'unavailable')"
if command -v needs-restarting >/dev/null 2>&1; then
  if needs-restarting -r >/dev/null 2>&1; then
    echo "  Reboot:       not requested by installed packages"
  else
    echo "  Reboot:       recommended after package/kernel updates"
  fi
else
  echo "  Reboot:       needs-restarting is not installed"
fi

section "Compute and governor"
cu_helper=""
if command -v bc250-cu-status >/dev/null 2>&1; then
  cu_helper="$(command -v bc250-cu-status)"
elif [[ -x /usr/libexec/bc250-llm-server/cu-status.sh ]]; then
  cu_helper=/usr/libexec/bc250-llm-server/cu-status.sh
fi
if [[ -n "$cu_helper" ]]; then
  cu_report="$("$cu_helper" 2>&1 || true)"
  cu_summary="$(grep -E 'Live manager report|Kernel active_cu_number|RADV report' \
    <<< "$cu_report" || true)"
  [[ -n "$cu_summary" ]] && printf '%s\n' "$cu_summary" || echo "  CU status could not be summarized"
else
  echo "  CU status helper is not installed"
fi

governor_config=/etc/cyan-skillfish-governor-smu/config.toml
if [[ -r "$governor_config" ]]; then
  governor_min="$(awk '/^\[frequency-range\]/{s=1;next} /^\[/{s=0} s&&$1=="min"{print $3;exit}' "$governor_config")"
  governor_max="$(awk '/^\[frequency-range\]/{s=1;next} /^\[/{s=0} s&&$1=="max"{print $3;exit}' "$governor_config")"
  throttle="$(awk '/^\[temperature\]/{s=1;next} /^\[/{s=0} s&&$1=="throttling"{print $3;exit}' "$governor_config")"
  printf '  Governor:     %s-%s MHz, throttle %s C\n' \
    "$(value_or_unknown "$governor_min")" \
    "$(value_or_unknown "$governor_max")" \
    "$(value_or_unknown "$throttle")"
else
  echo "  Governor:     configuration unavailable"
fi
service_status cyan-skillfish-governor-smu.service

section "Ollama instances"
if command -v ollama >/dev/null 2>&1; then
  ollama --version 2>/dev/null | sed 's/^/  /' || true
else
  echo "  Ollama command is not installed"
fi
ollama_status main ollama.service 11434
ollama_status task ollama-task.service 11435
ollama_status agent ollama-agent.service 11436

section "Web services"
for unit in open-webui.service tika.service nginx.service; do
  service_status "$unit"
done

section "Memory and swap"
free -h 2>/dev/null | sed 's/^/  /' || true
printf '  vm.swappiness: %s\n' "$(sysctl -n vm.swappiness 2>/dev/null || printf 'unknown')"
if zramctl --noheadings 2>/dev/null | grep -q .; then
  zramctl 2>/dev/null | sed 's/^/  /'
else
  echo "  No active zram device"
fi
if swapon --show --noheadings 2>/dev/null | grep -q .; then
  swapon --show 2>/dev/null | sed 's/^/  /'
else
  echo "  No active swap"
fi
[[ -r /proc/pressure/memory ]] && sed 's/^/  memory PSI: /' /proc/pressure/memory

section "Storage"
df -h / /boot 2>/dev/null | awk '!seen[$1]++' | sed 's/^/  /'
directory_usage "GGUF sources" /var/lib/bc250-llm-server/gguf
directory_usage "Ollama main" /var/lib/bc250-llm-server/ollama/main
directory_usage "Ollama task" /var/lib/bc250-llm-server/ollama/task
directory_usage "Ollama agent" /var/lib/bc250-llm-server/ollama/agent
directory_usage "Hugging Face cache" /var/cache/bc250-llm-server/huggingface
directory_usage "Open WebUI" /var/lib/open-webui
directory_usage "Podman storage" /var/lib/containers/storage
command -v journalctl >/dev/null 2>&1 && journalctl --disk-usage 2>/dev/null | sed 's/^/  Journal: /'

section "Sensors"
sensor_drivers="$(
  for path in /sys/class/hwmon/hwmon*/name; do
    [[ -r "$path" ]] && cat "$path"
  done | LC_ALL=C sort -u | paste -sd, -
)"
printf '  hwmon drivers: %s\n' "$(value_or_unknown "$sensor_drivers")"
pwm_count="$(find /sys/class/hwmon -maxdepth 2 -type f -name 'pwm[0-9]*' 2>/dev/null | wc -l)"
printf '  PWM controls:  %s\n' "$pwm_count"
if command -v sensors >/dev/null 2>&1; then
  sensor_lines="$(sensors 2>/dev/null | \
    grep -Ei 'Tctl:|edge:|junction:|mem:|PPT:|power[0-9]+:|fan[0-9]+:' | \
    head -20 || true)"
  [[ -n "$sensor_lines" ]] && printf '%s\n' "$sensor_lines" | sed 's/^/  /' || \
    echo "  No selected temperature, power or fan readings"
else
  echo "  sensors command is not installed"
fi

echo
echo "For full pass/fail validation run: sudo bc250-verify"
