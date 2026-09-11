#!/usr/bin/env bash
# Second-stage translation integration check. Temporarily points the existing
# Open WebUI translation preset at one experimental model, verifies live readback,
# runs the production-style source-only inputs, and restores the exact preset.
set -Eeuo pipefail
umask 077

CANDIDATE="${1:-}"
PROMPT_FILE="${2:-}"
ROUNDS="${3:-${BC250_SCREEN_ROUNDS:-3}}"
ALLOW_PRODUCTION_REFERENCE="${BC250_ALLOW_PRODUCTION_REFERENCE:-0}"
PRESET='bc250-office-translation'
MAIN_URL='http://127.0.0.1:11434'
MAIN_HOST='127.0.0.1:11434'
OWUI_URL='http://127.0.0.1:3000'
TOKEN_FILE="${BC250_OWUI_TOKEN_FILE:-/root/owui-test.key}"
FIXTURE='/usr/share/bc250-llm-server/benchmark/translation-office.json'
BENCH='/usr/libexec/bc250-llm-server/category-benchmark.py'
HEADER_FILE=''
ORIGINAL_SAVED=0
TELEMETRY_PID=''
TELEMETRY_STOP=''

[[ -n "$CANDIDATE" && -n "$PROMPT_FILE" ]] || {
    echo "usage: $0 EXPERIMENT-MODEL SYSTEM-PROMPT-FILE [ROUNDS]" >&2
    exit 2
}
if [[ "$CANDIDATE" == exp-* ]]; then
    INSTALL_EXPERIMENT=1
elif [[ "$ALLOW_PRODUCTION_REFERENCE" == 1 && "$CANDIDATE" == prod-lfm25-8b-a1b-liquidai-q6-k ]]; then
    INSTALL_EXPERIMENT=0
else
    echo 'ERROR: model must be an exp-* candidate (or the explicit production LFM reference wrapper).' >&2
    exit 2
fi
[[ -r "$PROMPT_FILE" ]] || { printf 'ERROR: prompt file unreadable: %s\n' "$PROMPT_FILE" >&2; exit 2; }
[[ "$ROUNDS" =~ ^[1-9][0-9]*$ ]] || { echo 'ERROR: rounds must be positive.' >&2; exit 2; }

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="${BC250_QUALITY_ROOT:-$HOME/bc250-quality}"
SAFE_NAME="${CANDIDATE//[^a-zA-Z0-9._-]/_}"
OUT="$ROOT/translation-owui-${SAFE_NAME}-${STAMP}"
START_ISO="$(date --iso-8601=seconds)"
mkdir -p "$OUT"/{setup,runs,post}
printf '%s\n' "$START_ISO" > "$OUT/setup/start-time.txt"
cp "$0" "$OUT/translation-owui-candidate-screen.sh" 2>/dev/null || true
cp "$PROMPT_FILE" "$OUT/setup/candidate-system.txt"

need() { command -v "$1" >/dev/null 2>&1 || { printf 'ERROR: required command unavailable: %s\n' "$1" >&2; exit 1; }; }
for cmd in bc250-model curl jq ollama python3 rpm systemctl journalctl tar sha256sum; do need "$cmd"; done
sudo -v
sudo test -r "$TOKEN_FILE" && sudo test -s "$TOKEN_FILE" || { printf 'ERROR: token file unavailable: %s\n' "$TOKEN_FILE" >&2; exit 1; }

HEADER_FILE="$(sudo mktemp /run/bc250-owui-header.XXXXXX)"
sudo chmod 600 "$HEADER_FILE"
sudo bash -c 'set -euo pipefail; token="$(<"$1")"; printf "Authorization: Bearer %s\n" "$token" > "$2"' bash "$TOKEN_FILE" "$HEADER_FILE"

owui_get() {
    sudo curl -fsS --connect-timeout 10 --max-time 900 -H @"$HEADER_FILE" "$OWUI_URL$1"
}
owui_post_file() {
    sudo curl -fsS --connect-timeout 10 --max-time 900 -H @"$HEADER_FILE" \
        -H 'Content-Type: application/json' --data-binary @"$2" "$OWUI_URL$1"
}

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

