#!/usr/bin/env bash
# Tiny warm-main coexistence gate for a task candidate already registered on 11435.
# This is a safety gate, not a task-quality benchmark.

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf '%s\n' 'REFUSED: execute this script with bash; do not source it.' >&2
    return 0
fi

set -u
set -o pipefail
umask 077

: "${CANDIDATE_MODEL:?set CANDIDATE_MODEL to a model already registered on the task lane}"
MAIN_URL="${BC250_MAIN_URL:-http://127.0.0.1:11434}"
TASK_URL="${BC250_TASK_URL:-http://127.0.0.1:11435}"
MAIN_MODEL="${MAIN_MODEL:-prod-gpt-oss20b-ggml-org-mxfp4:latest}"
MIN_MEM_MIB="${MIN_MEM_MIB:-512}"
MAX_SWAP_GROWTH_MIB="${MAX_SWAP_GROWTH_MIB:-512}"
ROOT="${BC250_QUALITY_ROOT:-$HOME/bc250-quality}"
STAMP="$(date +%Y%m%d-%H%M%S)"
SAFE_NAME="${CANDIDATE_MODEL//[^a-zA-Z0-9._-]/_}"
OUT="$ROOT/task-survival-${SAFE_NAME}-${STAMP}"
TARBALL="$HOME/$(basename "$OUT").tar.gz"
STATUS_FILE="${TARBALL}.status.txt"
LOCK_FILE="${XDG_RUNTIME_DIR:-/tmp}/bc250-task-survival-${UID}.lock"
START_ISO="$(date --iso-8601=seconds)"
MON_PID=""
INFRA_RC=0
QUALITY_RC=0
TAR_RC=125
FINAL_RC=0
mkdir -p "$OUT"

model_ref() { case "$1" in *:*) printf '%s\n' "$1" ;; *) printf '%s:latest\n' "$1" ;; esac; }
model_available() {
    jq -n --arg model "$(model_ref "$2")" '{model:$model}' |
      curl -fsS --connect-timeout 5 --max-time 20 -H 'Content-Type: application/json' \
        --data-binary @- "$1/api/show" >/dev/null 2>&1
}
model_in_ps() {
    local url="$1" model
    model="$(model_ref "$2")"
    curl -fsS --connect-timeout 3 --max-time 10 "$url/api/ps" 2>/dev/null |
      jq -e --arg m "$model" '.models | any((.name // .model // "") == $m or (((.name // .model // "") | sub(":latest$"; "")) == ($m | sub(":latest$"; ""))))' >/dev/null 2>&1
}
wait_unload() {
    local i
    for i in $(seq 1 80); do model_in_ps "$TASK_URL" "$CANDIDATE_MODEL" || return 0; sleep 0.25; done
    return 1
}
warm_main() {
    model_in_ps "$MAIN_URL" "$MAIN_MODEL" && return 0
    jq -n --arg model "$(model_ref "$MAIN_MODEL")" '{model:$model,prompt:"Reply with exactly: warm",stream:false,keep_alive:"30m",options:{num_predict:16}}' > "$OUT/main-warm-request.json"
    curl -fsS --connect-timeout 10 --max-time 300 -H 'Content-Type: application/json' \
      --data-binary @"$OUT/main-warm-request.json" "$MAIN_URL/api/generate" > "$OUT/main-warm-response.json" || return 1
    model_in_ps "$MAIN_URL" "$MAIN_MODEL"
}
sample_resource() {
    awk '/^MemAvailable:/ {mem=$2/1024} /^SwapTotal:/ {st=$2} /^SwapFree:/ {sf=$2} END {printf "%.2f %.2f\n",mem,(st-sf)/1024}' /proc/meminfo
}
start_monitor() {
    (
      printf 'timestamp\tMemAvailable_MiB\tswap_used_MiB\n'
      while :; do read -r mem swap < <(sample_resource); printf '%s\t%s\t%s\n' "$(date +%s.%N)" "$mem" "$swap"; sleep 0.20; done
    ) > "$OUT/resource.tsv" &
    MON_PID=$!
}
stop_monitor() {
    if [[ -n "$MON_PID" ]]; then kill "$MON_PID" >/dev/null 2>&1 || true; wait "$MON_PID" >/dev/null 2>&1 || true; MON_PID=""; fi
}
cleanup() { local rc=$?; trap - EXIT INT TERM HUP; stop_monitor; exit "$rc"; }
trap cleanup EXIT
trap 'INFRA_RC=90; exit 90' INT TERM HUP
SERIOUS_RE='out of memory|oom-kill|oom_reaper|killed process|device lost|gpu reset|amdgpu.*(reset|timeout|fault)|ring.*(timeout|reset|fault|error)'

for cmd in curl jq python3 journalctl tar sha256sum systemctl awk grep flock; do command -v "$cmd" >/dev/null 2>&1 || INFRA_RC=10; done
if [[ "$INFRA_RC" -eq 0 ]]; then exec 9>"$LOCK_FILE"; flock -n 9 || INFRA_RC=11; fi
model_available "$TASK_URL" "$CANDIDATE_MODEL" || INFRA_RC=12
for svc in ollama.service ollama-task.service open-webui.service tika.service; do
    state="$(systemctl is-active "$svc" 2>/dev/null || true)"; printf '%s=%s\n' "$svc" "$state" >> "$OUT/services-before.txt"; [[ "$state" == active ]] || INFRA_RC=13
done

if [[ "$INFRA_RC" -eq 0 ]]; then warm_main || INFRA_RC=14; fi
if [[ "$INFRA_RC" -eq 0 ]]; then wait_unload || INFRA_RC=15; fi

