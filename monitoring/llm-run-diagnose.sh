#!/usr/bin/env bash
# llm-run-diagnose.sh â€” BC-250 performance-parity CHECKER.
#
# Run on a NEW board; each check echoes the expected value FIRST, reads the live
# value, and verdicts it [ OK ] / [WARN] / [FAIL] so the board self-scores
# against the two reference boards we characterized (2026-07).
#
#   sudo ./llm-run-diagnose.sh                # full run incl. 60s load test
#   sudo ./llm-run-diagnose.sh --no-load      # static checks only
#   MODEL=gemma4-e4b sudo ./llm-run-diagnose.sh
#
# ===========================================================================
# REFERENCE DATASETS (gpt-oss-20b, mxfp4, num_ctx 16384):
#   Board A  "good bin"   : 84 tok/s decode | ~134W peak | ~31W idle | edge sensor
#   Board B  "ok bin"  : 73 tok/s decode | ~144W peak | ~38W idle | Tctl sensor
#   IDENTICAL on both: mclk 450, fclk 450, socclk 1254, 40/40 CU,
#     VBIOS 113-AMDRBN-003, SMU fw 88.6.0, Mesa 26.1.4, gov 0.4.11.
#
# THE ONE LAW OF THIS HARDWARE:
#   decode tok/s is MEMORY-BANDWIDTH-bound (mclk=450, governor CANNOT raise it).
#   GPU core clock (sclk) only affects PREFILL. So a decode gap between boards,
#   when mclk matches and both pin 2000MHz under load, is SILICON LEAKAGE
#   (compare the power line) â€” NOT cooling, NOT governor max, NOT a setting.
#   Proven this run: 1850->2100 MHz moved decode <2%; cooling 83C->70C moved 0%.
# ===========================================================================

set -uo pipefail
MODEL="${MODEL:-}"
OLLAMA="${OLLAMA_URL:-http://localhost:11434}"
LOAD_SECONDS="${LOAD_SECONDS:-60}"
NUM_PREDICT="${NUM_PREDICT:-2000}"
DO_LOAD=1; [[ "${1:-}" == "--no-load" ]] && DO_LOAD=0

cardg=/sys/class/drm/card*/device
hwmg=/sys/class/drm/card*/device/hwmon/hwmon*
pass=0; warn=0; fail=0
have(){ command -v "$1" >/dev/null 2>&1; }
active(){ cat $1 2>/dev/null | grep '\*' | tr -d ' *'; }   # starred pp_dpm line, cleaned

# Use the first installed model unless the operator supplied MODEL explicitly.
if [[ -z "$MODEL" ]] && have ollama; then
  MODEL=$(ollama list 2>/dev/null | awk 'NR > 1 {print $1; exit}')
fi
if [[ -z "$MODEL" ]]; then
  MODEL="<none>"
  DO_LOAD=0
fi

# verdict helpers: print aligned tag and tally
ok(){   printf '  [ OK ] %s\n' "$1"; pass=$((pass+1)); }
wn(){   printf '  [WARN] %s\n' "$1"; warn=$((warn+1)); }
fl(){   printf '  [FAIL] %s\n' "$1"; fail=$((fail+1)); }
exp(){  printf '  expect: %s\n' "$1"; }          # print expected range BEFORE the check
sec(){  printf '\n===== %s =====\n' "$1"; }

echo "############################################################"
echo "# BC-250 parity check â€” $(hostname) â€” $(date --iso-8601=seconds)"
echo "# model=$MODEL   load_test=$([[ $DO_LOAD -eq 1 ]] && echo yes || echo no)"
echo "############################################################"