restore_original() {
    [[ "$ORIGINAL_SAVED" == 1 ]] || return 0
    jq -n --slurpfile model "$OUT/setup/original-preset.json" '{models:[$model[0]]}' > "$OUT/post/restore-payload.json"
    owui_post_file '/api/v1/models/import' "$OUT/post/restore-payload.json" > "$OUT/post/restore-response.json"
    owui_get '/api/v1/models/export' | jq --arg id "$PRESET" '.[] | select(.id == $id)' > "$OUT/post/restored-preset.json"
    python3 - "$OUT/setup/original-preset.json" "$OUT/post/restored-preset.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as f: a=json.load(f)
with open(sys.argv[2], encoding='utf-8') as f: b=json.load(f)
def stable(x):
    return {k:x.get(k) for k in ('id','base_model_id','name','params','meta','is_active','access_grants')}
if stable(a)!=stable(b):
    raise SystemExit('restored preset differs from original')
print('Preset restoration verified.')
PY
    printf '%s\n' 'Preset restoration verified.' > "$OUT/post/restoration-status.txt"
}

write_evaluator() {
cat > "$OUT/setup/evaluate.py" <<'PY'
#!/usr/bin/env python3
import argparse, importlib.util, json, math, pathlib, statistics, sys
from collections import Counter, defaultdict

def load_benchmark(path):
    path=pathlib.Path(path); sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('bc250_category_benchmark',path)
    if spec is None or spec.loader is None: raise RuntimeError(path)
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod

def response_parts(result):
    choices=result.get('choices') if isinstance(result,dict) else None
    if not isinstance(choices,list) or not choices: return '', '', ''
    choice=choices[0] if isinstance(choices[0],dict) else {}
    msg=choice.get('message',{}) if isinstance(choice,dict) else {}
    content=str(msg.get('content') or '') if isinstance(msg,dict) else ''
    thinking=''
    if isinstance(msg,dict): thinking=str(msg.get('thinking') or msg.get('reasoning_content') or '')
    finish=str(choice.get('finish_reason') or '') if isinstance(choice,dict) else ''
    return content, thinking, finish

def read_json(path, default):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError): return default

def read_float(path):
    try: return float(path.read_text(encoding='utf-8').strip())
    except (OSError, ValueError): return None

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

def pct(xs,q):
    if not xs: return None
    ys=sorted(xs); idx=max(0,min(len(ys)-1,math.ceil(q*len(ys))-1)); return ys[idx]

def summary(label,xs):
    passed=sum(r['outcome']=='pass' for r in xs)
    failures=Counter(x for r in xs for x in r.get('failure_kinds',[]))
    diagnostics=Counter(x for r in xs for x in r.get('diagnostics',[]))
    mem=nums(xs,('telemetry','mem_available_min_mib')); swap=nums(xs,('telemetry','swap_used_max_mib')); temp=nums(xs,('telemetry','temp_max_c')); wall=nums(xs,('metrics','wall_s'))
    print(f'{label}: {passed}/{len(xs)}')
    print(f"  failures={dict(failures) or '-'} diagnostics={dict(diagnostics) or '-'}")
    print(f"  min_mem_available_mib={min(mem) if mem else 'NA'} max_swap_used_mib={max(swap) if swap else 'NA'} max_temp_c={max(temp) if temp else 'NA'}")
    print(f"  wall_mean_s={statistics.mean(wall):.3f}" if wall else '  wall_mean_s=NA',end='')
    print(f" wall_p95_s={pct(wall,0.95):.3f}" if wall else ' wall_p95_s=NA')

p=argparse.ArgumentParser(); p.add_argument('--benchmark',required=True); p.add_argument('--fixture',required=True); p.add_argument('--root',required=True); p.add_argument('--model',required=True)
a=p.parse_args(); bench=load_benchmark(a.benchmark); root=pathlib.Path(a.root)
cases=json.loads(pathlib.Path(a.fixture).read_text(encoding='utf-8')); byid={c['id']:c for c in cases}; rows=[]
round_dirs=[rd for rd in sorted((root/'runs').glob('*'), key=lambda x:int(x.name) if x.name.isdigit() else 999999) if rd.is_dir() and rd.name.isdigit()]
for rd in round_dirs:
    raw_files=sorted((rd/'raw').glob('*.response.json'))
    if len(raw_files)!=len(cases):
        raise SystemExit(f'infrastructure: round {rd.name} has {len(raw_files)} responses, expected {len(cases)}')
    n=int(rd.name)
    for raw in raw_files:
        cid=raw.name.removesuffix('.response.json')
        if cid not in byid: raise SystemExit(f'infrastructure: unknown case response {cid}')
        case=byid[cid]; result=json.loads(raw.read_text(encoding='utf-8')); content,thinking,finish=response_parts(result)
        required, forbidden, preserved, meaningful=bench.translation_content_checks(content,case)
        language=bench.task_language_hint(content,case['target_language'])=='match'; semantic=required and meaningful
        passed=bool(content.strip()) and language and semantic and forbidden and preserved
        failures=bench.translation_failure_kinds(content, language_ok=language, source_leakage_ok=forbidden, semantic_ok=semantic, preserved_ok=preserved)
        diagnostics=[]
        if finish=='length':
            diagnostics.append('output-budget')
            if not content.strip() and thinking.strip(): diagnostics.append('thinking-budget')
        telemetry=read_json(rd/'telemetry'/f'{cid}.json',{})
        wall=read_float(rd/'timing'/f'{cid}.wall_s')
        rows.append({'result_type':'qualification','path':'owui-candidate','round':n,'model':a.model,'case_id':cid,'source_language':case['source_language'],'target_language':case['target_language'],'outcome':'pass' if passed else 'quality-fail','failure_kinds':failures,'diagnostics':diagnostics,'checks':{'language':language,'semantic':semantic,'preservation':preserved,'source_leakage':forbidden},'metrics':{'wall_s':wall,'answer_chars':len(content),'thinking_chars':len(thinking),'finish_reason':finish},'telemetry':telemetry,'response':content,'thinking':thinking})
