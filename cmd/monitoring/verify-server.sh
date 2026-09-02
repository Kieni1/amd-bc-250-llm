#!/usr/bin/env bash
set -uo pipefail

OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
runtime_env="${BC250_RUNTIME_ENV:-/usr/share/bc250-llm-server/runtime.env}"
if [[ ! -r "$runtime_env" ]]; then runtime_env="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/../../config/runtime.env"; fi
if [[ -r "$runtime_env" ]]; then # shellcheck disable=SC1090
  source "$runtime_env"
else
  BC250_OLLAMA_VERSION=0.33.2
fi
RUN_MODEL_TESTS="${RUN_MODEL_TESTS:-0}"
PASS=0
WARN=0
FAIL=0

ok() { printf '  [ OK ] %s\n' "$1"; PASS=$((PASS + 1)); }
warn() { printf '  [WARN] %s\n' "$1"; WARN=$((WARN + 1)); }
bad() { printf '  [FAIL] %s\n' "$1"; FAIL=$((FAIL + 1)); }
info() { printf '  [info] %s\n' "$1"; }
section() { printf '\n=== %s ===\n' "$1"; }
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

if [[ ${EUID} -ne 0 ]]; then
  warn "not running as root; Podman, journal and live-CU checks may be incomplete"
fi

section "Platform"
kernel="$(uname -r)"
info "running kernel: $kernel"
if [[ -e "/usr/lib/modules/$kernel/build" ]]; then
  ok "matching kernel-devel/build tree is present"
else
  warn "matching kernel-devel/build tree is missing for $kernel"
fi
if command -v modinfo >/dev/null 2>&1; then
  amdgpu_path="$(modinfo -n amdgpu 2>/dev/null || true)"
  amdgpu_vermagic="$(modinfo -F vermagic amdgpu 2>/dev/null | awk 'NR == 1 {print $1}' || true)"
  amdgpu_metadata="$(modinfo amdgpu 2>/dev/null || true)"
  info "amdgpu module: ${amdgpu_path:-unknown}"
  info "amdgpu vermagic: ${amdgpu_vermagic:-unknown}"
  if grep -q 'bc250_cc_write_mode' <<< "$amdgpu_metadata"; then
    info "amdgpu type: modified 40-CU module"
  else
    info "amdgpu type: stock or unrecognized"
  fi
  if [[ -n "$amdgpu_vermagic" && "$amdgpu_vermagic" != "$kernel" ]]; then
    warn "amdgpu was built for a different kernel; rebuild/reapply the 40-CU module"
  fi
else
  warn "modinfo is unavailable; AMDGPU kernel compatibility was not checked"
fi
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
[[ -n "$cpufreq_driver" ]] && info "cpufreq driver: $cpufreq_driver" || warn "cpufreq driver is not exposed"
[[ -n "$cpufreq_governor" ]] && info "cpufreq governor: $cpufreq_governor" || warn "cpufreq governor is not exposed"
missing_idle="$(for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
  [[ -d "$cpu" ]] || continue
  [[ -r "$cpu/online" && "$(cat "$cpu/online")" == 0 ]] && continue
  compgen -G "$cpu/cpuidle/state*" >/dev/null || printf '%s\n' "${cpu##*/}"
done | paste -sd, -)"
if [[ -n "$missing_idle" ]]; then
  info "online CPUs without cpuidle states: $missing_idle"
  [[ "$threads" == 16 ]] && warn "16 threads are active but some CPUs lack C-states; check idle power/correctness" || \
    info "C-state availability is incomplete"
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
grep -qE '(^| )amd_iommu=on( |$)' <<< "$cmdline" && bad "amd_iommu=on is active; BC-250 community documentation requires IOMMU disabled" || ok "amd_iommu=on is not active"
grep -qE '(^| )nomodeset( |$)' <<< "$cmdline" && bad "nomodeset is still active and prevents normal GPU acceleration" || ok "nomodeset is not active"
case "$kernel" in
  6.15.[0-6]-*|6.15.[0-6]|6.17.[89]-*|6.17.10-*|6.17.[89]|6.17.10) warn "running kernel is in a BC-250 community-documented regression range" ;;
