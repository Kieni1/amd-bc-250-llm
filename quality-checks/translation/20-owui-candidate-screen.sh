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
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROVIDER_HELPER="${BC250_PROVIDER_HELPER:-$HERE/owui-provider-config.py}"
LOCK_FILE='/run/lock/bc250-translation-owui.lock'
HEADER_FILE=''
ROOT_TMP_FILES=()
ORIGINAL_OLLAMA_CONFIG=''
CANDIDATE_OLLAMA_CONFIG=''
LIVE_OLLAMA_CONFIG=''
RESTORED_OLLAMA_CONFIG=''
ORIGINAL_SAVED=0
ORIGINAL_OLLAMA_CONFIG_SAVED=0
OLLAMA_CONFIG_MUTATED=0
CANDIDATE_VISIBLE_BEFORE=-1
CANDIDATE_BASE_ID="${CANDIDATE}:latest"
TELEMETRY_PID=''
TELEMETRY_STOP=''
REQUEST_FAILURES=0
QUALITY_RC=-1
PRESET_RESTORED=0
PROVIDER_RESTORED=0
CREDENTIAL_SCAN_CLEAN=0
SERIOUS_WARNING_COUNT=0

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
[[ -r "$PROVIDER_HELPER" ]] || { printf 'ERROR: provider helper unreadable: %s\n' "$PROVIDER_HELPER" >&2; exit 2; }
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
cp "$PROVIDER_HELPER" "$OUT/setup/owui-provider-config.py"

need() { command -v "$1" >/dev/null 2>&1 || { printf 'ERROR: required command unavailable: %s\n' "$1" >&2; exit 1; }; }
for cmd in bc250-model curl flock jq ollama python3 rpm systemctl journalctl tar sha256sum; do need "$cmd"; done
sudo -v
sudo test -r "$TOKEN_FILE" && sudo test -s "$TOKEN_FILE" || { printf 'ERROR: token file unavailable: %s\n' "$TOKEN_FILE" >&2; exit 1; }

sudo touch "$LOCK_FILE"
sudo chown "$(id -u):$(id -g)" "$LOCK_FILE"
sudo chmod 0600 "$LOCK_FILE"
exec {LOCK_FD}>"$LOCK_FILE"
flock -n "$LOCK_FD" || { echo 'ERROR: another translation OWUI mutation screen is active.' >&2; exit 26; }

HEADER_FILE="$(sudo mktemp /run/bc250-owui-header.XXXXXX)"
sudo chmod 600 "$HEADER_FILE"
sudo bash -c 'set -euo pipefail; token="$(<"$1")"; printf "Authorization: Bearer %s\n" "$token" > "$2"' bash "$TOKEN_FILE" "$HEADER_FILE"

owui_get() {
    sudo curl -fsS --connect-timeout 10 --max-time 900 -H @"$HEADER_FILE" "$OWUI_URL$1"
}

make_root_tmp() {
    local var="$1" template="$2" path
    path="$(sudo mktemp "/run/${template}.XXXXXX")"
    sudo chmod 0600 "$path"
    ROOT_TMP_FILES+=("$path")
    printf -v "$var" '%s' "$path"
}

record_http_meta() {
    local file="$1" operation="$2" method="$3" endpoint="$4" curl_rc="$5" http_code="$6"
    jq -n --arg operation "$operation" --arg method "$method" --arg endpoint "$endpoint" \
        --argjson curl_rc "$curl_rc" --arg http_status "$http_code" \
        '{operation:$operation,method:$method,endpoint:$endpoint,curl_rc:$curl_rc,http_status:$http_status}' > "$file"
}

