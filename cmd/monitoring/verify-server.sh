#!/usr/bin/env bash
set -uo pipefail

OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
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

if [[ ${EUID} -ne 0 ]]; then
  warn "not running as root; Podman, journal and live-CU checks may be incomplete"
fi

section "Platform"
info "kernel: $(uname -r)"
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

section "GPU memory and storage"
gtt="$(read_param /sys/module/amdgpu/parameters/gttsize)"
pages="$(read_param /sys/module/ttm/parameters/pages_limit)"
pool="$(read_param /sys/module/ttm/parameters/page_pool_size)"
info "amdgpu.gttsize: $gtt"
info "ttm.pages_limit: $pages"
info "ttm.page_pool_size: $pool"
if [[ "$pages" =~ ^[0-9]+$ ]]; then
  gib="$(awk -v p="$pages" 'BEGIN {printf "%.2f", p*4096/1024/1024/1024}')"
  info "TTM pages_limit capacity: approximately ${gib} GiB"
  ((pages >= 4194304)) && ok "TTM limit supports the reviewed full-memory profile" || \
    warn "TTM limit is below 4194304 pages; large models may hit an allocation cap"
else
  warn "kernel does not expose a numeric TTM pages_limit"
fi

cmdline="$(cat /proc/cmdline 2>/dev/null || true)"
info "kernel arguments: $cmdline"
grep -qw 'ttm.pages_limit=4194304' <<< "$cmdline" && \
  ok "reviewed 16 GiB TTM limit is active" || \
  warn "ttm.pages_limit=4194304 is not present on the active kernel command line"
for token in amdgpu.gttsize ttm.page_pool_size amdgpu.ppfeaturemask; do
  grep -qE "(^| )${token}=" <<< "$cmdline" && warn "obsolete kernel argument remains active: $token"
done

while read -r fs size used avail pct mount; do
  [[ "$fs" == Filesystem ]] && continue
  info "$mount: $avail available ($pct used)"
  pct_num="${pct%%%}"
  [[ "$pct_num" =~ ^[0-9]+$ ]] && ((pct_num >= 95)) && bad "$mount is critically full"
done < <(df -h / /var/lib/bc250-llm-server 2>/dev/null | awk '!seen[$1]++')

section "Swap and zram"
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
if [[ -r "$config" ]]; then
  ok "governor config installed"
  min="$(awk '/^\[frequency-range\]/{s=1;next} /^\[/{s=0} s&&$1=="min"{print $3;exit}' "$config")"
  max="$(awk '/^\[frequency-range\]/{s=1;next} /^\[/{s=0} s&&$1=="max"{print $3;exit}' "$config")"
  info "governor range: ${min:-unknown}-${max:-unknown} MHz"
else
  bad "governor config missing"
fi
if command -v sensors >/dev/null 2>&1; then
  temp_lines="$(sensors 2>/dev/null | grep -Ei 'edge:|junction:|mem:|power1:' | head -12 || true)"
  [[ -n "$temp_lines" ]] && printf '%s\n' "$temp_lines" | sed 's/^/  /' || warn "no GPU temperature lines found"
fi
mods="$(lsmod 2>/dev/null | awk '{print $1}')"
if grep -qx nct6683 <<< "$mods" && grep -Eq '^nct6687' <<< "$mods"; then
  bad "nct6683 and nct6687 drivers are both loaded; they conflict"
elif grep -Eq '^nct6687' <<< "$mods"; then
  warn "experimental nct6687 PWM driver is loaded; rebuild/check it after kernel updates"
elif grep -qx nct6683 <<< "$mods"; then
  ok "safe nct6683 sensor driver is loaded"
else
  warn "neither nct6683 nor nct6687 sensor driver is loaded"
fi

section "Services"
for unit in cyan-skillfish-governor-smu.service ollama.service \
  tika.service open-webui.service nginx.service; do
  if systemctl is-active --quiet "$unit" 2>/dev/null; then
    ok "$unit active"
  else
    bad "$unit inactive"
  fi
done
if id -nG ollama 2>/dev/null | grep -qw render && \
   id -nG ollama 2>/dev/null | grep -qw video; then
  ok "ollama has render/video access"
else
  bad "ollama lacks render/video access"
fi

section "Ollama"
if curl -fsS "$OLLAMA_URL/api/tags" >/dev/null; then
  ok "Ollama API reachable"
  tag_count="$(curl -fsS "$OLLAMA_URL/api/tags" | jq '.models | length' 2>/dev/null || echo '?')"
  loaded_count="$(curl -fsS "$OLLAMA_URL/api/ps" | jq '.models | length' 2>/dev/null || echo '?')"
  info "registered models: $tag_count; currently loaded: $loaded_count"
else
  bad "Ollama API unavailable"
fi
ollama_env="$(systemctl show ollama.service -p Environment --value 2>/dev/null || true)"
for key in OLLAMA_CONTEXT_LENGTH OLLAMA_KV_CACHE_TYPE OLLAMA_FLASH_ATTENTION \
  OLLAMA_NUM_PARALLEL OLLAMA_MAX_LOADED_MODELS OLLAMA_HOST OLLAMA_MODELS; do
  value="$(grep -oE "${key}=[^ ]+" <<< "$ollama_env" | tail -1 || true)"
  [[ -n "$value" ]] && info "$value" || warn "$key is not visible in the effective service environment"
done

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
webui="$(awk '$4 ~ /:3000$/ {print $4}' <<< "$listeners")"
if [[ -z "$webui" ]]; then
  bad "Open WebUI :3000 listener missing"
elif grep -Evq '^(127\.0\.0\.1|\[::1\]):3000$' <<< "$webui"; then
  bad "Open WebUI is not loopback-only: $webui"
else
  ok "Open WebUI :3000 is loopback-only"
fi
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
  services="$(firewall-cmd --list-services 2>/dev/null || true)"
  ports="$(firewall-cmd --list-ports 2>/dev/null || true)"
  grep -qw http <<< "$services" && ok "HTTP allowed in firewalld" || bad "HTTP not allowed in firewalld"
  grep -Eq '11434|11435|11436|3000|9998' <<< "$ports" && bad "internal port explicitly opened in firewalld" || ok "no internal port opened explicitly"
else
  bad "firewalld inactive; Ollama may be exposed through its all-interface listener"
fi

section "Package configuration"
[[ -r /etc/bc250-llm-server/production-models.toml ]] && ok "production model catalog installed" || bad "production model catalog missing"
[[ -r /etc/bc250-llm-server/experiments-models.toml ]] && ok "experiment model catalog installed" || bad "experiment model catalog missing"
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
