#!/usr/bin/env bash
# Compare one packaged experimental task candidate against the current Gemma 3
# 1B task baseline. This is candidate evidence only; it never changes defaults.
set -Eeuo pipefail
umask 077

CANDIDATE="${1:-}"
ROUNDS="${2:-${BC250_SCREEN_ROUNDS:-3}}"
BASELINE='task-gemma3-1b-unsloth-ud-q4-k-xl'
MAIN_URL='http://127.0.0.1:11434'
TASK_URL='http://127.0.0.1:11435'
MAIN_HOST='127.0.0.1:11434'
TASK_HOST='127.0.0.1:11435'

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
    label=p.parent.name.split('-',1)[1]
    for line in p.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        r=json.loads(line)
        if r.get('result_type')!='qualification': continue
        r=dict(r); r['screen_label']=label; rows.append(r)
print('label\tpass/total\tfailure-kinds\toutput-budget-diags\tmin-mem-available-mib\tmax-swap-used-mib')
for label in sorted({r['screen_label'] for r in rows}):
    xs=[r for r in rows if r['screen_label']==label]
    p=sum(r.get('outcome')=='pass' for r in xs)
    failures=Counter(x for r in xs for x in r.get('failure_kinds',[]))
    budget=sum('output-budget' in r.get('diagnostics',[]) for r in xs)
    mem=[r.get('telemetry',{}).get('mem_available_min_mib') for r in xs]
    mem=[float(x) for x in mem if x is not None]
    swap=[r.get('telemetry',{}).get('swap_used_max_mib') for r in xs]
    swap=[float(x) for x in swap if x is not None]
    print(f"{label}\t{p}/{len(xs)}\t{dict(failures)}\t{budget}\t{min(mem) if mem else 'NA'}\t{max(swap) if swap else 'NA'}")
print('\nPER CASE')
by=defaultdict(list)
for r in rows: by[(r['screen_label'],r['case_id'])].append(r)
for (label,case),xs in sorted(by.items()):
    p=sum(r.get('outcome')=='pass' for r in xs)
    failures=sorted({x for r in xs for x in r.get('failure_kinds',[])})
    print(f"{label}\t{case}\t{p}/{len(xs)}\t{','.join(failures) or '-'}")
PY
}

finalize() {
    local rc=$?
    trap - EXIT
    set +e
    unload_host "$MAIN_URL" "$MAIN_HOST" >/dev/null 2>&1 || true
    unload_host "$TASK_URL" "$TASK_HOST" >/dev/null 2>&1 || true
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

for n in $(seq 1 "$ROUNDS"); do
    run_one "$n" baseline "$BASELINE" "$TASK_URL" "$TASK_HOST"
    # Never let a resident main model overlap the experimental task candidate.
    unload_host "$MAIN_URL" "$MAIN_HOST"
    run_one "$n" candidate "$CANDIDATE" "$MAIN_URL" "$MAIN_HOST"
done
write_aggregate