owui_request() {
    local operation="$1" method="$2" endpoint="$3" input="$4" body="$5" meta="$6"
    local tmp metrics curl_rc=0 http_code
    tmp="$(sudo mktemp /run/bc250-owui-response.XXXXXX)"; sudo chmod 0600 "$tmp"
    local args=(sudo curl -sS --connect-timeout 10 --max-time 900 -H @"$HEADER_FILE" -o "$tmp" -w '%{http_code}')
    if [[ "$method" == POST ]]; then args+=(-H 'Content-Type: application/json' --data-binary @"$input"); fi
    args+=("$OWUI_URL$endpoint")
    metrics="$("${args[@]}")" || curl_rc=$?
    http_code="${metrics:-000}"
    sudo cat "$tmp" > "$body"
    sudo rm -f "$tmp"
    record_http_meta "$meta" "$operation" "$method" "$endpoint" "$curl_rc" "$http_code"
    if [[ "$curl_rc" != 0 || ! "$http_code" =~ ^2[0-9][0-9]$ ]]; then
        REQUEST_FAILURES=$((REQUEST_FAILURES + 1))
        return 1
    fi
}

owui_sensitive_request() {
    local operation="$1" method="$2" endpoint="$3" input="$4" raw="$5" redacted="$6" meta="$7" secrets_from="${8:-}"
    local metrics curl_rc=0 http_code
    local args=(sudo curl -sS --connect-timeout 10 --max-time 900 -H @"$HEADER_FILE" -o "$raw" -w '%{http_code}')
    if [[ "$method" == POST ]]; then args+=(-H 'Content-Type: application/json' --data-binary @"$input"); fi
    args+=("$OWUI_URL$endpoint")
    metrics="$("${args[@]}")" || curl_rc=$?
    http_code="${metrics:-000}"
    local sanitize=(sudo python3 "$PROVIDER_HELPER" sanitize --input "$raw")
    [[ -n "$secrets_from" ]] && sanitize+=(--secrets-from "$secrets_from")
    "${sanitize[@]}" > "$redacted"
    record_http_meta "$meta" "$operation" "$method" "$endpoint" "$curl_rc" "$http_code"
    if [[ "$curl_rc" != 0 || ! "$http_code" =~ ^2[0-9][0-9]$ ]]; then
        REQUEST_FAILURES=$((REQUEST_FAILURES + 1))
        return 1
    fi
}

save_original_ollama_config() {
    make_root_tmp ORIGINAL_OLLAMA_CONFIG 'bc250-owui-original-ollama-config'
    owui_sensitive_request 'capture-original-provider' GET '/ollama/config' '' \
        "$ORIGINAL_OLLAMA_CONFIG" "$OUT/setup/original-ollama-config.redacted.json" \
        "$OUT/setup/original-ollama-config.http.json" || return 1
    ORIGINAL_OLLAMA_CONFIG_SAVED=1
}

