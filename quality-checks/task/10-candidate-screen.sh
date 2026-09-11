#!/usr/bin/env bash
# Compare one packaged experimental task candidate against the current Gemma 3
# 1B task baseline. This is candidate evidence only; it never changes defaults.
set -Eeuo pipefail
umask 077

CANDIDATE="${1:-}"
ROUNDS="${2:-${BC250_SCREEN_ROUNDS:-3}}"
BASELINE='task-gemma3-1b-unsloth-ud-q4-k-xl'
SHARE='/usr/share/bc250-llm-server'
MAIN_URL='http://127.0.0.1:11434'
TASK_URL='http://127.0.0.1:11435'
MAIN_HOST='127.0.0.1:11434'
TASK_HOST='127.0.0.1:11435'
QUALITY_FAILED=0
TASK_CANDIDATE_CREATED=0

[[ -n "$CANDIDATE" ]] || {
    echo "usage: $0 EXPERIMENT-MODEL [ROUNDS]" >&2
    exit 2
}
[[ "$CANDIDATE" == exp-* ]] || {
    echo 'ERROR: candidate must be a packaged exp-* model.' >&2
    exit 2
}
[[ "$ROUNDS" =~ ^[1-9][0-9]*$ ]] || {
    echo 'ERROR: rounds must be a positive integer.' >&2
    exit 2
}

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="${BC250_QUALITY_ROOT:-$HOME/bc250-quality}"
SAFE_NAME="${CANDIDATE//[^a-zA-Z0-9._-]/_}"
OUT="$ROOT/task-screen-${SAFE_NAME}-${STAMP}"
START_ISO="$(date --iso-8601=seconds)"
mkdir -p "$OUT"/{setup,runs,post}
printf '%s\n' "$START_ISO" > "$OUT/setup/start-time.txt"
cp "$0" "$OUT/task-candidate-screen.sh" 2>/dev/null || true

need() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'ERROR: required command unavailable: %s\n' "$1" >&2
        exit 1
    }
}
for cmd in bc250-benchmark bc250-model curl jq ollama python3 rpm systemctl journalctl tar sha256sum; do
    need "$cmd"
done
OLLAMA_BIN="$(command -v ollama)"
sudo -v

unload_host() {
    local url="$1" host="$2" model count i
    while IFS= read -r model; do
        [[ -n "$model" ]] || continue
        OLLAMA_HOST="$host" ollama stop "$model" >/dev/null 2>&1 || true
    done < <(curl -fsS "$url/api/ps" | jq -r '.models[]? | (.name // .model // empty)')
    for i in $(seq 1 30); do
        count="$(curl -fsS "$url/api/ps" | jq '.models | length')"
        [[ "$count" == 0 ]] && return 0
        sleep 1
    done
    printf 'ERROR: models remained resident on %s\n' "$url" >&2
    return 1
}