with (root/'results.jsonl').open('w',encoding='utf-8') as f:
    for r in rows: f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
summary('OVERALL',rows)
print('\nPER ROUND')
for n in sorted({r['round'] for r in rows}): summary(f'round {n}',[r for r in rows if r['round']==n])
print('\nBY DIRECTION')
for src,tgt in (('de','fr'),('fr','de')): summary(f'{src.upper()}->{tgt.upper()}',[r for r in rows if r['source_language']==src and r['target_language']==tgt])
print('\nPER CASE'); grouped=defaultdict(list)
for r in rows: grouped[r['case_id']].append(r)
for cid,xs in sorted(grouped.items()):
    n=sum(r['outcome']=='pass' for r in xs); fs=sorted({x for r in xs for x in r.get('failure_kinds',[])}); ds=sorted({x for r in xs for x in r.get('diagnostics',[])})
    print(f"{cid}\t{n}/{len(xs)}\tfail={','.join(fs) or '-'}\tdiag={','.join(ds) or '-'}")
print('\nFAILED RESPONSES')
for r in rows:
    if r['outcome']=='pass': continue
    print(f"\nround={r['round']} case={r['case_id']} fail={','.join(r.get('failure_kinds',[])) or '-'} diag={','.join(r.get('diagnostics',[])) or '-'}"); print(r['response'])
if not rows: raise SystemExit('infrastructure: no translation result rows')
raise SystemExit(0 if all(r['outcome']=='pass' for r in rows) else 3)
PY
chmod 0700 "$OUT/setup/evaluate.py"
python3 -m py_compile "$OUT/setup/evaluate.py"
}

write_telemetry_helper() {
cat > "$OUT/setup/telemetry-window.py" <<'PY'
#!/usr/bin/env python3
import argparse, json, pathlib, sys, time
p=argparse.ArgumentParser(); p.add_argument('--benchmark-dir',required=True); p.add_argument('--ready',required=True); p.add_argument('--stop',required=True); p.add_argument('--output',required=True); p.add_argument('--interval',type=float,default=0.5)
a=p.parse_args(); sys.path.insert(0,a.benchmark_dir)
from benchmark_common import TelemetrySampler
ready=pathlib.Path(a.ready); stop=pathlib.Path(a.stop); out=pathlib.Path(a.output)
sampler=TelemetrySampler(a.interval).start(); ready.touch()
try:
    while not stop.exists(): time.sleep(0.05)
finally:
    data=sampler.stop(); out.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf-8')
PY
chmod 0700 "$OUT/setup/telemetry-window.py"
python3 -m py_compile "$OUT/setup/telemetry-window.py"
}

credential_scan() {
    sudo python3 - "$TOKEN_FILE" "$OUT" <<'PY'
from pathlib import Path
import sys
token=Path(sys.argv[1]).read_text(encoding='utf-8').strip().encode(); root=Path(sys.argv[2])
if not token: raise SystemExit('token unexpectedly empty')
hits=[]
for p in root.rglob('*'):
    if not p.is_file(): continue
    try: data=p.read_bytes()
    except OSError: continue
    if token in data: hits.append(str(p))
if hits:
    print('ERROR: token found in evidence:',*hits,sep='\n',file=sys.stderr); raise SystemExit(1)
print('credential scan: Open WebUI token not present in evidence')
PY
}