prepare_candidate_provider() {
    [[ "$INSTALL_EXPERIMENT" == 1 ]] || return 0
    make_root_tmp CANDIDATE_OLLAMA_CONFIG 'bc250-owui-candidate-ollama-config'
    sudo python3 "$PROVIDER_HELPER" prepare --input "$ORIGINAL_OLLAMA_CONFIG" \
        --candidate "${CANDIDATE}:latest" --output "$CANDIDATE_OLLAMA_CONFIG" \
        > "$OUT/setup/candidate-provider-delta.json"
    sudo python3 "$PROVIDER_HELPER" redact --input "$CANDIDATE_OLLAMA_CONFIG" \
        > "$OUT/setup/candidate-ollama-config.redacted.json"
    CANDIDATE_BASE_ID="$(jq -r '.effective_candidate_id' "$OUT/setup/candidate-provider-delta.json")"

    owui_request 'models-before-provider-change' GET '/api/models?refresh=true' '' \
        "$OUT/setup/models-before-provider-change.json" "$OUT/setup/models-before-provider-change.http.json" || return 1
    if jq -e --arg id "$CANDIDATE_BASE_ID" '.data[]? | select(.id == $id)' "$OUT/setup/models-before-provider-change.json" >/dev/null; then
        CANDIDATE_VISIBLE_BEFORE=1
    else
        CANDIDATE_VISIBLE_BEFORE=0
    fi
    printf '%s\n' "$CANDIDATE_VISIBLE_BEFORE" > "$OUT/setup/candidate-visible-before.txt"

    if [[ "$(jq -r '.allowlist_changed' "$OUT/setup/candidate-provider-delta.json")" == true ]]; then
        OLLAMA_CONFIG_MUTATED=1
        local update_raw
        make_root_tmp update_raw 'bc250-owui-provider-update-response'
        owui_sensitive_request 'update-ollama-provider' POST '/ollama/config/update' "$CANDIDATE_OLLAMA_CONFIG" \
            "$update_raw" "$OUT/setup/candidate-ollama-config-update-response.redacted.json" \
            "$OUT/setup/candidate-ollama-config-update.http.json" "$ORIGINAL_OLLAMA_CONFIG" || return 1
    fi

    make_root_tmp LIVE_OLLAMA_CONFIG 'bc250-owui-live-candidate-ollama-config'
    owui_sensitive_request 'readback-candidate-provider' GET '/ollama/config' '' \
        "$LIVE_OLLAMA_CONFIG" "$OUT/setup/live-candidate-ollama-config.redacted.json" \
        "$OUT/setup/live-candidate-ollama-config.http.json" "$ORIGINAL_OLLAMA_CONFIG" || return 1
    sudo python3 "$PROVIDER_HELPER" compare --expected "$CANDIDATE_OLLAMA_CONFIG" --actual "$LIVE_OLLAMA_CONFIG"

    owui_request 'models-after-provider-change' GET '/api/models?refresh=true' '' \
        "$OUT/setup/models-after-provider-refresh.json" "$OUT/setup/models-after-provider-refresh.http.json" || return 1
    jq -e --arg id "$CANDIDATE_BASE_ID" '.data[]? | select(.id == $id)' "$OUT/setup/models-after-provider-refresh.json" \
        > "$OUT/setup/live-candidate-base-model.json" || {
        printf 'ERROR: candidate remains unavailable after verified provider allow-list update: %s\n' "$CANDIDATE_BASE_ID" >&2
        return 1
    }
}