model_present() {
    local url="$1" model="$2"
    curl -fsS "$url/api/tags" | jq -e --arg model "$model" '
      .models | any(((.name // .model // "") | sub(":latest$"; "")) == $model)
    ' >/dev/null
}

register_candidate_on_task() {
    local modelfile="$SHARE/model-management/modelfiles/${CANDIDATE}.Modelfile"
    if model_present "$TASK_URL" "$CANDIDATE"; then
        printf 'ERROR: candidate is already registered on task Ollama; refusing to reuse unknown task-lane state: %s\n' \
            "$CANDIDATE" >&2
        return 1
    fi
    [[ -r "$modelfile" ]] || {
        printf 'ERROR: packaged candidate Modelfile unavailable: %s\n' "$modelfile" >&2
        return 1
    }
    # bc250-model installs experimental GGUFs in the package experiment store and
    # registers them on main Ollama. Mirror only the Ollama registration into the
    # task service so quality/resource evidence uses the same q8 KV-cache, 4096
    # context and keep-alive policy as the deployment target.
    sudo -u ollama env HOME=/var/lib/ollama OLLAMA_HOST="$TASK_HOST" \
        "$OLLAMA_BIN" create "$CANDIDATE" -f "$modelfile"
    TASK_CANDIDATE_CREATED=1
    model_present "$TASK_URL" "$CANDIDATE" || {
        echo 'ERROR: candidate task-lane registration did not appear.' >&2
        return 1
    }
}

remove_temporary_task_candidate() {
    [[ "$TASK_CANDIDATE_CREATED" == 1 ]] || return 0
    unload_host "$TASK_URL" "$TASK_HOST" || return 1
    sudo -u ollama env HOME=/var/lib/ollama OLLAMA_HOST="$TASK_HOST" \
        "$OLLAMA_BIN" rm "$CANDIDATE" >/dev/null
    TASK_CANDIDATE_CREATED=0
}

capture_state() {
    local dest="$1"
    mkdir -p "$dest"
    date --iso-8601=seconds > "$dest/time.txt"
    rpm -q --qf '%{NAME} %{VERSION}-%{RELEASE} %{ARCH}\n' bc250-llm-server > "$dest/package.txt"
    systemctl is-active ollama.service ollama-task.service ollama-embedding.service open-webui.service \
        > "$dest/services-active.txt" 2>&1 || true
    cat /proc/meminfo > "$dest/meminfo.txt"
    cat /proc/swaps > "$dest/swaps.txt"
    curl -fsS "$MAIN_URL/api/ps" | jq . > "$dest/main-ps.json"
    curl -fsS "$TASK_URL/api/ps" | jq . > "$dest/task-ps.json"
}

run_one() {
    local round="$1" label="$2" model="$3" url="$4" host="$5"
    local dir="$OUT/runs/${round}-${label}" rc
    unload_host "$url" "$host"
    printf '\n===== round %s / %s / %s =====\n' "$round" "$label" "$model"
    set +e
    bc250-benchmark task "$model" --ollama-url "$url" --output-dir "$dir" \
        2>&1 | tee "$OUT/runs/${round}-${label}.console.txt"
    rc="${PIPESTATUS[0]}"
    set -e
    printf '%s\n' "$rc" > "$OUT/runs/${round}-${label}.rc"
    if [[ "$rc" == 3 ]]; then
        QUALITY_FAILED=1
    fi
    [[ "$rc" == 0 || "$rc" == 3 ]] || {
        printf 'ERROR: infrastructure failure: %s rc=%s\n' "$label" "$rc" >&2
        return "$rc"
    }
    unload_host "$url" "$host"
}

write_aggregate() {
    python3 - "$OUT" <<'PY' > "$OUT/aggregate.txt"
import json, pathlib, sys
from collections import Counter, defaultdict
root = pathlib.Path(sys.argv[1])
rows=[]
for p in sorted((root/'runs').glob('*/results.jsonl')):
    round_id,label=p.parent.name.split('-',1)
    for line in p.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        r=json.loads(line)
        if r.get('result_type')!='qualification': continue
        r=dict(r); r['screen_label']=label; r['screen_round']=round_id; rows.append(r)
print('label\tpass/total\tfailure-kinds\toutput-budget-diags\tmean-wall-s\tmax-wall-s\tmin-mem-available-mib\tmax-swap-used-mib')
for label in sorted({r['screen_label'] for r in rows}):
    xs=[r for r in rows if r['screen_label']==label]
    p=sum(r.get('outcome')=='pass' for r in xs)
    failures=Counter(x for r in xs for x in r.get('failure_kinds',[]))
    budget=sum('output-budget' in r.get('diagnostics',[]) for r in xs)
    walls=[r.get('metrics',{}).get('wall_s') for r in xs]
    walls=[float(x) for x in walls if x is not None]
    mem=[r.get('telemetry',{}).get('mem_available_min_mib') for r in xs]
    mem=[float(x) for x in mem if x is not None]
    swap=[r.get('telemetry',{}).get('swap_used_max_mib') for r in xs]
    swap=[float(x) for x in swap if x is not None]
    print(f"{label}\t{p}/{len(xs)}\t{dict(failures)}\t{budget}\t{sum(walls)/len(walls) if walls else 'NA'}\t{max(walls) if walls else 'NA'}\t{min(mem) if mem else 'NA'}\t{max(swap) if swap else 'NA'}")
print('\nPER ROUND')
rounds=defaultdict(list)
for r in rows: rounds[(r['screen_label'],r['screen_round'])].append(r)
for (label,round_id),xs in sorted(rounds.items(), key=lambda item:(item[0][0],int(item[0][1]))):
    p=sum(r.get('outcome')=='pass' for r in xs)
    print(f"{label}\tround={round_id}\t{p}/{len(xs)}")
print('\nPER CASE')
by=defaultdict(list)
for r in rows: by[(r['screen_label'],r['case_id'])].append(r)
for (label,case),xs in sorted(by.items()):
    p=sum(r.get('outcome')=='pass' for r in xs)
    failures=sorted({x for r in xs for x in r.get('failure_kinds',[])})
    print(f"{label}\t{case}\t{p}/{len(xs)}\t{','.join(failures) or '-'}")
print('\nFAILED RESPONSES')
for r in rows:
    if r.get('outcome')=='pass': continue
    failures=','.join(r.get('failure_kinds',[])) or '-'
    diagnostics=','.join(r.get('diagnostics',[])) or '-'
    print(f"\nlabel={r['screen_label']} round={r['screen_round']} case={r['case_id']} fail={failures} diagnostics={diagnostics}")
    print('response:')
    print(r.get('response',''))
    thinking=r.get('thinking','')
    if thinking:
        print('thinking:')
        print(thinking)
PY
}

finalize() {
    local rc=$? cleanup_rc=0
    trap - EXIT
    set +e
    unload_host "$MAIN_URL" "$MAIN_HOST" >/dev/null 2>&1 || true
    unload_host "$TASK_URL" "$TASK_HOST" >/dev/null 2>&1 || true
    if ! remove_temporary_task_candidate; then
        cleanup_rc=1
        printf '%s\n' 'ERROR: temporary task candidate registration cleanup failed.' \
            > "$OUT/post/restoration-status.txt"
        rc=23
    elif [[ "$TASK_CANDIDATE_CREATED" == 0 ]]; then
        printf '%s\n' 'Temporary task candidate registration cleaned up or none was created.' \
            > "$OUT/post/restoration-status.txt"
    fi
    capture_state "$OUT/post/state-after" || true
    journalctl -b --since "$START_ISO" --no-pager -u ollama.service -u ollama-task.service \
        > "$OUT/post/service-journal.txt" 2>&1 || true
    journalctl -k -b --since "$START_ISO" --no-pager > "$OUT/post/kernel-journal.txt" 2>&1 || true
    grep -Ein 'out of memory|oom-kill|oom_reaper|killed process|device lost|gpu reset|amdgpu.*(reset|timeout|fault)|ring.*(timeout|reset|fault|error)' \
        "$OUT/post/service-journal.txt" "$OUT/post/kernel-journal.txt" \
        > "$OUT/post/serious-warnings.txt" 2>/dev/null || true
    write_aggregate || true
    printf '%s\n' "$rc" > "$OUT/post/script-exit-rc.txt"
    date --iso-8601=seconds > "$OUT/post/end-time.txt"
    local parent name tarball
    parent="$(dirname "$OUT")"; name="$(basename "$OUT")"; tarball="$HOME/${name}.tar.gz"
    tar -C "$parent" -czf "$tarball" "$name"
    sha256sum "$tarball" > "$tarball.sha256"
    printf '\n=== task candidate summary ===\n'
    cat "$OUT/aggregate.txt" 2>/dev/null || true
    printf 'Evidence: %s\nTarball: %s\n' "$OUT" "$tarball"
    cat "$tarball.sha256"
    [[ "$cleanup_rc" == 0 ]] || printf '\nCRITICAL: task-lane cleanup FAILED.\n' >&2
    exit "$rc"
}
trap finalize EXIT

systemctl is-active --quiet ollama.service || { echo 'ERROR: ollama.service inactive.' >&2; exit 1; }
systemctl is-active --quiet ollama-task.service || { echo 'ERROR: ollama-task.service inactive.' >&2; exit 1; }
capture_state "$OUT/setup/state-before"
sha256sum /usr/libexec/bc250-llm-server/category-benchmark.py \
    /usr/share/bc250-llm-server/benchmark/task-cases.json > "$OUT/setup/benchmark-contract.sha256"
cp /usr/share/bc250-llm-server/benchmark/task-cases.json "$OUT/setup/task-cases.json"

sudo bc250-model install experiments "$CANDIDATE" 2>&1 | tee "$OUT/setup/candidate-install.txt"
model_present "$MAIN_URL" "$CANDIDATE" || { echo 'ERROR: candidate is not registered on main Ollama.' >&2; exit 1; }
model_present "$TASK_URL" "$BASELINE" || { echo 'ERROR: packaged task baseline is not registered.' >&2; exit 1; }
register_candidate_on_task
systemctl show -p Environment ollama-task.service > "$OUT/setup/task-service-environment.txt"
jq -n --arg model "$BASELINE" '{model:$model}' \
    | curl -fsS -H 'Content-Type: application/json' --data-binary @- "$TASK_URL/api/show" \
    | jq . > "$OUT/setup/baseline-task-show.json"
jq -n --arg model "$CANDIDATE" '{model:$model}' \
    | curl -fsS -H 'Content-Type: application/json' --data-binary @- "$TASK_URL/api/show" \
    | jq . > "$OUT/setup/candidate-task-show.json"

for n in $(seq 1 "$ROUNDS"); do
    run_one "$n" baseline "$BASELINE" "$TASK_URL" "$TASK_HOST"
    # Never let a resident main model overlap the experimental task candidate.
    unload_host "$MAIN_URL" "$MAIN_HOST"
    run_one "$n" candidate "$CANDIDATE" "$TASK_URL" "$TASK_HOST"
done
write_aggregate
[[ "$QUALITY_FAILED" == 0 ]] || exit 3