esac

section "GFX1013 compute queues"
gfx1013_root=/opt/bc250-gfx1013
gfx1013_marker=bc250.gfx1013_v33=1
dedicated_compute_queues=0
if command -v vulkaninfo >/dev/null 2>&1; then
  queue_flags="$(vulkaninfo 2>/dev/null | \
    awk '/queueFlags[[:space:]]*=/ {print}' || true)"
  dedicated_compute_queues="$(awk '
    /QUEUE_COMPUTE_BIT/ && !/QUEUE_GRAPHICS_BIT/ {count++}
    END {print count + 0}
  ' <<< "$queue_flags")"
  if ((dedicated_compute_queues > 0)); then
    info "dedicated Vulkan compute queue families: $dedicated_compute_queues"
  else
    info "dedicated Vulkan compute queue: not exposed"
  fi
else
  warn "vulkaninfo is unavailable; dedicated compute queues were not checked"
fi

gfx1013_mesa_installed=0
gfx1013_mesa_selected=0
gfx1013_kernel_active=0
gfx1013_selector="${VK_DRIVER_FILES:-}"$'\n'"${VK_ICD_FILENAMES:-}"
gfx1013_selector+=$'\n'"$(systemctl show ollama.service -p Environment --value 2>/dev/null || true)"
ollama_main_pid="$(systemctl show ollama.service -p MainPID --value 2>/dev/null || true)"
if [[ "$ollama_main_pid" =~ ^[1-9][0-9]*$ && -r "/proc/$ollama_main_pid/environ" ]]; then
  gfx1013_selector+=$'\n'"$(tr '\0' '\n' < "/proc/$ollama_main_pid/environ" 2>/dev/null || true)"
fi
[[ -d "$gfx1013_root" ]] && gfx1013_mesa_installed=1
grep -qF "$gfx1013_root" <<< "$gfx1013_selector" && gfx1013_mesa_selected=1
grep -qw "$gfx1013_marker" <<< "$cmdline" && gfx1013_kernel_active=1

gfx1013_module_active=0
if ((gfx1013_kernel_active)) && [[ -d /sys/module/amdgpu ]] && \
   [[ "${amdgpu_path:-}" == */updates/amdgpu.ko* ]] && \
   [[ "${amdgpu_vermagic:-}" == "$kernel" ]]; then
  gfx1013_module_active=1
fi

if ((gfx1013_mesa_installed)); then
  info "optional GFX1013 Mesa tree: $gfx1013_root"
else
  info "optional GFX1013 Mesa tree: not installed"
fi
if ((gfx1013_mesa_selected)); then
  info "custom GFX1013 Mesa ICD is selected by this environment or Ollama"
  if ((!gfx1013_kernel_active)); then
    bad "custom GFX1013 Mesa is selected without the patched boot marker; disable the custom ICD"
  elif ((!gfx1013_module_active)); then
    bad "GFX1013 patched boot is marked active, but the matching updates/amdgpu module was not verified"
  else
    ok "custom GFX1013 Mesa and matching patched AMDGPU are active"
  fi
elif ((gfx1013_mesa_installed)); then
  if ((gfx1013_kernel_active && gfx1013_module_active)); then
    info "GFX1013 patched kernel is active; custom Mesa is not selected for this verifier or Ollama"
  else
    info "GFX1013 files are installed but not selected; patched boot is not active"
  fi
fi
if ((dedicated_compute_queues > 0)); then
  if ((gfx1013_mesa_selected && gfx1013_module_active)); then
    ok "dedicated compute queue is exposed by the verified paired patch stack"
  else
    warn "dedicated compute queue is exposed without a fully verified GFX1013 Mesa/kernel pair"
  fi
fi

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
if swapon --show --noheadings 2>/dev/null | grep -q .; then
  swapon --show 2>/dev/null | sed 's/^/  /'
  ok "swap is active"
else
  warn "no swap is active"
fi
if zramctl --noheadings 2>/dev/null | grep -q .; then
  zramctl 2>/dev/null | sed 's/^/  /'
  zram_size="$(zramctl --bytes --noheadings --output DISKSIZE 2>/dev/null | awk '{s+=$1} END{print s+0}')"
  ((zram_size > 4*1024*1024*1024)) && \
    warn "zram exceeds 4 GiB and competes with the unified model-memory pool" || \
    ok "zram size is compatible with a dedicated LLM profile"