restore_original_ollama_config() {
    [[ "$ORIGINAL_OLLAMA_CONFIG_SAVED" == 1 ]] || return 0
    if [[ "$OLLAMA_CONFIG_MUTATED" == 1 ]]; then
        local restore_raw
        make_root_tmp restore_raw 'bc250-owui-provider-restore-response'
        owui_sensitive_request 'restore-ollama-provider' POST '/ollama/config/update' "$ORIGINAL_OLLAMA_CONFIG" \
            "$restore_raw" "$OUT/post/restore-ollama-config-response.redacted.json" \
            "$OUT/post/restore-ollama-config.http.json" "$ORIGINAL_OLLAMA_CONFIG" || return 1
    fi

    make_root_tmp RESTORED_OLLAMA_CONFIG 'bc250-owui-restored-ollama-config'
    owui_sensitive_request 'readback-restored-provider' GET '/ollama/config' '' \
        "$RESTORED_OLLAMA_CONFIG" "$OUT/post/restored-ollama-config.redacted.json" \
        "$OUT/post/restored-ollama-config.http.json" "$ORIGINAL_OLLAMA_CONFIG" || return 1
    sudo python3 "$PROVIDER_HELPER" compare --expected "$ORIGINAL_OLLAMA_CONFIG" --actual "$RESTORED_OLLAMA_CONFIG"

    owui_request 'models-after-provider-restore' GET '/api/models?refresh=true' '' \
        "$OUT/post/models-after-ollama-restore.json" "$OUT/post/models-after-ollama-restore.http.json" || return 1
    local visible_after=0 original_base
    if jq -e --arg id "$CANDIDATE_BASE_ID" '.data[]? | select(.id == $id)' "$OUT/post/models-after-ollama-restore.json" >/dev/null; then visible_after=1; fi
    printf '%s\n' "$visible_after" > "$OUT/post/candidate-visible-after.txt"
    if [[ "$CANDIDATE_VISIBLE_BEFORE" != -1 && "$visible_after" != "$CANDIDATE_VISIBLE_BEFORE" ]]; then
        echo 'ERROR: candidate effective visibility was not restored.' >&2
        return 1
    fi
    if [[ "$ORIGINAL_SAVED" == 1 ]]; then
        original_base="$(jq -r '.base_model_id' "$OUT/setup/original-preset.json")"
        jq -e --arg id "$PRESET" --arg base "$original_base" \
            '.data[]? | select(.id == $id and .info.base_model_id == $base)' "$OUT/post/models-after-ollama-restore.json" \
            > "$OUT/post/effective-restored-preset.json" || return 1
    fi
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

restore_original_preset() {
    [[ "$ORIGINAL_SAVED" == 1 ]] || return 0
    jq -n --slurpfile model "$OUT/setup/original-preset.json" '{models:[$model[0]]}' > "$OUT/post/restore-payload.json"
    owui_request 'restore-translation-preset' POST '/api/v1/models/import' "$OUT/post/restore-payload.json" \
        "$OUT/post/restore-response.json" "$OUT/post/restore-response.http.json" || return 1
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
    [[ "$ORIGINAL_OLLAMA_CONFIG_SAVED" == 1 && -n "$ORIGINAL_OLLAMA_CONFIG" ]] || {
        echo 'ERROR: original Ollama config unavailable for credential scan.' >&2
        return 1
    }
    sudo python3 "$PROVIDER_HELPER" scan \
        --config "$ORIGINAL_OLLAMA_CONFIG" \
        --token-file "$TOKEN_FILE" \
        --root "$OUT"
}

cleanup_root_tempfiles() {
    local path failed=0
    for path in "${ROOT_TMP_FILES[@]:-}"; do
        [[ -n "$path" ]] || continue
        sudo rm -f -- "$path" >/dev/null 2>&1 || failed=1
        sudo test ! -e "$path" || failed=1
    done
    ROOT_TMP_FILES=()
    return "$failed"
}

capture_provenance() {
    rpm -q --qf '%{NAME} %{VERSION}-%{RELEASE} %{ARCH}\n' bc250-llm-server > "$OUT/setup/package-version.txt"
    ollama --version > "$OUT/setup/ollama-version.txt" 2>&1 || true
    curl -sS --connect-timeout 5 --max-time 20 "$OWUI_URL/api/version" > "$OUT/setup/openwebui-version.json" 2>&1 || true
    sudo podman inspect open-webui --format '{{.ImageName}} {{.Image}}' > "$OUT/setup/openwebui-image.txt" 2>&1 || true
    curl -sS --connect-timeout 5 --max-time 30 -H 'Content-Type: application/json' \
        -d "$(jq -cn --arg model "$CANDIDATE" '{model:$model}')" "$MAIN_URL/api/show" \
        > "$OUT/setup/candidate-ollama-show.json" 2>&1 || true
    sha256sum "$PROMPT_FILE" "$BENCH" "$FIXTURE" "$PROVIDER_HELPER" > "$OUT/setup/evidence-contract.sha256"
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
    case "$QUALITY_RC" in
        0) quality=pass ;;
        3) quality=quality-fail ;;
        *) quality=not-run ;;
    esac
    if [[ "$final_rc" == 0 || "$final_rc" == 3 ]] && [[ "$PRESET_RESTORED" == 1 && "$PROVIDER_RESTORED" == 1 && "$CREDENTIAL_SCAN_CLEAN" == 1 ]]; then
        infra=pass
    else
        infra=fail
    fi
    jq -n \
        --arg candidate "$CANDIDATE" --arg path owui --argjson rounds "$ROUNDS" \
        --arg quality "$quality" --arg infrastructure "$infra" \
        --argjson quality_rc "$QUALITY_RC" --argjson final_rc "$final_rc" \
        --argjson request_failures "$REQUEST_FAILURES" \
        --argjson preset_restored "$PRESET_RESTORED" \
        --argjson provider_config_restored "$PROVIDER_RESTORED" \
        --argjson credential_scan_clean "$CREDENTIAL_SCAN_CLEAN" \
        --argjson serious_warning_count "$SERIOUS_WARNING_COUNT" \
        --arg effective_base "$CANDIDATE_BASE_ID" \
        '{candidate:$candidate,path:$path,rounds:$rounds,quality_result:$quality,infrastructure_result:$infrastructure,quality_rc:$quality_rc,final_rc:$final_rc,request_failures:$request_failures,preset_restored:($preset_restored==1),provider_config_restored:($provider_config_restored==1),credential_scan_clean:($credential_scan_clean==1),serious_warning_count:$serious_warning_count,effective_base_model_id:$effective_base}' \
        > "$OUT/run-manifest.json"
}