if [[ "$INFRA_RC" -eq 0 ]]; then
    read -r PRE_MEM PRE_SWAP < <(sample_resource)
    printf 'pre_mem_available_mib=%s\npre_swap_used_mib=%s\n' "$PRE_MEM" "$PRE_SWAP" > "$OUT/pre-resource.txt"
    jq -n --arg model "$(model_ref "$CANDIDATE_MODEL")" '{model:$model,prompt:"Reply with exactly: OK",stream:false,keep_alive:0,options:{num_predict:8}}' > "$OUT/request.json"
    TRIAL_START="$(date --iso-8601=seconds)"
    start_monitor
    http="$(curl -sS --connect-timeout 10 --max-time 300 -H 'Content-Type: application/json' --data-binary @"$OUT/request.json" -o "$OUT/response.json" -w '%{http_code}' "$TASK_URL/api/generate")"
    CURL_RC=$?
    stop_monitor
    printf 'curl_rc=%s\nhttp_status=%s\n' "$CURL_RC" "${http:-000}" > "$OUT/http.txt"
    [[ "$CURL_RC" -eq 0 && "$http" =~ ^2[0-9][0-9]$ ]] || INFRA_RC=16
    if [[ "$INFRA_RC" -eq 0 ]]; then
        jq -e '.done == true and (.response | type == "string") and ((.response | length) > 0)' "$OUT/response.json" >/dev/null 2>&1 || INFRA_RC=16
    fi
fi

if [[ "$INFRA_RC" -eq 0 ]]; then
    wait_unload || INFRA_RC=17
    model_in_ps "$MAIN_URL" "$MAIN_MODEL" || INFRA_RC=18
    for svc in ollama.service ollama-task.service open-webui.service tika.service; do
        state="$(systemctl is-active "$svc" 2>/dev/null || true)"; printf '%s=%s\n' "$svc" "$state" >> "$OUT/services-after.txt"; [[ "$state" == active ]] || INFRA_RC=19
    done
fi

if [[ -f "$OUT/resource.tsv" ]]; then
python3 - "$OUT/resource.tsv" "$PRE_SWAP" "$MIN_MEM_MIB" "$MAX_SWAP_GROWTH_MIB" > "$OUT/resource-summary.txt" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1]); pre=float(sys.argv[2]); min_gate=float(sys.argv[3]); swap_gate=float(sys.argv[4])
mem=[]; swap=[]
for line in p.read_text().splitlines()[1:]:
    c=line.split('\t')
    if len(c)>=3:
        try: mem.append(float(c[1])); swap.append(float(c[2]))
        except ValueError: pass
minimum=min(mem) if mem else float('nan'); peak=max([pre,*swap]) if swap else pre; growth=max(0.0,peak-pre)
ok=minimum==minimum and minimum>=min_gate and growth<=swap_gate
print(f'min_mem_mib={minimum:.2f}')
print(f'pre_swap_used_mib={pre:.2f}')
print(f'peak_swap_used_mib={peak:.2f}')
print(f'swap_growth_mib={growth:.2f}')
print(f'resource_ok={str(ok).lower()}')
raise SystemExit(0 if ok else 3)
PY
    RESOURCE_RC=$?
    [[ "$RESOURCE_RC" -eq 0 ]] || QUALITY_RC=3
fi

journalctl -b --since "${TRIAL_START:-$START_ISO}" --no-pager -u ollama.service -u ollama-task.service -u open-webui.service -u tika.service > "$OUT/service-journal.txt" 2>&1 || INFRA_RC=20
journalctl -k -b --since "${TRIAL_START:-$START_ISO}" --no-pager > "$OUT/kernel-journal.txt" 2>&1 || INFRA_RC=20
grep -Ein "$SERIOUS_RE" "$OUT/service-journal.txt" "$OUT/kernel-journal.txt" > "$OUT/serious-warnings.txt" 2>/dev/null || true
[[ ! -s "$OUT/serious-warnings.txt" ]] || INFRA_RC=21

if [[ "$INFRA_RC" -ne 0 ]]; then FINAL_RC="$INFRA_RC"; elif [[ "$QUALITY_RC" -ne 0 ]]; then FINAL_RC=3; else FINAL_RC=0; fi
printf 'candidate_model=%s\ninfrastructure_rc=%s\nquality_rc=%s\npre_archive_rc=%s\n' "$CANDIDATE_MODEL" "$INFRA_RC" "$QUALITY_RC" "$FINAL_RC" > "$OUT/status-pre-archive.txt"
tar --owner=0 --group=0 --numeric-owner -C "$(dirname "$OUT")" -czf "$TARBALL" "$(basename "$OUT")"
TAR_RC=$?
if [[ "$INFRA_RC" -ne 0 ]]; then FINAL_RC="$INFRA_RC"; elif [[ "$TAR_RC" -ne 0 ]]; then FINAL_RC=22; elif [[ "$QUALITY_RC" -ne 0 ]]; then FINAL_RC=3; else FINAL_RC=0; fi
{
  printf 'candidate_model=%s\n' "$CANDIDATE_MODEL"
  printf 'infrastructure_rc=%s\nquality_rc=%s\ntar_rc=%s\nfinal_rc=%s\n' "$INFRA_RC" "$QUALITY_RC" "$TAR_RC" "$FINAL_RC"
  printf 'evidence=%s\n' "$TARBALL"
} | tee "$STATUS_FILE"
[[ "$TAR_RC" -eq 0 ]] && sha256sum "$TARBALL"
exit "$FINAL_RC"