else
  info "no active zram device"
fi
if swapon --show --noheadings --output NAME 2>/dev/null | grep -qv '^/dev/zram'; then
  ok "disk-backed swap safety margin is active"
else
  warn "no disk-backed swap safety margin is active"
fi

section "Compute units"
if command -v bc250-cu-status >/dev/null 2>&1; then
  cu_output="$(bc250-cu-status 2>&1 || true)"
else
  cu_output="$(/usr/libexec/bc250-llm-server/cu-status.sh 2>&1 || true)"
fi
printf '%s\n' "$cu_output" | sed 's/^/  /'
if grep -qE 'CUs active[[:space:]]*& routed[[:space:]]*:[[:space:]]*40/40' <<< "$cu_output"; then
  ok "live CU manager reports 40/40 routed"
elif grep -qE 'CUs active[[:space:]]*& routed[[:space:]]*:' <<< "$cu_output"; then
  warn "live CU manager reports a partial CU routing table"
else
  info "no parseable live CU routing report"
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
    warn "governor fix-freq is not explicit; v0.4.12 defaults it to false"
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
  [[ -n "$sensor_lines" ]] && printf '%s\n' "$sensor_lines" | sed 's/^/  /' || \
    warn "no selected temperature, power or fan readings found"
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
    if systemctl list-unit-files "$unit" --no-legend 2>/dev/null | grep -q "^$unit"; then
      systemctl is-active --quiet "$unit" 2>/dev/null && ok "$unit active" || bad "$unit installed but inactive"
    else
      info "$unit is not installed (optional model lane not configured)"
    fi
  done
fi
if systemctl is-enabled --quiet ollama-agent.service 2>/dev/null; then
  warn "ollama-agent.service is enabled at boot; agent mode is intended to be exclusive and operator-entered"
else
  ok "ollama-agent.service is not enabled at boot"
fi
if id -nG ollama 2>/dev/null | grep -qw render && \
   id -nG ollama 2>/dev/null | grep -qw video; then
  ok "ollama has render/video access"
else
  bad "ollama lacks render/video access"
fi

section "Ollama"
ollama_api_version="$(curl -fsS "$OLLAMA_URL/api/version" 2>/dev/null | jq -r '.version // empty' 2>/dev/null || true)"
ollama_version="$ollama_api_version"
if [[ -z "$ollama_version" && -x /usr/local/bin/ollama ]]; then
  ollama_version="$(HOME=/var/lib/ollama /usr/local/bin/ollama --version 2>&1 | head -1 || true)"
fi
info "Ollama version: ${ollama_version:-unknown}"
ollama_semver="$(grep -oE '[0-9]+\.[0-9]+\.[0-9]+' <<< "$ollama_version" | head -1 || true)"
if [[ "$ollama_semver" == "$BC250_OLLAMA_VERSION" ]]; then
  ok "Ollama matches the package standard $BC250_OLLAMA_VERSION"
elif [[ -n "$ollama_semver" ]]; then
  warn "Ollama $ollama_semver differs from package standard $BC250_OLLAMA_VERSION; treat this as a deliberate runtime test"
else
  warn "Ollama version could not be parsed"