finalize() {
    local rc=$? preset_restore_rc=0 ollama_restore_rc=0
    trap - EXIT
    set +e
    if [[ -n "$TELEMETRY_STOP" ]]; then touch "$TELEMETRY_STOP" 2>/dev/null || true; fi
    if [[ -n "$TELEMETRY_PID" ]]; then wait "$TELEMETRY_PID" 2>/dev/null || true; fi
    TELEMETRY_PID=''; TELEMETRY_STOP=''
    printf '%s\n' "$rc" > "$OUT/post/test-script-rc.txt"

    if ! restore_original_preset; then
        printf '%s\n' 'ERROR: preset restoration failed.' >&2
        preset_restore_rc=1
        rc=23
    else
        PRESET_RESTORED=1
    fi
    if ! restore_original_ollama_config; then
        printf '%s\n' 'ERROR: Ollama provider config restoration failed.' >&2
        ollama_restore_rc=1
        rc=25
    else
        PROVIDER_RESTORED=1
    fi

    {
        [[ "$preset_restore_rc" == 0 ]] && echo 'Preset restoration verified.' || echo 'ERROR: preset restoration failed.'
        [[ "$ollama_restore_rc" == 0 ]] && echo 'Ollama provider config restoration verified.' || echo 'ERROR: Ollama provider config restoration failed.'
    } > "$OUT/post/restoration-status.txt"

    unload_main >/dev/null 2>&1 || true
    capture_state "$OUT/post/state-after" || true
    journalctl -b --since "$START_ISO" --no-pager -u ollama.service -u open-webui.service > "$OUT/post/service-journal.txt" 2>&1 || true
    journalctl -k -b --since "$START_ISO" --no-pager > "$OUT/post/kernel-journal.txt" 2>&1 || true
    grep -Ein 'out of memory|oom-kill|oom_reaper|killed process|device lost|gpu reset|amdgpu.*(reset|timeout|fault)|ring.*(timeout|reset|fault|error)' \
        "$OUT/post/service-journal.txt" "$OUT/post/kernel-journal.txt" > "$OUT/post/serious-warnings.txt" 2>/dev/null || true
    SERIOUS_WARNING_COUNT="$(wc -l < "$OUT/post/serious-warnings.txt" | tr -d ' ')"
    if [[ -x "$OUT/setup/evaluate.py" ]]; then
        python3 "$OUT/setup/evaluate.py" --benchmark "$BENCH" --fixture "$FIXTURE" --root "$OUT" --model "$CANDIDATE" > "$OUT/aggregate.txt" 2>&1 || true
    else
        printf '%s\n' 'Evaluation did not start.' > "$OUT/aggregate.txt"
    fi
    local archive_ok=1 cleanup_rc=0
    if ! credential_scan > "$OUT/post/credential-scan.txt" 2>&1; then
        cat "$OUT/post/credential-scan.txt" >&2
        rc=24
        archive_ok=0
    else
        CREDENTIAL_SCAN_CLEAN=1
    fi
    if [[ -n "$HEADER_FILE" ]]; then sudo rm -f "$HEADER_FILE" || true; HEADER_FILE=''; fi
    cleanup_root_tempfiles || cleanup_rc=$?
    if [[ "$cleanup_rc" != 0 ]]; then
        echo 'ERROR: one or more root-only Open WebUI temporary files could not be removed.' >&2
        rc=26
        archive_ok=0
    fi
    write_run_manifest "$rc"
    printf '%s\n' "$(date --iso-8601=seconds)" > "$OUT/post/end-time.txt"
    local parent name tarball
    parent="$(dirname "$OUT")"; name="$(basename "$OUT")"; tarball="$HOME/${name}.tar.gz"
    printf '\n=== OWUI translation candidate summary ===\n'; cat "$OUT/aggregate.txt" 2>/dev/null || true
    if [[ "$archive_ok" == 1 ]]; then
        tar -C "$parent" -czf "$tarball" "$name"; sha256sum "$tarball" > "$tarball.sha256"
        printf 'Evidence: %s\nTarball: %s\n' "$OUT" "$tarball"; cat "$tarball.sha256"
    else
        printf 'Evidence: %s\nTarball: WITHHELD because credential/root-temp safety checks failed.\n' "$OUT" >&2
    fi
    [[ "$preset_restore_rc" == 0 ]] || printf '\nCRITICAL: preset restoration FAILED.\n' >&2
    [[ "$ollama_restore_rc" == 0 ]] || printf '\nCRITICAL: Ollama provider config restoration FAILED.\n' >&2
    exit "$rc"
}
trap finalize EXIT

