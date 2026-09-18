#!/usr/bin/env bash
# Direct translation screen for one packaged experiment or explicitly enabled
# production reference. Uses the installed benchmark contract and does not mutate OWUI.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf '%s\n' 'REFUSED: execute this script with bash; do not source it.' >&2
    return 0
fi

set -Eeuo pipefail
umask 077

CANDIDATE="${1:-}"
ROUNDS="${2:-${BC250_SCREEN_ROUNDS:-1}}"
ALLOW_PRODUCTION_REFERENCE="${BC250_ALLOW_PRODUCTION_REFERENCE:-0}"
THINK_POLICY="${BC250_TRANSLATION_THINK:-auto}"
RECOVERY_MEM_MIB="${BC250_TRANSLATION_RECOVERY_MEM_MIB:-8192}"
LOCK_FILE="${XDG_RUNTIME_DIR:-/tmp}/bc250-translation-direct-${UID}.lock"
MAIN_URL='http://127.0.0.1:11434'
MAIN_HOST='127.0.0.1:11434'

[[ -n "$CANDIDATE" ]] || { echo "usage: $0 EXPERIMENT-MODEL [ROUNDS]" >&2; exit 2; }
if [[ "$CANDIDATE" == exp-* ]]; then
    INSTALL_EXPERIMENT=1
elif [[ "$ALLOW_PRODUCTION_REFERENCE" == 1 && "$CANDIDATE" == prod-* ]]; then
    INSTALL_EXPERIMENT=0
else
    echo 'ERROR: model must be a packaged exp-* candidate (or an explicitly enabled packaged prod-* reference).' >&2
    exit 2
fi
[[ "$ROUNDS" =~ ^[1-9][0-9]*$ ]] || { echo 'ERROR: rounds must be a positive integer.' >&2; exit 2; }
[[ "$THINK_POLICY" =~ ^(auto|true|false)$ ]] || { echo 'ERROR: BC250_TRANSLATION_THINK must be auto, true, or false.' >&2; exit 2; }
[[ "$RECOVERY_MEM_MIB" =~ ^[0-9]+$ ]] || { echo 'ERROR: BC250_TRANSLATION_RECOVERY_MEM_MIB must be an integer MiB value.' >&2; exit 2; }

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="${BC250_QUALITY_ROOT:-$HOME/bc250-quality}"
SAFE_NAME="${CANDIDATE//[^a-zA-Z0-9._-]/_}"
OUT="$ROOT/translation-direct-${SAFE_NAME}-${STAMP}"
START_ISO="$(date --iso-8601=seconds)"
QUALITY_FAIL=0
SERIOUS_WARNING_COUNT=0
MAIN_LANE_CLEANUP_ALLOWED=0
mkdir -p "$OUT"/{setup,runs,post}
printf '%s\n' "$START_ISO" > "$OUT/setup/start-time.txt"
cp "$0" "$OUT/translation-direct-candidate-screen.sh" 2>/dev/null || true

need() {
    command -v "$1" >/dev/null 2>&1 || { printf 'ERROR: required command unavailable: %s\n' "$1" >&2; exit 1; }
}
for cmd in bc250-benchmark bc250-model curl jq ollama python3 rpm systemctl journalctl tar sha256sum flock awk grep; do need "$cmd"; done
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

sample_resource() {
    awk '/^MemAvailable:/ {mem=$2/1024} /^SwapTotal:/ {st=$2} /^SwapFree:/ {sf=$2} END {printf "%.2f %.2f\n",mem,(st-sf)/1024}' /proc/meminfo
}

wait_recovery() {
    local i mem swap
    for i in $(seq 1 120); do
        read -r mem swap < <(sample_resource)
        awk -v m="$mem" -v gate="$RECOVERY_MEM_MIB" 'BEGIN{exit !(m>=gate)}' && return 0
        sleep 0.5
    done
    printf 'ERROR: MemAvailable did not recover to %s MiB after candidate unload.\n' "$RECOVERY_MEM_MIB" >&2
    return 1
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
    local n="$1" dir="$OUT/runs/$1" rc start_mem start_swap end_mem end_swap
    unload_main
    read -r start_mem start_swap < <(sample_resource)
    printf '\n===== direct translation / %s / round %s / think=%s =====\n' "$CANDIDATE" "$n" "$THINK_POLICY"
    set +e
    bc250-benchmark translation "$CANDIDATE" --think "$THINK_POLICY" --ollama-url "$MAIN_URL" --output-dir "$dir" \
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
    wait_recovery || return 27
    read -r end_mem end_swap < <(sample_resource)
    python3 - "$start_mem" "$start_swap" "$end_mem" "$end_swap" > "$OUT/runs/${n}.resource-window.txt" <<'PY2'
import sys
sm,ss,em,es=map(float,sys.argv[1:])
print(f'start_mem_available_mib={sm:.2f}')
print(f'end_mem_available_mib={em:.2f}')
print(f'start_swap_used_mib={ss:.2f}')
print(f'end_swap_used_mib={es:.2f}')
print(f'swap_delta_mib={es-ss:.2f}')
PY2
}

