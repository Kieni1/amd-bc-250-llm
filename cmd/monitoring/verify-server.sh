#!/usr/bin/env bash
set -uo pipefail
CU_STATUS="${BC250_LIBEXEC:-/usr/libexec/bc250-llm-server}/cu-status.sh"
RUNTIME_STATE="${BC250_LIBEXEC:-/usr/libexec/bc250-llm-server}/runtime-state.sh"
if [[ ! -r "$RUNTIME_STATE" ]]; then
  RUNTIME_STATE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/runtime-state.sh"
fi
# shellcheck disable=SC1090
source "$RUNTIME_STATE"

OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
runtime_env="${BC250_RUNTIME_ENV:-/usr/share/bc250-llm-server/runtime.env}"
if [[ ! -r "$runtime_env" ]]; then runtime_env="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/../../config/runtime.env"; fi
if [[ -r "$runtime_env" ]]; then # shellcheck disable=SC1090
  source "$runtime_env"
else
  BC250_OLLAMA_VERSION=unknown
fi
RUN_MODEL_TESTS="${RUN_MODEL_TESTS:-0}"
OWUI_TOKEN_FILE=""
DEFAULT_OWUI_TOKEN_FILE=/var/lib/bc250-llm-server/secrets/openwebui-admin.key
SUMMARY=0
PASS=0
WARN=0
FAIL=0
SKIP=0
CURRENT_SECTION=""
SECTION_PASS=0
SECTION_WARN=0
SECTION_FAIL=0

usage() {
  cat <<'USAGE'
Usage: sudo bc250 verify [--summary] [--owui-token-file FILE]

Runs local appliance verification. --summary keeps the same checks but prints a
compact section-level result. With --owui-token-file, the protected Open WebUI
administrator API key is used only for the live package-owned desired-state check
and is not persisted.
USAGE
}