fi
ollama_tags="$(curl -fsS "$OLLAMA_URL/api/tags" 2>/dev/null || true)"
if [[ -n "$ollama_tags" ]]; then
  ok "active Ollama API reachable at $OLLAMA_URL"
  tag_count="$(jq '.models | length' <<< "$ollama_tags" 2>/dev/null || echo '?')"
  loaded_count="$(curl -fsS "$OLLAMA_URL/api/ps" | jq '.models | length' 2>/dev/null || echo '?')"
  info "registered models: $tag_count; currently loaded: $loaded_count"
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
rag_env="$(podman inspect open-webui --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null || true)"
rag_embedding_model="$(awk -F= '$1 == "RAG_EMBEDDING_MODEL" {sub(/^[^=]*=/, ""); print; exit}' <<< "$rag_env")"
rag_embedding_url="$(awk -F= '$1 == "RAG_OLLAMA_BASE_URL" {sub(/^[^=]*=/, ""); print; exit}' <<< "$rag_env")"
rag_extraction_engine="$(awk -F= '$1 == "CONTENT_EXTRACTION_ENGINE" {sub(/^[^=]*=/, ""); print; exit}' <<< "$rag_env")"
embedding_tags="$(curl -fsS http://127.0.0.1:11437/api/tags 2>/dev/null || true)"
if [[ -n "$rag_embedding_model" ]]; then
  info "Open WebUI embedding default: $rag_embedding_model"
  [[ -n "$rag_embedding_url" ]] && info "Open WebUI embedding endpoint: $rag_embedding_url"
  if ((agent_active)); then
    info "embedding registration check deferred while exclusive agent mode stops :11437"
  elif [[ -n "$embedding_tags" ]] && jq -e --arg model "$rag_embedding_model" \
      'any(.models[]?; (.name | sub(":latest$"; "")) == $model)' \
      <<< "$embedding_tags" >/dev/null 2>&1; then
    ok "default RAG embedding model is registered with dedicated embedding Ollama"
  else
    warn "default RAG embedding model is not registered on dedicated embedding Ollama :11437"
  fi
else
  warn "Open WebUI RAG embedding model is not visible in the container environment"
fi
[[ -n "$rag_extraction_engine" ]] && info "Open WebUI extraction engine: $rag_extraction_engine" || \
  warn "Open WebUI extraction engine is not visible in the container environment"
if command -v bc250-openwebui-setup >/dev/null 2>&1; then
  if [[ -n "${OWUI_API_KEY:-}" ]]; then
    owui_drift="$(bc250-openwebui-setup status 2>&1)"
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
    info "authenticated Open WebUI desired-state drift check skipped; set OWUI_API_KEY temporarily to enable"
  fi
else
  warn "bc250-openwebui-setup is not installed; live Open WebUI drift was not checked"
fi
info "Open WebUI database settings can override bootstrap environment defaults after first launch"

section "Local endpoints"
curl -fsS http://127.0.0.1:3000/ >/dev/null && ok "Open WebUI loopback endpoint reachable" || bad "Open WebUI unavailable"
curl -fsS http://127.0.0.1/ >/dev/null && ok "nginx HTTP endpoint reachable" || bad "nginx HTTP endpoint unavailable"
if podman exec open-webui python -c \
  'import urllib.request; urllib.request.urlopen("http://tika:9998/version", timeout=10).read()' \
  >/dev/null 2>&1; then
  ok "Open WebUI reaches private Tika"
else
  bad "private Tika connection failed"
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
  internal_open=0
  for zone in "${active_zones[@]}"; do
    services="$(firewall-cmd --zone="$zone" --list-services 2>/dev/null || true)"
    ports="$(firewall-cmd --zone="$zone" --list-ports 2>/dev/null || true)"
    rich="$(firewall-cmd --zone="$zone" --list-rich-rules 2>/dev/null || true)"
    grep -qw http <<< "$services" && http_open=1
    grep -Eq 'service name="http".*accept' <<< "$rich" && http_open=1
    if grep -Eq '(^|[^0-9])(11434|11435|11436|11437|3000|9998)(/|[^0-9]|$)' <<< "$ports" ||
       grep -E 'port port="(11434|11435|11436|11437|3000|9998)(-[0-9]+)?"' <<< "$rich" | grep -qE '(^| )accept( |$)'; then
      bad "internal port explicitly allowed in active firewalld zone $zone"
      internal_open=1
    fi
  done
  ((http_open)) && ok "HTTP allowed in an active firewalld zone" || bad "HTTP not allowed in any active firewalld zone"
  ((internal_open)) || ok "no internal port explicitly allowed in active firewalld zones"
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

printf '\n================ %d ok / %d warn / %d fail ================\n' "$PASS" "$WARN" "$FAIL"
if ((FAIL == 0)); then
  echo "Server checks completed. Review warnings before long-running or 40-CU workloads."
else
  echo "Fix failures before wider use."
fi
exit "$FAIL"