# ---------------------------------------------------------------------------
sec "1. GPU MEMORY CEILING  (the 4x-slowdown bug â€” check this first)"
exp "ttm.pages_limit = 4194304.  A substantially lower limit can make the model spill to CPU and fall to ~22 tok/s."
tl=$(cat /sys/module/ttm/parameters/pages_limit 2>/dev/null || echo 0)
if [[ "$tl" == "4194304" ]]; then ok "ttm.pages_limit=$tl"
elif [[ "$tl" =~ ^[0-9]+$ && "$tl" -lt 3000000 ]]; then fl "ttm.pages_limit=$tl  <- add 'ttm.pages_limit=4194304' to the kernel cmdline + reboot"
else wn "ttm.pages_limit=$tl (non-standard)"; fi
pool=$(cat /sys/module/ttm/parameters/page_pool_size 2>/dev/null || echo '?')
gttsize=$(cat /sys/module/amdgpu/parameters/gttsize 2>/dev/null || echo '?')
[[ "$pool" == "0" ]] && ok "ttm.page_pool_size=$pool (kernel-managed)" || wn "ttm.page_pool_size=$pool (expected kernel default 0)"
[[ "$gttsize" == "-1" ]] && ok "amdgpu.gttsize=$gttsize (automatic)" || wn "amdgpu.gttsize=$gttsize (expected kernel default -1)"
if have dmesg; then
  gtt=$(dmesg 2>/dev/null | grep -m1 'GTT memory ready' | grep -oE '[0-9]+M')
  [[ -n "$gtt" ]] && echo "  GTT reported=$gtt" || wn "GTT line not in dmesg buffer (rotated?)"
fi
echo "  cmdline: $(cat /proc/cmdline)"

# ---------------------------------------------------------------------------
sec "2. OLLAMA GPU RESIDENCY  ($MODEL)"
exp "PROCESSOR = '100% GPU'.  Anything with 'CPU' (e.g. 62%/38%) = memory spill = the bug above."
if [[ $DO_LOAD -eq 1 ]]; then
  curl -s "$OLLAMA/api/generate" -d "{\"model\":\"$MODEL\",\"prompt\":\"hi\",\"stream\":false,\"options\":{\"num_predict\":1}}" >/dev/null 2>&1
fi
ps=$(ollama ps 2>/dev/null | tail -n +2)
if [[ -z "$ps" ]]; then wn "no model resident (start it, or run without --no-load)"
elif grep -q '100% GPU' <<<"$ps"; then ok "$(echo "$ps" | sed 's/  */ /g')"
else fl "NOT 100% GPU: $(echo "$ps" | sed 's/  */ /g')  <- lower num_ctx or fix ttm (check 1)"; fi

# ---------------------------------------------------------------------------
sec "3. CLOCK DOMAINS  (memory bandwidth = the decode ceiling)"
exp "mclk=450  fclk=450  socclk=1254  (IDENTICAL on both ref boards; mclk is NOT tunable and sets decode speed)"
m=$(active $cardg/pp_dpm_mclk); f=$(active $cardg/pp_dpm_fclk); s=$(active $cardg/pp_dpm_socclk)
[[ "$m" == *450Mhz* ]] && ok "mclk=$m" || wn "mclk=$m  <- differs from ref 450Mhz; would directly change decode tok/s"
[[ "$f" == *450Mhz* ]] && ok "fclk=$f" || wn "fclk=$f  (ref 450Mhz)"
[[ "$s" == *1254Mhz* ]] && ok "socclk=$s" || wn "socclk=$s  (ref 1254Mhz)"

# ---------------------------------------------------------------------------
sec "4. CU COUNT"
exp "40 CUs active.  (both ref boards 40/40, no dead-WGP mask)"
if have bc250-cu-live-manager; then
  cu_status=$(bc250-cu-live-manager status 2>&1 || true)
  printf '%s\n' "$cu_status" | sed 's/^/  /'
  if grep -qE 'CUs active[[:space:]]*& routed[[:space:]]*:[[:space:]]*40/40' <<<"$cu_status"; then
    ok "live manager reports 40/40 active and routed"
  elif grep -qE 'CUs active[[:space:]]*& routed[[:space:]]*:' <<<"$cu_status"; then
    wn "live manager reports a partial CU routing table"
  else
    wn "live-manager status could not be parsed"
  fi
else
  wn "bc250-cu-live-manager is not installed"
fi
if have dmesg && dmesg 2>/dev/null | grep -qi 'amdgpu.*disable_cu'; then
  wn "amdgpu.disable_cu present â€” some CUs masked (fine only if this board has dead WGPs)"
else ok "no disable_cu kernel mask (matches ref)"; fi
echo "  note: run 'bc250-cu-live-manager' without arguments for the interactive table"

