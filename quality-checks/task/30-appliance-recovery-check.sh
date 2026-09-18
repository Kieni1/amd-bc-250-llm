#!/usr/bin/env bash
# Post-task-experiment appliance recovery gate.
# Historical OOM/reset evidence is reported for context; only faults that occur during
# this recovery probe fail the check.

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf '%s\n' 'REFUSED: execute this script with bash; do not source it.' >&2
    return 0
fi
set -u
set -o pipefail
MAIN_URL="${BC250_MAIN_URL:-http://127.0.0.1:11434}"
TASK_URL="${BC250_TASK_URL:-http://127.0.0.1:11435}"
MAIN_MODEL="${MAIN_MODEL:-prod-gpt-oss20b-ggml-org-mxfp4:latest}"
HISTORY_SINCE="${SINCE:-10 minutes ago}"
WARM_MAIN="${WARM_MAIN:-1}"
CHECK_START="$(date --iso-8601=seconds)"
QUALITY_RC=0
INFRA_RC=0
SERIOUS_RE='out of memory|oom-kill|oom_reaper|killed process|device lost|gpu reset|amdgpu.*(reset|timeout|fault)|ring.*(timeout|reset|fault|error)'
model_ref(){ case "$1" in *:*) printf '%s\n' "$1" ;; *) printf '%s:latest\n' "$1" ;; esac; }
model_in_ps(){
    local url="$1" model
    model="$(model_ref "$2")"
    curl -fsS --connect-timeout 3 --max-time 10 "$url/api/ps" 2>/dev/null |
      jq -e --arg m "$model" '.models | any((.name // .model // "") == $m or (((.name // .model // "") | sub(":latest$"; "")) == ($m | sub(":latest$"; ""))))' >/dev/null 2>&1
}
[[ "$WARM_MAIN" =~ ^[01]$ ]] || { printf 'ERROR: WARM_MAIN must be 0 or 1.\n' >&2; exit 2; }
for c in curl jq systemctl journalctl awk grep date; do command -v "$c" >/dev/null 2>&1 || INFRA_RC=10; done

printf '\n=== recent serious kernel events before recovery probe (context only; since %s) ===\n' "$HISTORY_SINCE"
historical="$(journalctl -k -b --since "$HISTORY_SINCE" --until "$CHECK_START" --no-pager 2>/dev/null | grep -Ei "$SERIOUS_RE" || true)"
if [[ -n "$historical" ]]; then printf '%s\n' "$historical"; else printf 'none\n'; fi

if [[ "$INFRA_RC" -eq 0 && "$WARM_MAIN" == 1 ]] && ! model_in_ps "$MAIN_URL" "$MAIN_MODEL"; then
    printf '\n=== reload warm main ===\n'
    jq -n --arg model "$(model_ref "$MAIN_MODEL")" '{model:$model,prompt:"Reply with exactly: warm",stream:false,keep_alive:"30m",options:{num_predict:16}}' |
      curl -fsS --connect-timeout 10 --max-time 300 -H 'Content-Type: application/json' --data-binary @- "$MAIN_URL/api/generate" >/dev/null || INFRA_RC=11
fi

printf '\n=== service health ===\n'
for svc in ollama.service ollama-task.service open-webui.service tika.service; do
    state="$(systemctl is-active "$svc" 2>/dev/null || true)"; printf '%-28s %s\n' "$svc" "$state"; [[ "$state" == active ]] || QUALITY_RC=3
done
printf '\n=== residency ===\n'
model_in_ps "$MAIN_URL" "$MAIN_MODEL" || { printf 'main_model_resident=false\n'; QUALITY_RC=3; }
model_in_ps "$MAIN_URL" "$MAIN_MODEL" && printf 'main_model_resident=true\n'
task_count="$(curl -fsS --connect-timeout 3 --max-time 10 "$TASK_URL/api/ps" 2>/dev/null | jq '.models | length' 2>/dev/null)" || { task_count=-1; INFRA_RC=12; }
printf 'task_resident_count=%s\n' "$task_count"
[[ "$task_count" == 0 ]] || QUALITY_RC=3
printf '\n=== memory ===\n'
awk '/^MemAvailable:/ {printf "MemAvailable_MiB=%.2f\n",$2/1024} /^SwapTotal:/ {st=$2} /^SwapFree:/ {sf=$2} END {printf "swap_used_MiB=%.2f\n",(st-sf)/1024}' /proc/meminfo

# Give faults caused by the reload/health probe a moment to reach the journal.
sleep 1
printf '\n=== new serious kernel events during recovery probe ===\n'
new_warns="$(journalctl -k -b --since "$CHECK_START" --no-pager 2>/dev/null | grep -Ei "$SERIOUS_RE" || true)"
if [[ -n "$new_warns" ]]; then printf '%s\n' "$new_warns"; QUALITY_RC=3; else printf 'none\n'; fi
if [[ "$INFRA_RC" -ne 0 ]]; then FINAL_RC="$INFRA_RC"; elif [[ "$QUALITY_RC" -ne 0 ]]; then FINAL_RC=3; else FINAL_RC=0; fi
printf '\nRECOVERY_RC=%s\n' "$FINAL_RC"
exit "$FINAL_RC"
