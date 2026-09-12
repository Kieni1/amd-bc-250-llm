#!/usr/bin/env bash
# Direct translation screen for one packaged experimental model. This uses the
# installed benchmark's explicit source/target direction and does not mutate OWUI.
set -Eeuo pipefail
umask 077

CANDIDATE="${1:-}"
ROUNDS="${2:-${BC250_SCREEN_ROUNDS:-3}}"
ALLOW_PRODUCTION_REFERENCE="${BC250_ALLOW_PRODUCTION_REFERENCE:-0}"
MAIN_URL='http://127.0.0.1:11434'
MAIN_HOST='127.0.0.1:11434'

[[ -n "$CANDIDATE" ]] || { echo "usage: $0 EXPERIMENT-MODEL [ROUNDS]" >&2; exit 2; }
if [[ "$CANDIDATE" == exp-* ]]; then
    INSTALL_EXPERIMENT=1
elif [[ "$ALLOW_PRODUCTION_REFERENCE" == 1 && "$CANDIDATE" == prod-lfm25-8b-a1b-liquidai-q6-k ]]; then
    INSTALL_EXPERIMENT=0
else
    echo 'ERROR: model must be a packaged exp-* candidate (or the explicit production LFM reference wrapper).' >&2
    exit 2
fi
[[ "$ROUNDS" =~ ^[1-9][0-9]*$ ]] || { echo 'ERROR: rounds must be a positive integer.' >&2; exit 2; }

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="${BC250_QUALITY_ROOT:-$HOME/bc250-quality}"
SAFE_NAME="${CANDIDATE//[^a-zA-Z0-9._-]/_}"
OUT="$ROOT/translation-direct-${SAFE_NAME}-${STAMP}"
START_ISO="$(date --iso-8601=seconds)"
QUALITY_FAIL=0
SERIOUS_WARNING_COUNT=0
mkdir -p "$OUT"/{setup,runs,post}
printf '%s\n' "$START_ISO" > "$OUT/setup/start-time.txt"
cp "$0" "$OUT/translation-direct-candidate-screen.sh" 2>/dev/null || true

need() {
    command -v "$1" >/dev/null 2>&1 || { printf 'ERROR: required command unavailable: %s\n' "$1" >&2; exit 1; }
}
for cmd in bc250-benchmark bc250-model curl jq ollama python3 rpm systemctl journalctl tar sha256sum; do need "$cmd"; done
sudo -v

unload_main() {
    local model count i
    while IFS= read -r model; do
        [[ -n "$model" ]] || continue
        OLLAMA_HOST="$MAIN_HOST" ollama stop "$model" >/dev/null 2>&1 || true
    done < <(curl -fsS "$MAIN_URL/api/ps" | jq -r '.models[]? | (.name // .model // empty)')
    for i in $(seq 1 30); do
        count="$(curl -fsS "$MAIN_URL/api/ps" | jq '.models | length')"
        [[ "$count" == 0 ]] && return 0
        sleep 1
    done
    echo 'ERROR: main Ollama did not unload.' >&2
    return 1
}

model_present() {
    curl -fsS "$MAIN_URL/api/tags" | jq -e --arg model "$CANDIDATE" '
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
}

run_round() {
    local n="$1" dir="$OUT/runs/$1" rc
    unload_main
    printf '\n===== direct translation / %s / round %s =====\n' "$CANDIDATE" "$n"
    set +e
    bc250-benchmark translation "$CANDIDATE" --ollama-url "$MAIN_URL" --output-dir "$dir" \
        2>&1 | tee "$OUT/runs/${n}.console.txt"
    rc="${PIPESTATUS[0]}"
    set -e
    printf '%s\n' "$rc" > "$OUT/runs/${n}.rc"
    [[ "$rc" == 0 || "$rc" == 3 ]] || {
        printf 'ERROR: translation benchmark infrastructure failure rc=%s\n' "$rc" >&2
        return "$rc"
    }
    [[ "$rc" == 0 ]] || QUALITY_FAIL=1
    unload_main
}