capture_provenance() {
    ollama --version > "$OUT/setup/ollama-version.txt" 2>&1 || true
    curl -sS --connect-timeout 5 --max-time 30 -H 'Content-Type: application/json' \
        -d "$(jq -cn --arg model "$CANDIDATE" '{model:$model}')" "$MAIN_URL/api/show" \
        > "$OUT/setup/candidate-ollama-show.json" 2>&1 || true
    local category resolved sidecar
    category=experiments; [[ "$INSTALL_EXPERIMENT" == 0 ]] && category=production
    resolved="$(bc250-model path "$category" "$CANDIDATE" 2>/dev/null | cut -f1 || true)"
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
        --arg quality "$quality" --arg infrastructure "$infra" --arg think_policy "$THINK_POLICY" --argjson final_rc "$final_rc" \
        --argjson serious_warning_count "$SERIOUS_WARNING_COUNT" \
        '{candidate:$candidate,path:$path,rounds:$rounds,think_policy:$think_policy,quality_result:$quality,infrastructure_result:$infrastructure,final_rc:$final_rc,serious_warning_count:$serious_warning_count}' \
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
print('\nRESOURCE WINDOWS')
for p in sorted((root/'runs').glob('*.resource-window.txt')):
    print(f"round {p.stem.split('.')[0]}: " + ' '.join(p.read_text().splitlines()))
print('\nFAILED RESPONSES')
for r in rows:
    if r.get('outcome')=='pass': continue
    print(f"\n[round={r['_round']} {r['case_id']}] fail={','.join(r.get('failure_kinds',[])) or '-'} diag={','.join(r.get('diagnostics',[])) or '-'}")
    print(r.get('response',''))
PY
}