systemctl is-active --quiet ollama.service || { echo 'ERROR: ollama.service inactive.' >&2; exit 1; }
systemctl is-active --quiet open-webui.service || { echo 'ERROR: open-webui.service inactive.' >&2; exit 1; }
capture_state "$OUT/setup/state-before"
cp "$FIXTURE" "$OUT/setup/translation-office.json"

owui_request 'capture-original-presets' GET '/api/v1/models/export' '' \
    "$OUT/setup/original-models-export.json" "$OUT/setup/original-models-export.http.json" || exit 20
jq --arg id "$PRESET" '.[] | select(.id == $id)' \
    "$OUT/setup/original-models-export.json" > "$OUT/setup/original-preset.json"
jq -e --arg id "$PRESET" '.id == $id' "$OUT/setup/original-preset.json" >/dev/null || {
    echo 'ERROR: translation preset not found.' >&2
    exit 1
}
ORIGINAL_SAVED=1
save_original_ollama_config || exit 20

if [[ "$INSTALL_EXPERIMENT" == 1 ]]; then
    sudo bc250-model install experiments "$CANDIDATE" 2>&1 | tee "$OUT/setup/candidate-install.txt"
    prepare_candidate_provider || exit 20
else
    printf 'production reference: using existing registered model %s\n' "$CANDIDATE" | tee "$OUT/setup/candidate-install.txt"
fi
capture_provenance