capture_provenance() {
    ollama --version > "$OUT/setup/ollama-version.txt" 2>&1 || true
    curl -sS --connect-timeout 5 --max-time 30 -H 'Content-Type: application/json' \
        -d "$(jq -cn --arg model "$CANDIDATE" '{model:$model}')" "$MAIN_URL/api/show" \
        > "$OUT/setup/candidate-ollama-show.json" 2>&1 || true
    local category resolved sidecar
    category=experiments; [[ "$INSTALL_EXPERIMENT" == 0 ]] && category=production
    resolved="$(bc250-model resolve "$category" "$CANDIDATE" 2>/dev/null | cut -f1 || true)"
    if [[ -n "$resolved" ]]; then
        printf '%s\n' "$resolved" > "$OUT/setup/candidate-source-path.txt"
        sidecar="${resolved}.bc250.json"
        if [[ -r "$sidecar" ]]; then
            python3 - "$sidecar" <<'PY' > "$OUT/setup/candidate-source-identity.json"
import json,sys
v=json.load(open(sys.argv[1],encoding='utf-8'))
print(json.dumps({k:v.get(k) for k in ('schema','model_name','model_id','category','sha256','size')},indent=2,sort_keys=True))
PY
        fi
    fi
}

write_run_manifest() {
    local final_rc="$1" quality infra
    [[ "$QUALITY_FAIL" == 0 ]] && quality=pass || quality=quality-fail
    if [[ "$final_rc" == 0 || "$final_rc" == 3 ]]; then infra=pass; else infra=fail; fi
    jq -n --arg candidate "$CANDIDATE" --arg path direct --argjson rounds "$ROUNDS" \
        --arg quality "$quality" --arg infrastructure "$infra" --argjson final_rc "$final_rc" \
        --argjson serious_warning_count "$SERIOUS_WARNING_COUNT" \
        '{candidate:$candidate,path:$path,rounds:$rounds,quality_result:$quality,infrastructure_result:$infrastructure,final_rc:$final_rc,serious_warning_count:$serious_warning_count}' \
        > "$OUT/run-manifest.json"
}

write_aggregate() {
    python3 - "$OUT" <<'PY' > "$OUT/aggregate.txt"
import json, math, pathlib, statistics, sys
from collections import Counter, defaultdict
root=pathlib.Path(sys.argv[1]); rows=[]
for p in sorted((root/'runs').glob('*/results.jsonl')):
    round_name=p.parent.name
    for line in p.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        r=json.loads(line)
        if r.get('result_type')!='qualification': continue
        r=dict(r); r['_round']=round_name; rows.append(r)

def nums(xs, path):
    out=[]
    for r in xs:
        cur=r
        for key in path:
            cur=cur.get(key,{}) if isinstance(cur,dict) else None
        if cur is not None:
            try: out.append(float(cur))
            except (TypeError, ValueError): pass
    return out

def pct(xs, q):
    if not xs: return None
    ys=sorted(xs); idx=max(0, min(len(ys)-1, math.ceil(q*len(ys))-1)); return ys[idx]

def summary(label, xs):
    passed=sum(r.get('outcome')=='pass' for r in xs)
    failures=Counter(x for r in xs for x in r.get('failure_kinds',[]))
    diagnostics=Counter(x for r in xs for x in r.get('diagnostics',[]))
    mem=nums(xs,('telemetry','mem_available_min_mib'))
    swap=nums(xs,('telemetry','swap_used_max_mib'))
    temp=nums(xs,('telemetry','temp_max_c'))
    wall=nums(xs,('metrics','wall_s'))
    print(f"{label}: {passed}/{len(xs)}")
    print(f"  failures={dict(failures) or '-'} diagnostics={dict(diagnostics) or '-'}")
    print(f"  min_mem_available_mib={min(mem) if mem else 'NA'} max_swap_used_mib={max(swap) if swap else 'NA'} max_temp_c={max(temp) if temp else 'NA'}")
    print(f"  wall_mean_s={statistics.mean(wall):.3f}" if wall else "  wall_mean_s=NA", end='')
    print(f" wall_p95_s={pct(wall,0.95):.3f}" if wall else " wall_p95_s=NA")

summary('OVERALL', rows)
print('\nPER ROUND')
for rd in sorted({r['_round'] for r in rows}, key=lambda x:int(x) if x.isdigit() else 999999):
    summary(f'round {rd}', [r for r in rows if r['_round']==rd])
print('\nBY DIRECTION')
for src,tgt in (('de','fr'),('fr','de')):
    summary(f'{src.upper()}->{tgt.upper()}', [r for r in rows if r.get('source_language')==src and r.get('target_language')==tgt])
print('\nPER CASE')
by=defaultdict(list)
for r in rows: by[r['case_id']].append(r)
for case,xs in sorted(by.items()):
    p=sum(r.get('outcome')=='pass' for r in xs)
    fs=sorted({x for r in xs for x in r.get('failure_kinds',[])})
    ds=sorted({x for r in xs for x in r.get('diagnostics',[])})
    print(f"{case}\t{p}/{len(xs)}\tfail={','.join(fs) or '-'}\tdiag={','.join(ds) or '-'}")
print('\nFAILED RESPONSES')
for r in rows:
    if r.get('outcome')=='pass': continue
    print(f"\n[round={r['_round']} {r['case_id']}] fail={','.join(r.get('failure_kinds',[])) or '-'} diag={','.join(r.get('diagnostics',[])) or '-'}")
    print(r.get('response',''))
PY
}