finalize() {
    local rc=$? restore_rc=0
    trap - EXIT
    set +e
    if [[ -n "$TELEMETRY_STOP" ]]; then touch "$TELEMETRY_STOP" 2>/dev/null || true; fi
    if [[ -n "$TELEMETRY_PID" ]]; then wait "$TELEMETRY_PID" 2>/dev/null || true; fi
    TELEMETRY_PID=''; TELEMETRY_STOP=''
    printf '%s\n' "$rc" > "$OUT/post/test-script-rc.txt"
    if ! restore_original; then printf '%s\n' 'ERROR: preset restoration failed.' > "$OUT/post/restoration-status.txt"; restore_rc=1; rc=23; fi
    unload_main >/dev/null 2>&1 || true
    capture_state "$OUT/post/state-after" || true
    journalctl -b --since "$START_ISO" --no-pager -u ollama.service -u open-webui.service > "$OUT/post/service-journal.txt" 2>&1 || true
    journalctl -k -b --since "$START_ISO" --no-pager > "$OUT/post/kernel-journal.txt" 2>&1 || true
    grep -Ein 'out of memory|oom-kill|oom_reaper|killed process|device lost|gpu reset|amdgpu.*(reset|timeout|fault)|ring.*(timeout|reset|fault|error)' \
        "$OUT/post/service-journal.txt" "$OUT/post/kernel-journal.txt" > "$OUT/post/serious-warnings.txt" 2>/dev/null || true
    python3 "$OUT/setup/evaluate.py" --benchmark "$BENCH" --fixture "$FIXTURE" --root "$OUT" --model "$CANDIDATE" > "$OUT/aggregate.txt" 2>&1 || true
    if [[ -n "$HEADER_FILE" ]]; then sudo rm -f "$HEADER_FILE" || true; HEADER_FILE=''; fi
    if ! credential_scan > "$OUT/post/credential-scan.txt" 2>&1; then cat "$OUT/post/credential-scan.txt" >&2; rc=24; fi
    printf '%s\n' "$(date --iso-8601=seconds)" > "$OUT/post/end-time.txt"
    local parent name tarball
    parent="$(dirname "$OUT")"; name="$(basename "$OUT")"; tarball="$HOME/${name}.tar.gz"
    tar -C "$parent" -czf "$tarball" "$name"; sha256sum "$tarball" > "$tarball.sha256"
    printf '\n=== OWUI translation candidate summary ===\n'; cat "$OUT/aggregate.txt" 2>/dev/null || true
    printf 'Evidence: %s\nTarball: %s\n' "$OUT" "$tarball"; cat "$tarball.sha256"
    [[ "$restore_rc" == 0 ]] || printf '\nCRITICAL: preset restoration FAILED.\n' >&2
    exit "$rc"
}
trap finalize EXIT

systemctl is-active --quiet ollama.service || { echo 'ERROR: ollama.service inactive.' >&2; exit 1; }
systemctl is-active --quiet open-webui.service || { echo 'ERROR: open-webui.service inactive.' >&2; exit 1; }
capture_state "$OUT/setup/state-before"
sha256sum "$BENCH" "$FIXTURE" > "$OUT/setup/benchmark-contract.sha256"
cp "$FIXTURE" "$OUT/setup/translation-office.json"
owui_get '/api/v1/models/export' | jq --arg id "$PRESET" '.[] | select(.id == $id)' > "$OUT/setup/original-preset.json"
jq -e --arg id "$PRESET" '.id == $id' "$OUT/setup/original-preset.json" >/dev/null || { echo 'ERROR: translation preset not found.' >&2; exit 1; }
ORIGINAL_SAVED=1
if [[ "$INSTALL_EXPERIMENT" == 1 ]]; then
    sudo bc250-model install experiments "$CANDIDATE" 2>&1 | tee "$OUT/setup/candidate-install.txt"
else
    printf 'production reference: using existing registered model %s\n' "$CANDIDATE" | tee "$OUT/setup/candidate-install.txt"