SYSTEM_PROMPT="$(cat "$PROMPT_FILE")"
jq --arg base "$CANDIDATE_BASE_ID" --arg system "$SYSTEM_PROMPT" '
  .base_model_id=$base | .params=((.params // {}) + {system:$system}) | del(.params.temperature)
' "$OUT/setup/original-preset.json" > "$OUT/setup/candidate-preset.json"
jq -n --slurpfile model "$OUT/setup/candidate-preset.json" '{models:[$model[0]]}' > "$OUT/setup/candidate-import.json"
owui_request 'import-candidate-preset' POST '/api/v1/models/import' "$OUT/setup/candidate-import.json" \
    "$OUT/setup/candidate-import-response.json" "$OUT/setup/candidate-import-response.http.json" || exit 20
owui_request 'models-after-preset-import' GET '/api/models?refresh=true' '' \
    "$OUT/setup/models-after-preset-import.json" "$OUT/setup/models-after-preset-import.http.json" || exit 20
jq -e --arg id "$CANDIDATE_BASE_ID" '.data[]? | select(.id == $id)' \
    "$OUT/setup/models-after-preset-import.json" > "$OUT/setup/effective-candidate-base-model.json" || {
    printf 'ERROR: effective model list does not contain candidate base model: %s\n' "$CANDIDATE_BASE_ID" >&2
    exit 20
}
jq -e --arg id "$PRESET" --arg base "$CANDIDATE_BASE_ID" \
    '.data[]? | select(.id == $id and .info.base_model_id == $base)' \
    "$OUT/setup/models-after-preset-import.json" > "$OUT/setup/effective-candidate-preset.json" || {
    printf 'ERROR: effective model list does not contain candidate translation preset/base mapping.\n' >&2
    exit 20
}
owui_request 'readback-candidate-presets' GET '/api/v1/models/export' '' \
    "$OUT/setup/live-models-export.json" "$OUT/setup/live-models-export.http.json" || exit 20
jq --arg id "$PRESET" '.[] | select(.id == $id)' \
    "$OUT/setup/live-models-export.json" > "$OUT/setup/live-candidate-preset.json"
python3 - "$OUT/setup/original-preset.json" "$OUT/setup/live-candidate-preset.json" "$CANDIDATE_BASE_ID" "$SYSTEM_PROMPT" <<'PYPRESET'
import copy,json,sys
with open(sys.argv[1],encoding='utf-8') as f: original=json.load(f)
with open(sys.argv[2],encoding='utf-8') as f: live=json.load(f)
expected=copy.deepcopy(original); expected['base_model_id']=sys.argv[3]; expected['params']=dict(expected.get('params') or {}); expected['params']['system']=sys.argv[4]; expected['params'].pop('temperature',None)
def stable(x): return {k:x.get(k) for k in ('id','base_model_id','name','params','meta','is_active','access_grants')}
if stable(expected)!=stable(live): raise SystemExit('selected stable live preset fields differ outside the intended candidate delta')
print('Live candidate preset verified.')
PYPRESET
write_evaluator
write_telemetry_helper

for n in $(seq 1 "$ROUNDS"); do
    printf '\n===== OWUI candidate %s / round %s =====\n' "$CANDIDATE" "$n"
    RUN="$OUT/runs/$n"; mkdir -p "$RUN"/{payloads,raw,telemetry,timing,http}; unload_main
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
        http_meta="$RUN/http/${case_id}.json"
        set +e
        owui_request "chat-round-${n}-${case_id}" POST '/api/chat/completions' "$payload" "$raw" "$http_meta"
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
        if [[ "$request_rc" != 0 ]]; then
            curl_rc="$(jq -r '.curl_rc' "$http_meta")"
            http_code="$(jq -r '.http_status' "$http_meta")"
            printf 'ERROR: OWUI request failed: round=%s case=%s curl_rc=%s http=%s\n' "$n" "$case_id" "$curl_rc" "$http_code" >&2
            if [[ -s "$raw" ]]; then
                printf '%s\n' '--- Open WebUI error response ---' >&2
                jq . "$raw" >&2 2>/dev/null || cat "$raw" >&2
            fi
            exit 20
        fi
        jq . "$raw" > "$raw.pretty" && mv -f "$raw.pretty" "$raw"
        jq -e '.choices | type=="array" and length>0 and .[0].message.content != null' "$raw" >/dev/null || { printf 'ERROR: malformed OWUI response: round=%s case=%s\n' "$n" "$case_id" >&2; exit 21; }
    done < <(jq -r '.[] | [.id,.input] | @tsv' "$FIXTURE")
    unload_main
done
set +e
python3 "$OUT/setup/evaluate.py" --benchmark "$BENCH" --fixture "$FIXTURE" --root "$OUT" --model "$CANDIDATE" > "$OUT/aggregate.txt"
eval_rc=$?
QUALITY_RC="$eval_rc"
set -e
cat "$OUT/aggregate.txt"
[[ "$eval_rc" == 0 || "$eval_rc" == 3 ]] || exit "$eval_rc"
[[ "$eval_rc" == 0 ]] || exit 3