# ---------------------------------------------------------------------------
sec "5. FIRMWARE / VBIOS / SMU"
exp "VBIOS 113-AMDRBN-003 | SMU fw 88.6.0 (0x00580600).  A mismatch here can change power/clock behavior."
if have dmesg; then
  vb=$(dmesg 2>/dev/null | grep -m1 'ATOM BIOS' | grep -oE '113-[A-Z0-9-]+')
  sm=$(dmesg 2>/dev/null | grep -m1 'smu fw version' | grep -oE '\(88\.6\.0\)')
  [[ "$vb" == "113-AMDRBN-003" ]] && ok "VBIOS=$vb" || wn "VBIOS=${vb:-?}  (ref 113-AMDRBN-003)"
  [[ -n "$sm" ]] && ok "SMU fw=88.6.0" || wn "SMU fw differs from ref 88.6.0"
else wn "dmesg unavailable (need sudo)"; fi

# ---------------------------------------------------------------------------
sec "6. VERSIONS  (compare these when investigating a performance delta)"
exp "Mesa 26.1.4 | governor 0.4.11.  The installed Ollama version is reported without enforcing an old pin."
k=$(uname -r); echo "  kernel: $k"
ov=$(ollama --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
[[ -n "$ov" ]] && ok "ollama=$ov" || wn "Ollama version unavailable"
if have vulkaninfo; then
  mv=$(vulkaninfo --summary 2>/dev/null | grep -m1 -i driverInfo | grep -oE 'Mesa [0-9.]+')
  [[ "$mv" == "Mesa 26.1.4" ]] && ok "$mv" || wn "${mv:-Mesa ?}  (ref Mesa 26.1.4)"
fi
gv=$(cyan-skillfish-governor-smu --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
[[ "$gv" == "0.4.11" ]] && ok "governor=$gv" || wn "governor=${gv:-?}  (ref 0.4.11)"

# ---------------------------------------------------------------------------
sec "7. OLLAMA SERVICE ENV"
exp "OLLAMA_NUM_PARALLEL=1, OLLAMA_MAX_LOADED_MODELS=1, OLLAMA_FLASH_ATTENTION=1, OLLAMA_KV_CACHE_TYPE=q8_0"
env=$(systemctl cat ollama 2>/dev/null | grep -iE 'Environment')
chk_env(){ grep -q "$1" <<<"$env" && ok "$1" || fl "$1 MISSING <- KV cache doubles / concurrency multiplies memory without it"; }
if [[ -n "$env" ]]; then
  chk_env 'OLLAMA_NUM_PARALLEL=1'
  chk_env 'OLLAMA_MAX_LOADED_MODELS=1'
  chk_env 'OLLAMA_FLASH_ATTENTION=1'
  chk_env 'OLLAMA_KV_CACHE_TYPE=q8_0'
else wn "could not read ollama unit env (need sudo)"; fi

# ---------------------------------------------------------------------------
sec "8. GOVERNOR RANGE"
exp "max=2000 (or your chosen cap). min/throttle differ harmlessly between ref boards (350vs500, 90/78 vs 85/75)."
gmax=$(grep -E '^\s*max\s*=' /etc/cyan-skillfish-governor-smu/config.toml 2>/dev/null | grep -oE '[0-9]+' | head -1)
if [[ -n "$gmax" ]]; then
  if [[ "$gmax" -ge 1850 && "$gmax" -le 2000 ]]; then ok "max=$gmax MHz"
  elif [[ "$gmax" -gt 2000 ]]; then wn "max=$gmax MHz  <- >2000 buys <2% decode for real extra voltage/heat; not worth it on this hardware"
  else wn "max=$gmax MHz (below ref 2000)"; fi
else wn "governor config not found"; fi

# ---------------------------------------------------------------------------
if [[ $DO_LOAD -eq 1 ]]; then
sec "9. SUSTAINED LOAD  (clock stability + the power/leakage tell)"
exp "sclk should PIN 2000MHz the whole run (no throttling). Power: ref A ~120avg/134peak, ref B ~135avg/144peak."
exp "If your board pins 2000 but draws MORE watts than ref A -> ok bin -> expect lower tok/s. That's silicon, not fixable."
  log="/tmp/bc250-load-$(hostname).log"; : > "$log"
  curl -s "$OLLAMA/api/generate" -d "{\"model\":\"$MODEL\",\"prompt\":\"Write a detailed 2000-word technical essay about GPU memory bandwidth and LLM inference.\",\"stream\":false,\"options\":{\"num_predict\":$NUM_PREDICT}}" >/dev/null 2>&1 &
  gp=$!
  for ((i=1;i<=LOAD_SECONDS;i++)); do
    sc=$(active $cardg/pp_dpm_sclk)
    tp=$(sensors 2>/dev/null | grep -m1 -E 'edge:|Tctl:' | grep -oE '[0-9]+\.[0-9]+' | head -1)
    pr=$(cat $hwmg/power1_average 2>/dev/null | head -1)
    pw=$(awk "BEGIN{printf \"%.0f\", ${pr:-0}/1000000}")
    printf '%s sclk=%s temp=%s power=%s\n' "$(date +%s)" "${sc:-?}" "${tp:-?}" "$pw" >> "$log"
    sleep 1
  done
  wait $gp 2>/dev/null

  # verdict: did it hold top clock while busy? (busy rows = power>60W).
  # field 4 is literal "power=NNN"; strip prefix to a number first.
  PW='{v=$4; sub(/power=/,"",v); v=v+0}'
  top=$(grep 'power=' "$log" | awk "$PW"' v>60' | grep -c '2000Mhz')
  busy=$(grep 'power=' "$log" | awk "$PW"' v>60' | wc -l)
  echo "  sclk distribution while busy:"
  grep 'power=' "$log" | awk "$PW"' v>60{print $2}' | sort | uniq -c | sort -rn | sed 's/^/    /'
  if [[ "$busy" -gt 0 && "$top" -eq "$busy" ]]; then ok "held 2000MHz for all $busy busy samples (no throttle)"
  elif [[ "$busy" -gt 0 ]]; then wn "dropped below 2000MHz in $((busy-top))/$busy busy samples (thermal/power limit â€” but note: sub-2000 barely affects DECODE)"
  else wn "no busy samples captured (model too fast / didn't load?)"; fi

  # power verdict vs the two reference bins
  read -r pavg ppk < <(grep 'power=' "$log" | awk "$PW"' v>60{s+=v;n++; if(v>x)x=v} END{if(n)printf "%.0f %.0f", s/n, x; else print "0 0"}')
  echo "  power under load: avg=${pavg}W peak=${ppk}W"
  if   [[ "$ppk" -eq 0 ]]; then wn "no load power captured"
  elif [[ "$ppk" -le 136 ]]; then ok "peak ${ppk}W ~ ref A (good bin) -> expect ~84 tok/s class"
  elif [[ "$ppk" -le 150 ]]; then wn "peak ${ppk}W ~ ref B (ok bin) -> expect ~73 tok/s class; this is silicon, not config"
  else wn "peak ${ppk}W ABOVE both refs -> very leaky / high governor voltage; check governor max"; fi

  tmax=$(grep 'temp=' "$log" | grep -oE 'temp=[0-9.]+' | cut -d= -f2 | sort -n | tail -1)
  echo "  temp peak=${tmax}C  (NOTE: ref A read 'edge', ref B read 'Tctl' â€” labels differ ~5-8C, normalize before comparing)"
else
sec "9. SUSTAINED LOAD â€” skipped (--no-load)"
fi

# ---------------------------------------------------------------------------
sec "SCORE"
printf '  OK=%d  WARN=%d  FAIL=%d\n' "$pass" "$warn" "$fail"
if [[ $fail -gt 0 ]]; then
  echo "  -> FAILs are real misconfig (usually the ttm memory bug in check 1). Fix those first."
elif [[ $warn -gt 0 ]]; then
  echo "  -> No hard failures. WARNs are deltas vs the reference boards â€” if tok/s is low"
  echo "     despite mclk=450 + 100% GPU + 2000MHz held, it's the silicon bin (power line), not a bug."
else
  echo "  -> Matches the reference stack. Any residual tok/s gap = silicon leakage bin."
fi