fi
SYSTEM_PROMPT="$(cat "$PROMPT_FILE")"
jq --arg base "${CANDIDATE}:latest" --arg system "$SYSTEM_PROMPT" '
  .base_model_id=$base | .params=((.params // {}) + {system:$system}) | del(.params.temperature)
' "$OUT/setup/original-preset.json" > "$OUT/setup/candidate-preset.json"
jq -n --slurpfile model "$OUT/setup/candidate-preset.json" '{models:[$model[0]]}' > "$OUT/setup/candidate-import.json"
owui_post_file '/api/v1/models/import' "$OUT/setup/candidate-import.json" > "$OUT/setup/candidate-import-response.json"
owui_get '/api/v1/models/export' | jq --arg id "$PRESET" '.[] | select(.id == $id)' > "$OUT/setup/live-candidate-preset.json"
python3 - "$OUT/setup/original-preset.json" "$OUT/setup/live-candidate-preset.json" "${CANDIDATE}:latest" "$SYSTEM_PROMPT" <<'PY'
import copy,json,sys
with open(sys.argv[1],encoding='utf-8') as f: original=json.load(f)
with open(sys.argv[2],encoding='utf-8') as f: live=json.load(f)
expected=copy.deepcopy(original); expected['base_model_id']=sys.argv[3]; expected['params']=dict(expected.get('params') or {}); expected['params']['system']=sys.argv[4]; expected['params'].pop('temperature',None)
def stable(x): return {k:x.get(k) for k in ('id','base_model_id','name','params','meta','is_active','access_grants')}
if stable(expected)!=stable(live): raise SystemExit('selected stable live preset fields differ outside the intended candidate delta')
print('Live candidate preset verified.')
PY
write_evaluator
write_telemetry_helper

for n in $(seq 1 "$ROUNDS"); do
    printf '\n===== OWUI candidate %s / round %s =====\n' "$CANDIDATE" "$n"
    RUN="$OUT/runs/$n"; mkdir -p "$RUN"/{payloads,raw,telemetry,timing}; unload_main
    while IFS=$'\t' read -r case_id text; do
        payload="$RUN/payloads/${case_id}.json"; raw="$RUN/raw/${case_id}.response.json"
        jq -n --arg model "$PRESET" --arg text "$text" '{model:$model,messages:[{role:"user",content:$text}],stream:false,background_tasks:{title_generation:false,tags_generation:false,follow_up_generation:false}}' > "$payload"

        ready="$RUN/telemetry/${case_id}.ready"; stop="$RUN/telemetry/${case_id}.stop"; telemetry="$RUN/telemetry/${case_id}.json"
        rm -f "$ready" "$stop" "$telemetry"
        python3 "$OUT/setup/telemetry-window.py" --benchmark-dir "$(dirname "$BENCH")" --ready "$ready" --stop "$stop" --output "$telemetry" &
        TELEMETRY_PID=$!; TELEMETRY_STOP="$stop"
        for _ in $(seq 1 100); do
            [[ -e "$ready" ]] && break
            kill -0 "$TELEMETRY_PID" 2>/dev/null || { echo 'ERROR: telemetry sampler exited early.' >&2; exit 22; }
            sleep 0.05
        done
        [[ -e "$ready" ]] || { echo 'ERROR: telemetry sampler did not become ready.' >&2; exit 22; }

        start_ns="$(date +%s%N)"
        set +e
        owui_post_file '/api/chat/completions' "$payload" | jq . > "$raw"
        request_rc=$?
        set -e
        end_ns="$(date +%s%N)"
        touch "$stop"
        wait "$TELEMETRY_PID" || { echo 'ERROR: telemetry sampler failed.' >&2; exit 22; }
        TELEMETRY_PID=''; TELEMETRY_STOP=''
        python3 - "$start_ns" "$end_ns" <<'PY' > "$RUN/timing/${case_id}.wall_s"
import sys
print(f"{(int(sys.argv[2])-int(sys.argv[1]))/1_000_000_000:.6f}")
PY
        [[ "$request_rc" == 0 ]] || { printf 'ERROR: OWUI request failed: round=%s case=%s rc=%s\n' "$n" "$case_id" "$request_rc" >&2; exit 20; }
        jq -e '.choices | type=="array" and length>0 and .[0].message.content != null' "$raw" >/dev/null || { printf 'ERROR: malformed OWUI response: round=%s case=%s\n' "$n" "$case_id" >&2; exit 21; }
    done < <(jq -r '.[] | [.id,.input] | @tsv' "$FIXTURE")
    unload_main
done
set +e
python3 "$OUT/setup/evaluate.py" --benchmark "$BENCH" --fixture "$FIXTURE" --root "$OUT" --model "$CANDIDATE" > "$OUT/aggregate.txt"
eval_rc=$?
set -e
cat "$OUT/aggregate.txt"
[[ "$eval_rc" == 0 || "$eval_rc" == 3 ]] || exit "$eval_rc"
[[ "$eval_rc" == 0 ]] || exit 3