while (($#)); do
  case "$1" in
    --summary) SUMMARY=1; shift ;;
    --owui-token-file)
      (($# >= 2)) || { echo "ERROR: --owui-token-file requires a path" >&2; exit 2; }
      OWUI_TOKEN_FILE="$2"
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$OWUI_TOKEN_FILE" && -s "$DEFAULT_OWUI_TOKEN_FILE" ]]; then
  OWUI_TOKEN_FILE="$DEFAULT_OWUI_TOKEN_FILE"
fi

if [[ -n "$OWUI_TOKEN_FILE" ]]; then
  [[ -f "$OWUI_TOKEN_FILE" && -r "$OWUI_TOKEN_FILE" && -s "$OWUI_TOKEN_FILE" ]] || {
    echo "ERROR: Open WebUI API key file must be a readable, non-empty regular file: $OWUI_TOKEN_FILE" >&2
    exit 2
  }
  token_mode="$(stat -c '%a' "$OWUI_TOKEN_FILE" 2>/dev/null || true)"
  [[ "$token_mode" =~ ^[0-7]{3,4}$ ]] || {
    echo "ERROR: cannot determine permissions for Open WebUI API key file: $OWUI_TOKEN_FILE" >&2
    exit 2
  }
  if (( (8#$token_mode) & 077 )); then
    echo "ERROR: Open WebUI API key file must not be group/world accessible: $OWUI_TOKEN_FILE (mode $token_mode)" >&2
    exit 2
  fi
  if [[ "$OWUI_TOKEN_FILE" == "$DEFAULT_OWUI_TOKEN_FILE" ]]; then
    [[ "$(stat -c '%u' "$OWUI_TOKEN_FILE" 2>/dev/null || echo -1)" == 0 ]] || { echo "ERROR: package default Open WebUI API key must be root-owned" >&2; exit 2; }
    [[ "$(stat -c '%u' "$(dirname "$OWUI_TOKEN_FILE")" 2>/dev/null || echo -1)" == 0 ]] || { echo "ERROR: package secrets directory must be root-owned" >&2; exit 2; }
    dir_mode="$(stat -c '%a' "$(dirname "$OWUI_TOKEN_FILE")" 2>/dev/null || true)"
    [[ "$dir_mode" == 700 || "$dir_mode" == 0700 ]] || { echo "ERROR: package secrets directory must be mode 0700" >&2; exit 2; }
  fi
  OWUI_API_KEY="$(<"$OWUI_TOKEN_FILE")"
  export OWUI_API_KEY
fi

finish_section() {
  ((SUMMARY)) || return 0
  [[ -n "$CURRENT_SECTION" ]] || return 0
  local status=OK detail=""
  local pass_delta=$((PASS - SECTION_PASS)) warn_delta=$((WARN - SECTION_WARN)) fail_delta=$((FAIL - SECTION_FAIL))
  if ((fail_delta > 0)); then
    status=FAIL
  elif ((warn_delta > 0)); then
    status=WARN
  elif ((pass_delta == 0)); then
    status=INFO
  fi
  if [[ "$status" == INFO ]]; then
    detail="informational"
  else
    detail="$pass_delta ok"
    ((warn_delta > 0)) && detail+=" / $warn_delta warn"
    ((fail_delta > 0)) && detail+=" / $fail_delta fail"
  fi
  printf '  %-30s %-4s  (%s)\n' "$CURRENT_SECTION" "$status" "$detail"
}

ok() { ((SUMMARY)) || printf '  [ OK ] %s\n' "$1"; PASS=$((PASS + 1)); }
warn() { ((SUMMARY)) && printf '    [WARN] %s\n' "$1" || printf '  [WARN] %s\n' "$1"; WARN=$((WARN + 1)); }
bad() { ((SUMMARY)) && printf '    [FAIL] %s\n' "$1" || printf '  [FAIL] %s\n' "$1"; FAIL=$((FAIL + 1)); }
skipped() { ((SUMMARY)) && printf '    [SKIP] %s\n' "$1" || printf '  [SKIP] %s\n' "$1"; SKIP=$((SKIP + 1)); }
info() { ((SUMMARY)) || printf '  [info] %s\n' "$1"; }
section() {
  finish_section
  CURRENT_SECTION="$1"
  SECTION_PASS=$PASS
  SECTION_WARN=$WARN
  SECTION_FAIL=$FAIL
  ((SUMMARY)) || printf '\n=== %s ===\n' "$1"
}
read_param() { [[ -r "$1" ]] && cat "$1" || printf 'not exposed'; }
toml_table_value() {
  local table="$1" key="$2" file="$3"
  awk -v table="[$table]" -v key="$key" '
    $0 == table { inside=1; next }
    /^\[/ { inside=0 }
    inside && $1 == key && $2 == "=" {
      sub(/#.*/, "")
      sub(/^[^=]*=[[:space:]]*/, "")
      sub(/[[:space:]]+$/, "")
      print
      exit
    }
  ' "$file"
}

INTERNAL_FIREWALL_PORTS=(11434 11435 11436 11437 3000 9998)

firewall_port_spec_exposes_tcp_port() {
  local token="$1" target="$2" span proto start end
  [[ "$token" == */* ]] || return 1
  span="${token%/*}"
  proto="${token##*/}"
  [[ "$proto" == tcp ]] || return 1
  if [[ "$span" =~ ^([0-9]+)-([0-9]+)$ ]]; then
    start="${BASH_REMATCH[1]}"
    end="${BASH_REMATCH[2]}"
  elif [[ "$span" =~ ^[0-9]+$ ]]; then
    start="$span"
    end="$span"
  else
    return 1
  fi
  ((start <= end)) || return 1
  ((target >= start && target <= end))
}

firewall_port_list_exposes_tcp_port() {
  local specs="$1" target="$2" token
  local -a parsed=()
  read -r -a parsed <<< "$specs"
  for token in "${parsed[@]}"; do
    firewall_port_spec_exposes_tcp_port "$token" "$target" && return 0
  done
  return 1
}

firewall_port_spec_exposes_internal() {
  local token="$1" protected
  for protected in "${INTERNAL_FIREWALL_PORTS[@]}"; do
    firewall_port_spec_exposes_tcp_port "$token" "$protected" && return 0
  done
  return 1
}

firewall_port_list_exposes_internal() {
  local token
  local -a specs=()
  read -r -a specs <<< "$1"
  for token in "${specs[@]}"; do
    firewall_port_spec_exposes_internal "$token" && return 0
  done
  return 1
}

firewalld_service_ports() {
  local service="$1" info
  if ! info="$(firewall-cmd --info-service="$service" 2>/dev/null)"; then
    return 2
  fi
  sed -n 's/^[[:space:]]*ports:[[:space:]]*//p' <<< "$info" | paste -sd' ' -
}

firewalld_service_exposes_tcp_port() {
  local service="$1" target="$2" ports
  if ! ports="$(firewalld_service_ports "$service")"; then
    return 2
  fi
  [[ -n "$ports" ]] && firewall_port_list_exposes_tcp_port "$ports" "$target"
}

firewalld_service_exposes_internal() {
  local service="$1" ports
  if ! ports="$(firewalld_service_ports "$service")"; then
    return 2
  fi
  [[ -n "$ports" ]] && firewall_port_list_exposes_internal "$ports"
}

firewall_rich_rules_expose_tcp_port() {
  local rich="$1" target="$2" rule service port proto service_state
  while IFS= read -r rule; do
    [[ "$rule" =~ (^|[[:space:]])accept($|[[:space:]]) ]] || continue
    service="$(sed -n 's/.*service name="\([^"]*\)".*/\1/p' <<< "$rule")"
    if [[ -n "$service" ]]; then
      if [[ "$service" == http && "$target" == 80 ]]; then
        return 0
      fi
      if firewalld_service_exposes_tcp_port "$service" "$target"; then
        return 0
      else
        service_state=$?
        ((service_state == 2)) && return 2
      fi
    fi
    port="$(sed -n 's/.*port port="\([^"]*\)".*/\1/p' <<< "$rule")"
    proto="$(sed -n 's/.*protocol="\([^"]*\)".*/\1/p' <<< "$rule")"
    if [[ -n "$port" && -n "$proto" ]] && \
       firewall_port_spec_exposes_tcp_port "$port/$proto" "$target"; then
      return 0
    fi
  done <<< "$rich"
  return 1
}

firewall_rich_rules_expose_internal() {
  local rich="$1" rule service port proto service_state
  while IFS= read -r rule; do
    [[ "$rule" =~ (^|[[:space:]])accept($|[[:space:]]) ]] || continue
    service="$(sed -n 's/.*service name="\([^"]*\)".*/\1/p' <<< "$rule")"
    if [[ -n "$service" ]]; then
      if firewalld_service_exposes_internal "$service"; then
        return 0
      else
        service_state=$?
        ((service_state == 2)) && return 2
      fi
    fi
    port="$(sed -n 's/.*port port="\([^"]*\)".*/\1/p' <<< "$rule")"
    proto="$(sed -n 's/.*protocol="\([^"]*\)".*/\1/p' <<< "$rule")"
    if [[ -n "$port" && -n "$proto" ]] && firewall_port_spec_exposes_internal "$port/$proto"; then
      return 0
    fi
  done <<< "$rich"
  return 1
}

if [[ ${EUID} -ne 0 ]]; then
  warn "not running as root; Podman, journal and live-CU checks may be incomplete"
fi

section "Platform"
kernel="$(uname -r)"
info "running kernel: $kernel"
if command -v rpm >/dev/null 2>&1; then
  mesa="$(rpm -q --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' mesa-vulkan-drivers 2>/dev/null || true)"
  [[ -n "$mesa" ]] && info "Mesa: $mesa" || warn "mesa-vulkan-drivers package not found"
fi
if lspci -nn 2>/dev/null | grep -qiE '13fe|Cyan Skillfish|BC-250'; then
  ok "BC-250/Cyan Skillfish PCI device detected"
else
  warn "BC-250 PCI identifier was not recognized"
fi
if command -v vulkaninfo >/dev/null 2>&1; then
  dev="$(vulkaninfo --summary 2>/dev/null | grep -i deviceName | head -1)"
  if grep -qi llvmpipe <<< "$dev"; then
    bad "software Vulkan device: $dev"
  elif grep -qiE 'AMD|RADV|Radeon|BC-250|Cyan' <<< "$dev"; then
    ok "Vulkan GPU: ${dev#*=}"
  else
    bad "no recognized AMD Vulkan device: ${dev:-none}"
  fi
else
  bad "vulkaninfo missing"
fi

section "CPU power states"
physical_cores="$(lscpu -p=SOCKET,CORE 2>/dev/null | grep -v '^#' | sort -u | wc -l)"
threads="$(nproc 2>/dev/null || printf '0')"
info "CPU topology: $physical_cores physical cores / $threads online threads"
cpufreq_driver="$(cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_driver 2>/dev/null | sort -u | paste -sd, -)"
cpufreq_governor="$(cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null | sort -u | paste -sd, -)"
if [[ -z "$cpufreq_driver" && -z "$cpufreq_governor" ]]; then
  if systemctl is-active --quiet cyan-skillfish-governor-smu.service 2>/dev/null; then
    info "standard CPU cpufreq interfaces are not exposed on this platform; the BC-250 SMU governor is active"
  else
    warn "standard CPU cpufreq interfaces are not exposed and the BC-250 SMU governor is not active"
  fi
else
  [[ -n "$cpufreq_driver" ]] && info "cpufreq driver: $cpufreq_driver" || warn "cpufreq driver is not exposed"
  [[ -n "$cpufreq_governor" ]] && info "cpufreq governor: $cpufreq_governor" || warn "cpufreq governor is not exposed"
fi
missing_idle="$(for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
  [[ -d "$cpu" ]] || continue
  [[ -r "$cpu/online" && "$(cat "$cpu/online")" == 0 ]] && continue
  compgen -G "$cpu/cpuidle/state*" >/dev/null || printf '%s\n' "${cpu##*/}"
done | paste -sd, -)"
if [[ -n "$missing_idle" ]]; then
  info "online CPUs without cpuidle states: $missing_idle"
  [[ "$threads" == 16 ]] && warn "16 threads are active but some CPUs lack C-states; check idle power/correctness" || \
    info "cpuidle/C-state telemetry is not exposed for all online CPUs on this platform; no action required"
else
  ok "all online CPUs expose cpuidle states"
fi

section "GPU memory and storage"
gtt="$(read_param /sys/module/amdgpu/parameters/gttsize)"
pages="$(read_param /sys/module/ttm/parameters/pages_limit)"
pool="$(read_param /sys/module/ttm/parameters/page_pool_size)"
info "amdgpu.gttsize: $gtt"
info "ttm.pages_limit: $pages"
info "ttm.page_pool_size: $pool"
ppmask="$(read_param /sys/module/amdgpu/parameters/ppfeaturemask)"
info "amdgpu.ppfeaturemask: $ppmask"
if [[ "$pages" =~ ^[0-9]+$ ]]; then
  gib="$(awk -v p="$pages" 'BEGIN {printf "%.2f", p*4096/1024/1024/1024}')"
  info "TTM pages_limit capacity: approximately ${gib} GiB"
  ((pages >= 4194304)) && ok "TTM limit supports the reviewed TTM memory profile" || \
    warn "TTM limit is below 4194304 pages; large models may hit an allocation cap"
else
  warn "kernel does not expose a numeric TTM pages_limit"
fi
if [[ "$pages" != 4194304 || "$pool" != 4194304 ]]; then
  conflicts="$(grep -RInE 'ttm\.(pages_limit|page_pool_size)|options[[:space:]]+ttm' \
    /etc/tmpfiles.d /usr/lib/tmpfiles.d /etc/modprobe.d 2>/dev/null | head -12 || true)"
  if [[ -n "$conflicts" ]]; then
    info "possible TTM override/config conflict(s):"
    ((SUMMARY)) || sed 's/^/  /' <<< "$conflicts"
  else
    info "no TTM override was found in tmpfiles.d/modprobe.d; inspect bootloader and local administration state"
  fi
fi

cmdline="$(cat /proc/cmdline 2>/dev/null || true)"
info "kernel arguments: $cmdline"
for token in ttm.pages_limit=4194304 ttm.page_pool_size=4194304; do
  grep -qE "(^| )${token//./\.}( |$)" <<< "$cmdline" && ok "kernel profile: $token" || warn "missing reviewed kernel profile argument: $token"
done
for prefix in amdgpu.gttsize= amdgpu.ppfeaturemask=; do
  if grep -qE "(^| )${prefix//./\.}[^ ]*( |$)" <<< "$cmdline"; then
    warn "legacy kernel override remains: ${prefix}...; current reviewed profile uses TTM limits only"
  else
    ok "legacy kernel override absent: ${prefix}..."
  fi
done
if grep -qE '(^| )amd_iommu=on( |$)' <<< "$cmdline"; then
  info "amd_iommu=on is active; IOMMU is outside the qualified LLM baseline and should be device-qualified with matching BIOS SVM/IOMMU state"
else
  ok "IOMMU is not forced from the kernel command line (qualified appliance baseline)"
fi
grep -qE '(^| )nomodeset( |$)' <<< "$cmdline" && bad "nomodeset is still active and prevents normal GPU acceleration" || ok "nomodeset is not active"

while read -r fs size used avail pct mount; do
  [[ "$fs" == Filesystem ]] && continue
  info "$mount: $avail available ($pct used)"
  pct_num="${pct%%%}"
  [[ "$pct_num" =~ ^[0-9]+$ ]] && ((pct_num >= 95)) && bad "$mount is critically full"
done < <(df -h / /var/lib/bc250-llm-server 2>/dev/null | awk '!seen[$1]++')

section "Swap and zram"
swappiness="$(sysctl -n vm.swappiness 2>/dev/null || true)"
[[ -n "$swappiness" ]] && info "vm.swappiness: $swappiness" || \
  warn "vm.swappiness is not readable"
swap_state_readable=1
if swap_names="$(bc250_active_swap_names)"; then
  if [[ -n "$swap_names" ]]; then
    ((SUMMARY)) || swapon --show 2>/dev/null | sed 's/^/  /'
    ok "swap is active"
  else
    warn "no swap is active"
  fi
else
  swap_state_readable=0
  swap_names=""
  warn "active swap state could not be determined"
fi
active_zram_names=""
if ((swap_state_readable)); then
  active_zram_names="$(awk '$1 ~ /^\/dev\/zram[0-9]+$/ {print $1}' <<< "$swap_names")"
fi
if [[ -n "$active_zram_names" ]]; then
  ((SUMMARY)) || {
    echo "  Active zram swap device(s):"
    sed 's/^/    /' <<< "$active_zram_names"
    zramctl 2>/dev/null | sed 's/^/  /' || true
  }
  if command -v zramctl >/dev/null 2>&1; then
    zram_size=0
    while IFS= read -r zram_device; do
      [[ -n "$zram_device" ]] || continue
      device_size="$(zramctl --bytes --noheadings --output DISKSIZE "$zram_device" 2>/dev/null | awk 'NR==1 {print $1+0}')"
      zram_size=$((zram_size + ${device_size:-0}))
    done <<< "$active_zram_names"
    ((zram_size > 4*1024*1024*1024)) && \
      warn "active zram swap exceeds 4 GiB and competes with the unified model-memory pool" || \
      ok "active zram swap size is compatible with the dedicated LLM profile"
  else
    warn "zram swap is active but zramctl is unavailable for size verification"
  fi
elif ((swap_state_readable)); then
  initialized_zram="$(zramctl --noheadings --output NAME 2>/dev/null | awk '$1 ~ /^\/dev\/zram[0-9]+$/ {print $1}' | paste -sd, -)"
  if [[ -r /etc/systemd/zram-generator.conf.d/90-bc250-llm-server.conf ]]; then
    if [[ -n "$initialized_zram" ]]; then
      warn "package-managed zram profile is configured and ${initialized_zram} exists, but no zram device is active as swap"
    else
      warn "package-managed zram profile is configured but no zram device is active as swap"
    fi
  elif [[ -n "$initialized_zram" ]]; then
    info "zram device(s) exist but are not active as swap: $initialized_zram"
  else
    info "no active zram swap (no package-managed zram profile configured)"
  fi
else
  warn "zram swap activity is unverified because active swap state is unavailable"
fi
if ((swap_state_readable)); then
  if grep -Ev '^/dev/zram[0-9]+$' <<< "$swap_names" | grep -q .; then
    ok "disk-backed swap safety margin is active"
  else
    warn "no disk-backed swap safety margin is active"
  fi
else
  warn "disk-backed swap safety margin is unverified because active swap state is unavailable"
fi

section "Compute units"
if [[ -x "$CU_STATUS" ]]; then
  if ((SUMMARY)); then
    cu_output="$("$CU_STATUS" --summary 2>&1 || true)"
  else
    cu_output="$("$CU_STATUS" 2>&1 || true)"
  fi
else
  if ((SUMMARY)); then
    cu_output="$(/usr/libexec/bc250-llm-server/cu-status.sh --summary 2>&1 || true)"
  else
    cu_output="$(/usr/libexec/bc250-llm-server/cu-status.sh 2>&1 || true)"
  fi
fi
((SUMMARY)) || printf '%s\n' "$cu_output" | sed 's/^/  /'
cu_problems="$(sed -n 's/^[[:space:]]*Problem cells[[:space:]]*:[[:space:]]*//p' <<< "$cu_output" | head -1)"
if [[ "$cu_problems" =~ ^[0-9]+$ ]] && ((cu_problems > 0)); then
  warn "live CU routing contains $cu_problems unexpected D! cell(s)"
elif grep -Fq 'Routing profile match   : exact' <<< "$cu_output"; then
  ok "live CU routing matches the configured saved profile"
elif grep -Fq 'Routing profile match   : not configured' <<< "$cu_output"; then
  ok "live CU routing parsed; no saved CU profile is configured (optional)"
elif grep -Fq 'Routing profile match   : mismatch' <<< "$cu_output"; then
  warn "live CU routing differs from the configured saved profile"
elif grep -Fq 'Routing profile match   : invalid saved profile' <<< "$cu_output"; then
  warn "saved CU routing profile is invalid; rewrite it with the live manager"
else
  info "no parseable live CU routing profile comparison"
fi

section "Governor and sensors"
config=/etc/cyan-skillfish-governor-smu/config.toml
if command -v cyan-skillfish-governor-smu >/dev/null 2>&1; then
  governor_version="$(cyan-skillfish-governor-smu --version 2>/dev/null | head -1 || true)"
  info "governor version: ${governor_version:-unknown}"
else
  warn "cyan-skillfish-governor-smu executable is missing"
fi
if [[ -r "$config" ]]; then
  ok "governor config installed"
  min="$(awk '/^\[frequency-range\]/{s=1;next} /^\[/{s=0} s&&$1=="min"{print $3;exit}' "$config")"
  max="$(awk '/^\[frequency-range\]/{s=1;next} /^\[/{s=0} s&&$1=="max"{print $3;exit}' "$config")"
  fix_freq="$(toml_table_value gpu-usage fix-freq "$config")"
  usage_method="$(toml_table_value gpu-usage method "$config")"
  info "governor range: ${min:-unknown}-${max:-unknown} MHz"
  info "governor gpu usage: method=${usage_method:-unknown}; fix-freq=${fix_freq:-not set}"
  [[ -n "$fix_freq" ]] || \
    warn "governor fix-freq is not explicit; package policy expects false"
  [[ "$usage_method" != '"kernel"' ]] || \
    warn "governor kernel usage method requires a separately patched compatible kernel"
  active_sclk=""
  for drm_card in /sys/class/drm/card[0-9]*; do
    [[ -r "$drm_card/device/vendor" ]] || continue
    [[ "$(cat "$drm_card/device/vendor")" == 0x1002 ]] || continue
    [[ -r "$drm_card/device/pp_dpm_sclk" ]] || continue
    active_sclk="$(grep '\*' "$drm_card/device/pp_dpm_sclk" | grep -oE '[0-9]+Mhz' | tr -d 'A-Za-z' | head -1 || true)"
    [[ -n "$active_sclk" ]] && break
  done
  if [[ "$active_sclk" =~ ^[0-9]+$ && "$max" =~ ^[0-9]+$ ]]; then
    if ((active_sclk > max)); then
      warn "active GPU clock ${active_sclk} MHz exceeds configured normal maximum ${max} MHz; check explicit D-Bus/performance override"
    else
      info "active GPU clock: ${active_sclk} MHz (configured normal max ${max} MHz)"
    fi
  fi
else
  bad "governor config missing"
fi
if command -v sensors >/dev/null 2>&1; then
  sensor_lines="$(sensors 2>/dev/null | \
    grep -Ei 'Tctl:|edge:|junction:|mem:|PPT:|power[0-9]+:|fan[0-9]+:' | \
    head -20 || true)"
  if [[ -n "$sensor_lines" ]]; then
    ((SUMMARY)) || printf '%s\n' "$sensor_lines" | sed 's/^/  /'
  else
    warn "no selected temperature, power or fan readings found"
  fi
fi
mods="$(lsmod 2>/dev/null | awk '{print $1}')"
if grep -qx nct6683 <<< "$mods" && grep -Eq '^nct6687' <<< "$mods"; then
  bad "nct6683 and nct6687 drivers are both loaded; they conflict"
elif grep -Eq '^nct6687' <<< "$mods"; then
  warn "experimental nct6687 PWM driver is loaded; rebuild/check it after kernel updates"
  pwm_count="$(find /sys/class/hwmon -maxdepth 2 -type f -name 'pwm[0-9]*' 2>/dev/null | wc -l)"
  ((pwm_count > 0)) && info "$pwm_count PWM control file(s) exposed" || \
    warn "nct6687 is loaded but no PWM control files are exposed"
elif grep -qx nct6683 <<< "$mods"; then
  ok "safe nct6683 sensor driver is loaded"
else
  warn "neither nct6683 nor nct6687 sensor driver is loaded"
fi

section "Services"
agent_active=0
systemctl is-active --quiet ollama-agent.service 2>/dev/null && agent_active=1
task_lane_active=0
embedding_lane_active=0
systemctl is-active --quiet ollama-task.service 2>/dev/null && task_lane_active=1
systemctl is-active --quiet ollama-embedding.service 2>/dev/null && embedding_lane_active=1
for unit in cyan-skillfish-governor-smu.service tika.service open-webui.service nginx.service; do
  if systemctl is-active --quiet "$unit" 2>/dev/null; then
    ok "$unit active"
  else
    bad "$unit inactive"
  fi
done
if ((agent_active)); then
  ok "exclusive agent mode is active"
  OLLAMA_URL="http://127.0.0.1:11436"
  for unit in ollama.service ollama-task.service ollama-embedding.service; do
    if systemctl is-active --quiet "$unit" 2>/dev/null; then
      bad "$unit is active while exclusive agent mode is active"
    else
      info "$unit stopped for exclusive agent mode"
    fi
  done
else
  if systemctl is-active --quiet ollama.service 2>/dev/null; then
    ok "ollama.service active"
  else
    bad "ollama.service inactive"
  fi
  for unit in ollama-task.service ollama-embedding.service; do
    if ! systemctl cat "$unit" >/dev/null 2>&1; then
      bad "$unit missing; normal appliance mode requires main + task + embedding"
    elif systemctl is-active --quiet "$unit" 2>/dev/null; then
      ok "$unit active"
    else
      bad "$unit inactive; normal appliance mode requires main + task + embedding"
    fi
  done
fi
if ((agent_active == 0)); then
  if ((task_lane_active)); then
    task_tags="$(curl -fsS http://127.0.0.1:11435/api/tags 2>/dev/null || true)"
    if [[ -n "$task_tags" ]] && jq -e --arg model "task-lfm25-1.2b-instruct-liquidai-q6-k" \
        'any(.models[]?; (.name | sub(":latest$"; "")) == $model)' \
        <<< "$task_tags" >/dev/null 2>&1; then
      ok "default Open WebUI task model is registered on dedicated task Ollama"
    else
      bad "default Open WebUI task model is not registered on dedicated task Ollama :11435"
    fi
  else
    skipped "task model registration unavailable because ollama-task.service is inactive"
  fi
fi

agent_unit_state="$(systemctl show -p UnitFileState --value ollama-agent.service 2>/dev/null || true)"
if [[ $agent_unit_state == enabled || $agent_unit_state == enabled-runtime ]]; then
  warn "optional Agent lane is enabled at boot; Agent mode is intended to be exclusive and operator-entered"
elif ((agent_active == 0)); then
  ok "optional Agent lane is inactive in normal mode (unit ${agent_unit_state:-unknown})"
else
  info "optional Agent lane is active by operator request (unit ${agent_unit_state:-unknown})"
fi
if id -nG ollama 2>/dev/null | grep -qw render && \
   id -nG ollama 2>/dev/null | grep -qw video; then
  ok "ollama has render/video access"
else
  bad "ollama lacks render/video access"
fi
failed_units="$(bc250_failed_systemd_units)"
failed_units_rc=$?
if ((failed_units_rc != 0)); then
  warn "systemd failed-unit state could not be inspected"
elif [[ -n "$failed_units" ]]; then
  bad "systemd has failed units: $(paste -sd, - <<< "$failed_units")"
else
  ok "systemd has no failed units"
fi

section "Ollama"
ollama_api_version="$(curl -fsS "$OLLAMA_URL/api/version" 2>/dev/null | jq -r '.version // empty' 2>/dev/null || true)"
ollama_version="$ollama_api_version"
if [[ -z "$ollama_version" && -x /usr/local/bin/ollama ]]; then
  ollama_version="$(HOME=/var/lib/ollama /usr/local/bin/ollama --version 2>&1 | head -1 || true)"
fi
info "active Ollama version: ${ollama_version:-unknown}"
if ((agent_active)); then
  ollama_semver="$(grep -oE '[0-9]+\.[0-9]+\.[0-9]+' <<< "$ollama_version" | head -1 || true)"
  if [[ "$ollama_semver" == "$BC250_OLLAMA_VERSION" ]]; then
    ok "exclusive agent Ollama matches package standard $BC250_OLLAMA_VERSION"
  elif [[ -n "$ollama_semver" ]]; then
    warn "agent Ollama $ollama_semver differs from package standard $BC250_OLLAMA_VERSION"
  else
    warn "agent Ollama version could not be parsed"
  fi
else
  lane_versions=()
  version_mismatch=0
  for port in 11434 11435 11437; do
    lane_version="$(curl -fsS "http://127.0.0.1:${port}/api/version" 2>/dev/null | jq -r '.version // empty' 2>/dev/null || true)"
    lane_versions+=(":${port}=${lane_version:-unavailable}")
    [[ "$lane_version" == "$BC250_OLLAMA_VERSION" ]] || version_mismatch=1
  done
  info "Ollama lane versions: ${lane_versions[*]}"
  if ((version_mismatch == 0)); then
    ok "main/task/embedding Ollama lanes all match package standard $BC250_OLLAMA_VERSION"
  else
    warn "one or more normal Ollama lanes differ from package standard $BC250_OLLAMA_VERSION; treat this as deliberate runtime drift"
  fi
fi
ollama_tags="$(curl -fsS "$OLLAMA_URL/api/tags" 2>/dev/null || true)"
if [[ -n "$ollama_tags" ]]; then
  ok "active Ollama API reachable at $OLLAMA_URL"
  tag_count="$(jq '.models | length' <<< "$ollama_tags" 2>/dev/null || echo '?')"
  loaded_count="$(curl -fsS "$OLLAMA_URL/api/ps" | jq '.models | length' 2>/dev/null || echo '?')"
  if ((agent_active)); then
    info "registered models: agent=$tag_count; currently loaded=$loaded_count"
  else
    task_count="$(curl -fsS http://127.0.0.1:11435/api/tags 2>/dev/null | jq '.models | length' 2>/dev/null || echo '?')"
    embedding_count="$(curl -fsS http://127.0.0.1:11437/api/tags 2>/dev/null | jq '.models | length' 2>/dev/null || echo '?')"
    info "registered models by lane: main=$tag_count task=$task_count embedding=$embedding_count; main currently loaded=$loaded_count"

    owui_models_file="${BC250_OWUI_MODELS_FILE:-/usr/share/bc250-llm-server/openwebui/models.json}"
    if [[ ! -r "$owui_models_file" ]]; then
      owui_models_file="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/../../config/openwebui/models.json"
    fi
    if [[ -r "$owui_models_file" ]]; then
      while IFS= read -r required_model; do
        [[ -n "$required_model" ]] || continue
        if jq -e --arg model "$required_model" \
            'any(.models[]?; (.name | sub(":latest$"; "")) == $model)' \
            <<< "$ollama_tags" >/dev/null 2>&1; then
          ok "active Open WebUI role base model is registered: $required_model"
        else
          bad "active Open WebUI role base model is not registered on main Ollama: $required_model"
        fi
      done < <(jq -r '.models[] | select(.is_active == true) | .base_model_id // empty | sub(":latest$"; "")' "$owui_models_file" | awk 'NF && !seen[$0]++')
    else
      bad "package Open WebUI model preset file is unavailable for active base-model verification"
    fi
  fi
else
  bad "active Ollama API unavailable at $OLLAMA_URL"
fi
ollama_env="$(systemctl show ollama.service -p Environment --value 2>/dev/null || true)"
for key in OLLAMA_CONTEXT_LENGTH OLLAMA_KV_CACHE_TYPE OLLAMA_FLASH_ATTENTION \
  OLLAMA_NUM_PARALLEL OLLAMA_MAX_LOADED_MODELS OLLAMA_HOST OLLAMA_MODELS OLLAMA_NO_CLOUD; do
  value="$(grep -oE "${key}=[^ ]+" <<< "$ollama_env" | tail -1 || true)"
  [[ -n "$value" ]] && info "$value" || warn "$key is not visible in the effective service environment"
done
if grep -qE '(^| )OLLAMA_NO_CLOUD=1( |$)' <<< "$ollama_env"; then
  ok "main Ollama cloud features are disabled"
else
  bad "main Ollama is missing OLLAMA_NO_CLOUD=1"
fi

if command -v journalctl >/dev/null 2>&1; then
  ollama_log="$(journalctl -b --no-pager -n 1000 \
    -u ollama.service -u ollama-task.service -u ollama-embedding.service -u ollama-agent.service \
    2>/dev/null || true)"
  kernel_log="$(journalctl -k -b --no-pager -n 1000 2>/dev/null || \
    dmesg 2>/dev/null | tail -n 1000 || true)"
  vulkan_failures="$(printf '%s\n%s\n' "$ollama_log" "$kernel_log" | \
    grep -Ei 'ErrorDeviceLost|Not enough memory for command submission|ring comp_[[:alnum:]_.-]+[[:space:]]+timeout' | \
    tail -n 20 || true)"
  if [[ -n "$vulkan_failures" ]]; then
    warn "recent Ollama/AMDGPU logs contain Vulkan device-loss or compute-ring failures"
    printf '%s\n' "$vulkan_failures" | sed 's/^/    /'
    info "for long-prompt timeouts, test a smaller num_batch in an operator Modelfile"
  elif [[ -n "$ollama_log" || -n "$kernel_log" ]]; then
    ok "no known Vulkan device-loss or compute-ring failure pattern in recent logs"
  else
    warn "Ollama and kernel journals are unreadable; Vulkan failure patterns were not checked"
  fi
else
  warn "journalctl is unavailable; Vulkan failure patterns were not checked"
fi

section "Documents / RAG"
desired_state="${BC250_OWUI_DESIRED_STATE:-/usr/share/bc250-llm-server/openwebui/desired-state.json}"
if [[ ! -r "$desired_state" ]]; then
  desired_state="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/../../config/openwebui/desired-state.json"
fi
rag_embedding_model="$(jq -r '.embedding.RAG_EMBEDDING_MODEL // empty' "$desired_state" 2>/dev/null || true)"
rag_embedding_url="$(jq -r '.embedding.ollama_config.url // empty' "$desired_state" 2>/dev/null || true)"
rag_extraction_engine="$(jq -r '.rag.CONTENT_EXTRACTION_ENGINE // empty' "$desired_state" 2>/dev/null || true)"
embedding_tags="$(curl -fsS http://127.0.0.1:11437/api/tags 2>/dev/null || true)"
if [[ -n "$rag_embedding_model" ]]; then
  info "Package RAG embedding default: $rag_embedding_model"
  [[ -n "$rag_embedding_url" ]] && info "Package RAG embedding endpoint: $rag_embedding_url"
  if ((agent_active)); then
    info "embedding registration check deferred while exclusive agent mode stops :11437"
  elif ((!embedding_lane_active)); then
    skipped "RAG embedding registration unavailable because ollama-embedding.service is inactive"
  elif [[ -n "$embedding_tags" ]] && jq -e --arg model "$rag_embedding_model" \
      'any(.models[]?; (.name | sub(":latest$"; "")) == $model)' \
      <<< "$embedding_tags" >/dev/null 2>&1; then
    ok "default RAG embedding model is registered with dedicated embedding Ollama"
  else
    bad "default RAG embedding model is not registered on dedicated embedding Ollama :11437"
  fi
else
  bad "package Open WebUI desired state does not define a RAG embedding model"
fi
[[ -n "$rag_extraction_engine" ]] && info "Package extraction engine: $rag_extraction_engine" || \
  warn "package Open WebUI desired state does not define an extraction engine"
if command -v bc250 >/dev/null 2>&1; then
  if [[ -n "${OWUI_API_KEY:-}" ]]; then
    owui_drift="$(bc250 openwebui-setup status 2>&1)"
    owui_rc=$?
    if ((owui_rc == 0)); then
      ok "authenticated Open WebUI package-owned desired-state check passed"
    elif ((owui_rc == 2)); then
      warn "Open WebUI package-owned settings differ from the reviewed baseline; this may be an intentional operator override"
      printf '%s\n' "$owui_drift" | sed 's/^/    /'
    else
      warn "authenticated Open WebUI desired-state check could not complete"
      printf '%s\n' "$owui_drift" | sed 's/^/    /'
    fi
  else
    skipped "authenticated Open WebUI desired-state check (no API token supplied)"
  fi
else
  warn "bc250 openwebui-setup is not installed; live Open WebUI drift was not checked"
fi
info "Open WebUI database settings can override bootstrap environment defaults after first launch"

section "Local endpoints"
curl -fsS http://127.0.0.1:3000/api/version >/dev/null && ok "Open WebUI backend ready" || bad "Open WebUI backend unavailable/not ready"
curl -fsS http://127.0.0.1/api/version >/dev/null && ok "Open WebUI front door usable through nginx" || bad "Open WebUI front door unavailable/not usable (listener-only/502 is not ready)"

container_http() {
  local url="$1"
  podman exec open-webui python -c \
    'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=10).read()' \
    "$url" >/dev/null 2>&1
}

if podman exec open-webui getent hosts tika >/dev/null 2>&1; then
  ok "Open WebUI resolves private Tika alias"
  if container_http "http://tika:9998/version"; then
    ok "Open WebUI reaches private Tika HTTP endpoint"
  else
    bad "Open WebUI resolves Tika but cannot reach its HTTP endpoint"
  fi
else
  bad "Open WebUI cannot resolve private Tika alias"
  info "private Tika HTTP check skipped because container DNS resolution failed"
fi

if podman exec open-webui getent hosts host.containers.internal >/dev/null 2>&1; then
  ok "Open WebUI resolves host.containers.internal"
else
  bad "Open WebUI cannot resolve host.containers.internal"
fi
if ((agent_active)); then
  if container_http "http://host.containers.internal:11436/api/tags"; then
    ok "Open WebUI container reaches active agent Ollama host gateway :11436"
  else
    bad "Open WebUI container cannot reach active agent Ollama host gateway :11436"
  fi
else
  for port in 11434 11435 11437; do
    if [[ "$port" == 11435 ]] && ((!task_lane_active)); then
      skipped "Open WebUI task gateway check unavailable because ollama-task.service is inactive"
      continue
    fi
    if [[ "$port" == 11437 ]] && ((!embedding_lane_active)); then
      skipped "Open WebUI embedding gateway check unavailable because ollama-embedding.service is inactive"
      continue
    fi
    if container_http "http://host.containers.internal:${port}/api/tags"; then
      ok "Open WebUI container reaches Ollama host gateway :$port"
    else
      bad "Open WebUI container cannot reach Ollama host gateway :$port"
    fi
  done
fi

section "Listeners and firewall"
listeners="$(ss -H -lnt 2>/dev/null || true)"
awk '$4 ~ /:80$/ {found=1} END{exit found?0:1}' <<< "$listeners" && ok "HTTP :80 listener exists" || bad "HTTP :80 listener missing"
awk '$4 ~ /:9998$/ {found=1} END{exit found?0:1}' <<< "$listeners" && bad "host has Tika :9998 listener" || ok "no host Tika :9998 listener"
for port in 11434 11435 11436 11437; do
  ollama_listeners="$(awk -v suffix=":$port" 'index($4, suffix) == length($4)-length(suffix)+1 {print $4}' <<< "$listeners")"
  if [[ -z "$ollama_listeners" ]]; then
    if ((agent_active)) && [[ "$port" == 11436 ]]; then
      bad "agent Ollama :11436 listener missing in exclusive agent mode"
    elif ((!agent_active)) && [[ "$port" == 11434 ]]; then
      bad "main Ollama :11434 listener missing in normal mode"
    else
      info "Ollama :$port listener absent as allowed for the current mode/configuration"
    fi
    continue
  fi
  if grep -Evq "^(\*|0\.0\.0\.0|\[::\]):$port$" <<< "$ollama_listeners"; then
    warn "Ollama :$port has an unexpected bind: $(tr '\n' ' ' <<< "$ollama_listeners")"
  else
    info "Ollama :$port uses the expected container-bridge listener; firewalld must keep it off the LAN"
  fi
done

webui="$(awk '$4 ~ /:3000$/ {print $4}' <<< "$listeners")"
if [[ -z "$webui" ]]; then
  bad "Open WebUI :3000 listener missing"
elif grep -Evq '^(127\.0\.0\.1|\[::1\]):3000$' <<< "$webui"; then
  bad "Open WebUI is not loopback-only: $webui"
else
  ok "Open WebUI :3000 is loopback-only"
fi
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
  mapfile -t active_zones < <(firewall-cmd --get-active-zones 2>/dev/null | awk '/^[^[:space:]]/{print $1}')
  ((${#active_zones[@]})) || active_zones+=("$(firewall-cmd --get-default-zone 2>/dev/null)")
  http_open=0
  http_unverified=0
  internal_open=0
  for zone in "${active_zones[@]}"; do
    if ! services="$(firewall-cmd --zone="$zone" --list-services 2>/dev/null)" ||
       ! ports="$(firewall-cmd --zone="$zone" --list-ports 2>/dev/null)" ||
       ! rich="$(firewall-cmd --zone="$zone" --list-rich-rules 2>/dev/null)"; then
      bad "cannot inspect active firewalld zone $zone; firewall publication/isolation is unverified"
      http_unverified=1
      internal_open=1
      continue
    fi

    zone_http_open=""
    zone_http_unknown=""
    if grep -qw http <<< "$services" || firewall_port_list_exposes_tcp_port "$ports" 80; then
      zone_http_open="direct service/port/range"
    else
      for service in $services; do
        [[ "$service" == http ]] && continue
        if firewalld_service_exposes_tcp_port "$service" 80; then
          zone_http_open="service $service"
          break
        else
          service_state=$?
          if ((service_state == 2)); then
            zone_http_unknown="cannot inspect service $service"
            break
          fi
        fi
      done
    fi
    if [[ -z "$zone_http_open" && -z "$zone_http_unknown" ]]; then
      if firewall_rich_rules_expose_tcp_port "$rich" 80; then
        zone_http_open="rich rule"
      else
        rich_state=$?
        ((rich_state == 2)) && zone_http_unknown="cannot inspect service referenced by rich rule"
      fi
    fi
    [[ -n "$zone_http_open" ]] && http_open=1
    [[ -n "$zone_http_unknown" ]] && http_unverified=1

    zone_internal_reason=""
    zone_internal_unknown=""
    if firewall_port_list_exposes_internal "$ports"; then
      zone_internal_reason="direct port/range"
    else
      for service in $services; do
        if firewalld_service_exposes_internal "$service"; then
          zone_internal_reason="service $service"
          break
        else
          service_state=$?
          if ((service_state == 2)); then
            zone_internal_unknown="cannot inspect service $service"
            break
          fi
        fi
      done
    fi
    if [[ -z "$zone_internal_reason" && -z "$zone_internal_unknown" ]]; then
      if firewall_rich_rules_expose_internal "$rich"; then
        zone_internal_reason="rich rule"
      else
        rich_state=$?
        ((rich_state == 2)) && zone_internal_unknown="cannot inspect service referenced by rich rule"
      fi
    fi
    if [[ -n "$zone_internal_unknown" ]]; then
      bad "cannot verify internal-port isolation in active firewalld zone $zone ($zone_internal_unknown)"
      internal_open=1
    elif [[ -n "$zone_internal_reason" ]]; then
      bad "internal port exposed in active firewalld zone $zone ($zone_internal_reason)"
      internal_open=1
    fi
  done
  if ((http_open)); then
    ok "HTTP allowed in an active firewalld zone"
  elif ((http_unverified)); then
    bad "HTTP publication could not be verified in active firewalld zones"
  else
    bad "HTTP not allowed in any active firewalld zone"
  fi
  ((internal_open)) || ok "no internal port exposed in active firewalld zones"
else
  bad "firewalld inactive; Ollama may be exposed through its all-interface listener"
fi

section "Package configuration"
packaged_models=/usr/share/bc250-llm-server/model-management/modelfiles
operator_models=/etc/bc250-llm-server/models.d
[[ -d "$packaged_models" ]] && ok "packaged Modelfile directory installed" || bad "packaged Modelfile directory missing"
[[ -d "$operator_models" ]] && ok "operator models.d directory installed" || bad "operator models.d directory missing"
model_count="$(find "$packaged_models" "$operator_models" -maxdepth 1 -type f -name '*.Modelfile' 2>/dev/null | wc -l)"
((model_count > 0)) && ok "$model_count Modelfile template(s) discoverable" || bad "no Modelfile templates found"
if grep -RqsE 'hf_[A-Za-z0-9]{20,}|WEBUI_ADMIN_PASSWORD=' \
  /etc/bc250-llm-server /usr/share/bc250-llm-server 2>/dev/null; then
  bad "token or administrator password found in packaged configuration"
else
  ok "no embedded token or administrator password found"
fi

section "Optional model test"
if [[ "$RUN_MODEL_TESTS" == 1 ]]; then
  mapfile -t models < <(curl -fsS "$OLLAMA_URL/api/tags" | jq -r '.models[].name' | grep -viE 'embed|nomic')
  ((${#models[@]})) || info "no chat models registered"
  for model in "${models[@]}"; do
    payload="$(jq -nc --arg model "$model" \
      '{model:$model,prompt:"Reply exactly: ok",stream:false,keep_alive:"2m",options:{num_predict:16}}')"
    if curl -fsS --max-time 900 -H 'Content-Type: application/json' \
      -d "$payload" "$OLLAMA_URL/api/generate" \
      | jq -e '.done == true and (.error == null)' >/dev/null 2>&1; then
      ok "$model generated"
    else
      bad "$model failed generation"
    fi
  done
else
  info "model tests skipped; set RUN_MODEL_TESTS=1 to enable"
fi

finish_section
if ((SUMMARY)); then
  printf '\nVerification: %d ok / %d warn / %d fail / %d skipped\n' \
    "$PASS" "$WARN" "$FAIL" "$SKIP"
else
  printf '\n================ %d ok / %d warn / %d fail / %d skipped ================\n' \
    "$PASS" "$WARN" "$FAIL" "$SKIP"
fi
if ((FAIL == 0 && WARN == 0)); then
  if ((SKIP == 1)); then
    echo "Server verification completed successfully; 1 optional/authenticated check was skipped."
  elif ((SKIP > 1)); then
    printf 'Server verification completed successfully; %d optional/authenticated checks were skipped.\n' "$SKIP"
  else
    echo "Server verification completed successfully."
  fi
elif ((FAIL == 0)); then
  echo "Server verification completed with warnings; review the items above."
else
  echo "Verification failed; fix the reported failures before wider use."
fi
exit "$FAIL"