finalize() {
    local rc=$?
    trap - EXIT
    set +e
    unload_main >/dev/null 2>&1 || true
    capture_state "$OUT/post/state-after" || true
    journalctl -b --since "$START_ISO" --no-pager -u ollama.service > "$OUT/post/service-journal.txt" 2>&1 || true
    journalctl -k -b --since "$START_ISO" --no-pager > "$OUT/post/kernel-journal.txt" 2>&1 || true
    grep -Ein 'out of memory|oom-kill|oom_reaper|killed process|device lost|gpu reset|amdgpu.*(reset|timeout|fault)|ring.*(timeout|reset|fault|error)' \
        "$OUT/post/service-journal.txt" "$OUT/post/kernel-journal.txt" > "$OUT/post/serious-warnings.txt" 2>/dev/null || true
    SERIOUS_WARNING_COUNT="$(wc -l < "$OUT/post/serious-warnings.txt" | tr -d ' ')"
    write_aggregate || true
    write_run_manifest "$rc"
    printf '%s\n' "$rc" > "$OUT/post/script-exit-rc.txt"
    date --iso-8601=seconds > "$OUT/post/end-time.txt"
    local parent name tarball
    parent="$(dirname "$OUT")"; name="$(basename "$OUT")"; tarball="$HOME/${name}.tar.gz"
    tar -C "$parent" -czf "$tarball" "$name"
    sha256sum "$tarball" > "$tarball.sha256"
    printf '\n=== direct translation candidate summary ===\n'
    cat "$OUT/aggregate.txt" 2>/dev/null || true
    printf 'Evidence: %s\nTarball: %s\n' "$OUT" "$tarball"
    cat "$tarball.sha256"
    exit "$rc"
}
trap finalize EXIT

systemctl is-active --quiet ollama.service || { echo 'ERROR: ollama.service inactive.' >&2; exit 1; }
capture_state "$OUT/setup/state-before"
sha256sum /usr/libexec/bc250-llm-server/category-benchmark.py \
    /usr/share/bc250-llm-server/benchmark/translation-office.json > "$OUT/setup/benchmark-contract.sha256"
cp /usr/share/bc250-llm-server/benchmark/translation-office.json "$OUT/setup/translation-office.json"
if [[ "$INSTALL_EXPERIMENT" == 1 ]]; then
    sudo bc250-model install experiments "$CANDIDATE" 2>&1 | tee "$OUT/setup/candidate-install.txt"
else
    printf 'production reference: using existing registered model %s\n' "$CANDIDATE" | tee "$OUT/setup/candidate-install.txt"
fi
model_present || { echo 'ERROR: candidate/reference model is not registered on main Ollama.' >&2; exit 1; }
capture_provenance
for n in $(seq 1 "$ROUNDS"); do run_round "$n"; done
write_aggregate
[[ "$QUALITY_FAIL" == 0 ]] || exit 3