finalize() {
    local rc=$? tar_rc=125 privacy_rc=0 definition_rc=0
    trap - EXIT
    set +e
    if [[ "$MAIN_LANE_CLEANUP_ALLOWED" == 1 ]]; then
        unload_main >/dev/null 2>&1 || true
        wait_recovery >/dev/null 2>&1 || { [[ "$rc" == 0 || "$rc" == 3 ]] && rc=28; }
    fi
    capture_state "$OUT/post/state-after" || true
    curl -sS --connect-timeout 5 --max-time 30 -H 'Content-Type: application/json' \
        -d "$(jq -cn --arg model "$CANDIDATE" '{model:$model}')" "$MAIN_URL/api/show" \
        > "$OUT/post/candidate-ollama-show-after.json" 2>&1 || true
    if [[ -s "$OUT/setup/candidate-ollama-show.json" && -s "$OUT/post/candidate-ollama-show-after.json" ]]; then
      python3 - "$OUT/setup/candidate-ollama-show.json" "$OUT/post/candidate-ollama-show-after.json" > "$OUT/post/model-definition-check.txt" <<'PY2'
import json,sys
a=json.load(open(sys.argv[1],encoding='utf-8')); b=json.load(open(sys.argv[2],encoding='utf-8'))
keys=('modelfile','parameters','template','system','details')
ok=all(a.get(k)==b.get(k) for k in keys)
print(f'model_definition_unchanged={str(ok).lower()}')
raise SystemExit(0 if ok else 1)
PY2
      definition_rc=$?
      [[ "$definition_rc" == 0 ]] || { [[ "$rc" == 0 || "$rc" == 3 ]] && rc=29; }
    fi
    journalctl -b --since "$START_ISO" --no-pager -u ollama.service > "$OUT/post/service-journal.txt" 2>&1 || true
    journalctl -k -b --since "$START_ISO" --no-pager > "$OUT/post/kernel-journal.txt" 2>&1 || true
    grep -Ein 'out of memory|oom-kill|oom_reaper|killed process|device lost|gpu reset|amdgpu.*(reset|timeout|fault)|ring.*(timeout|reset|fault|error)' \
        "$OUT/post/service-journal.txt" "$OUT/post/kernel-journal.txt" > "$OUT/post/serious-warnings.txt" 2>/dev/null || true
    SERIOUS_WARNING_COUNT="$(wc -l < "$OUT/post/serious-warnings.txt" | tr -d ' ')"
    [[ "$SERIOUS_WARNING_COUNT" == 0 ]] || { [[ "$rc" == 0 || "$rc" == 3 ]] && rc=30; }
    write_aggregate || true
    date --iso-8601=seconds > "$OUT/post/end-time.txt"
    # The benchmark prints its result paths. Redact this script's expected local HOME
    # prefix from console captures before the privacy scan so the scanner still catches
    # unrelated user paths without withholding every normal evidence archive.
    python3 - "$OUT" "$HOME" <<'PY2'
from pathlib import Path
import sys
root=Path(sys.argv[1]); home=sys.argv[2]
for p in (root/'runs').glob('*.console.txt'):
    try: text=p.read_text(encoding='utf-8')
    except (OSError, UnicodeError): continue
    p.write_text(text.replace(home, '$HOME'), encoding='utf-8')
PY2
    python3 - "$OUT" > "$OUT/post/privacy-scan.txt" <<'PY2'
from pathlib import Path
import re,sys
root=Path(sys.argv[1]); hits=[]
patterns=[
 ('authorization',re.compile(rb'Authorization:\s*Bearer\s+\S+',re.I)),
 ('bearer',re.compile(rb'\bBearer\s+[A-Za-z0-9._~+/=-]{12,}',re.I)),
 ('secret-key',re.compile(rb'\b(?:api_key|access_token|auth_token)\b\s*[=:]\s*[^\s,}]+',re.I)),
 ('home-path',re.compile(rb'/' + b'home/' + rb'[A-Za-z0-9._-]+/')),
 ('email',re.compile(rb'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')),
]
for p in root.rglob('*'):
    if not p.is_file() or p.name=='privacy-scan.txt': continue
    try:data=p.read_bytes()
    except OSError:continue
    for name,pat in patterns:
        if pat.search(data): hits.append((name,str(p)))
if hits:
    print('privacy_scan=FAIL')
    for name,p in hits: print(f'{name}: {p}')
    raise SystemExit(1)
print('privacy_scan=PASS')
PY2
    privacy_rc=$?
    if [[ "$privacy_rc" != 0 && ( "$rc" == 0 || "$rc" == 3 ) ]]; then rc=32; fi
    # Privacy is part of the result: do not persist a final rc before it is known.
    printf '%s\n' "$rc" > "$OUT/post/script-exit-rc.txt"
    write_run_manifest "$rc"
    local parent name tarball
    parent="$(dirname "$OUT")"; name="$(basename "$OUT")"; tarball="$HOME/${name}.tar.gz"
    if [[ "$privacy_rc" == 0 ]]; then
        tar --owner=0 --group=0 --numeric-owner -C "$parent" -czf "$tarball" "$name"
        tar_rc=$?
        if [[ "$tar_rc" != 0 && ( "$rc" == 0 || "$rc" == 3 ) ]]; then
            rc=31
            # Archive failure changes the authoritative local result as well.
            printf '%s\n' "$rc" > "$OUT/post/script-exit-rc.txt"
            write_run_manifest "$rc"
        fi
    fi
    printf '\n=== direct translation candidate summary ===\n'
    cat "$OUT/aggregate.txt" 2>/dev/null || true
    printf 'Evidence: %s\n' "$OUT"
    if [[ "$privacy_rc" == 0 && "$tar_rc" == 0 ]]; then printf 'Tarball: %s\n' "$tarball"; sha256sum "$tarball"; else printf 'Tarball withheld/failed; inspect local evidence directory.\n'; fi
    exit "$rc"
}
trap finalize EXIT

# Preflight an intentionally empty main lane; never evict an operator workload.
systemctl is-active --quiet ollama.service || { echo 'ERROR: ollama.service inactive.' >&2; exit 1; }
exec 9>"$LOCK_FILE"
flock -n 9 || { echo 'ERROR: another direct translation screen is active.' >&2; exit 26; }
capture_state "$OUT/setup/state-before"
INITIAL_MAIN_COUNT="$(jq '.models | length' "$OUT/setup/state-before/main-ps.json")"
[[ "$INITIAL_MAIN_COUNT" == 0 ]] || { echo 'ERROR: main Ollama lane must be empty before a foreground direct translation screen; refusing to unload a pre-existing model.' >&2; exit 26; }
MAIN_LANE_CLEANUP_ALLOWED=1
cp /usr/libexec/bc250-llm-server/category-benchmark.py "$OUT/setup/category-benchmark.py"
cp /usr/share/bc250-llm-server/benchmark/translation-office.json "$OUT/setup/translation-office.json"
if [[ "$INSTALL_EXPERIMENT" == 1 ]]; then
    sudo bc250-model apply experiments "$CANDIDATE" 2>&1 | tee "$OUT/setup/candidate-apply.txt"
else
    printf 'production reference: using existing registered model %s\n' "$CANDIDATE" | tee "$OUT/setup/candidate-apply.txt"
fi
model_present || { echo 'ERROR: candidate/reference model is not registered on main Ollama.' >&2; exit 1; }
capture_provenance
# Run identical rounds sequentially so candidate comparisons share one contract.
for n in $(seq 1 "$ROUNDS"); do run_round "$n"; done
write_aggregate
[[ "$QUALITY_FAIL" == 0 ]] || exit 3
