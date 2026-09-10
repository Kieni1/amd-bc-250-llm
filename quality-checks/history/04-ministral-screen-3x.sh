#!/usr/bin/env bash
# Queued screening batch: Ministral 3 8B translation challenger, 3 rounds only.
# Purpose: obtain a cheap comparison point before spending time on new candidates.
# This is NOT a production promotion script and does not modify package source.
# It temporarily repoints the existing OWUI translation preset and restores it.
set -Eeuo pipefail
umask 077

CANDIDATE='exp-ministral3-8b-unsloth-ud-q5-k-xl'
PRESET='bc250-office-translation'
MAIN_URL='http://127.0.0.1:11434'
MAIN_HOST='127.0.0.1:11434'
OWUI_URL='http://127.0.0.1:3000'
TOKEN_FILE="${BC250_OWUI_TOKEN_FILE:-/root/owui-test.key}"
FIXTURE='/usr/share/bc250-llm-server/benchmark/translation-office.json'
BENCH='/usr/libexec/bc250-llm-server/category-benchmark.py'
ROUNDS="${BC250_SCREEN_ROUNDS:-3}"
STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="${BC250_QUALITY_ROOT:-$HOME/bc250-quality}"
OUT="$ROOT/batch4-ministral-screen-$STAMP"
HEADER_FILE=''
ORIGINAL_SAVED=0
START_ISO="$(date --iso-8601=seconds)"

mkdir -p "$OUT"/{setup,runs,post}
printf '%s\n' "$START_ISO" > "$OUT/setup/start-time.txt"
cp "$0" "$OUT/04-ministral-screen-3x.sh" 2>/dev/null || true

need() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'ERROR: required command unavailable: %s\n' "$1" >&2
        exit 1
    }
}

for cmd in bc250-model curl jq ollama python3 rpm systemctl journalctl free tar sha256sum; do
    need "$cmd"
done

sudo -v
sudo test -r "$TOKEN_FILE" && sudo test -s "$TOKEN_FILE" || {
    printf 'ERROR: OWUI token file unavailable: %s\n' "$TOKEN_FILE" >&2
    exit 1
}

# Keep the bearer token in /run, never inside the evidence directory.
HEADER_FILE="$(sudo mktemp /run/bc250-owui-header.XXXXXX)"
sudo chmod 600 "$HEADER_FILE"
sudo bash -c '
    set -euo pipefail
    token="$(<"$1")"
    printf "Authorization: Bearer %s\n" "$token" > "$2"
' bash "$TOKEN_FILE" "$HEADER_FILE"

owui_get() {
    sudo curl -fsS --connect-timeout 10 --max-time 900 \
        -H @"$HEADER_FILE" "$OWUI_URL$1"
}

owui_post_file() {
    sudo curl -fsS --connect-timeout 10 --max-time 900 \
        -H @"$HEADER_FILE" -H 'Content-Type: application/json' \
        --data-binary @"$2" "$OWUI_URL$1"
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
    free -h > "$dest/free-h.txt"
    cat /proc/meminfo > "$dest/meminfo.txt"
    cat /proc/swaps > "$dest/swaps.txt"
    curl -fsS "$MAIN_URL/api/ps" | jq . > "$dest/main-ps.json"
}

restore_original_preset() {
    [[ "$ORIGINAL_SAVED" == 1 ]] || return 0
    jq -n --slurpfile model "$OUT/setup/original-preset.json" \
        '{models: [$model[0]]}' > "$OUT/post/restore-payload.json"
    owui_post_file '/api/v1/models/import' "$OUT/post/restore-payload.json" \
        > "$OUT/post/restore-response.json"
    owui_get '/api/v1/models/export' | jq --arg id "$PRESET" \
        '.[] | select(.id == $id)' > "$OUT/post/restored-preset.json"
    python3 - "$OUT/setup/original-preset.json" "$OUT/post/restored-preset.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as f: a=json.load(f)
with open(sys.argv[2], encoding='utf-8') as f: b=json.load(f)
def stable(x):
    return {k:x.get(k) for k in ('id','base_model_id','name','params','meta','is_active','access_grants')}
if stable(a) != stable(b):
    raise SystemExit('ERROR: restored preset differs from original')
print('Preset restoration verified.')
PY
    printf '%s\n' 'Preset restoration verified.' > "$OUT/post/restoration-status.txt"
}

# Evaluate candidate outputs with the package's existing translation semantics.
cat > "$OUT/setup/evaluate.py" <<'PY'
#!/usr/bin/env python3
import importlib.util, json, pathlib, sys
from collections import Counter, defaultdict
root=pathlib.Path(sys.argv[1]); bench_path=pathlib.Path(sys.argv[2]); fixture=pathlib.Path(sys.argv[3])
sys.path.insert(0, str(bench_path.parent))
spec=importlib.util.spec_from_file_location('bc250_category_benchmark', bench_path)
mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
cases={c['id']:c for c in json.loads(fixture.read_text(encoding='utf-8'))}
rows=[]
for rd in sorted((root/'runs').glob('*'), key=lambda p:int(p.name) if p.name.isdigit() else 9999):
    if not rd.is_dir() or not rd.name.isdigit(): continue
    for raw in sorted((rd/'raw').glob('*.response.json')):
        cid=raw.name.removesuffix('.response.json'); case=cases[cid]
        obj=json.loads(raw.read_text(encoding='utf-8'))
        choices=obj.get('choices') or []
        msg=(choices[0].get('message') or {}) if choices else {}
        content=str(msg.get('content') or '')
        req, forb, pres, meaningful=mod.translation_content_checks(content, case)
        lang=mod.task_language_hint(content, case['target_language']) == 'match'
        sem=req and meaningful
        ok=bool(content.strip()) and lang and sem and forb and pres
        fails=mod.translation_failure_kinds(content, language_ok=lang, source_leakage_ok=forb,
                                            semantic_ok=sem, preserved_ok=pres)
        rows.append({'round':int(rd.name),'case_id':cid,'outcome':'pass' if ok else 'quality-fail',
                     'failure_kinds':fails,'response':content})
(root/'results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows),encoding='utf-8')
passed=sum(r['outcome']=='pass' for r in rows)
print(f'MINISTRAL SCREEN: {passed}/{len(rows)}')
print('LFM BEST REFERENCE (Batch 3B): 69/80 = 86.25%')
print(f'MINISTRAL SCREEN RATE: {passed/len(rows):.2%}' if rows else 'MINISTRAL SCREEN RATE: n/a')
print('\nPER CASE')
by=defaultdict(list)
for r in rows: by[r['case_id']].append(r)
for cid in sorted(by):
    p=sum(r['outcome']=='pass' for r in by[cid])
    print(f'{cid}: {p}/{len(by[cid])}')
fc=Counter(f for r in rows for f in r['failure_kinds'])
print('\nFAILURES:', ', '.join(f'{k}={v}' for k,v in sorted(fc.items())) or '-')
print('\nFAILED RESPONSES')
for r in rows:
    if r['outcome']=='pass': continue
    print(f"\nround={r['round']} case={r['case_id']} fail={','.join(r['failure_kinds']) or '-'}")
    print(r['response'])
PY
chmod 700 "$OUT/setup/evaluate.py"
python3 -m py_compile "$OUT/setup/evaluate.py"

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
if hits: raise SystemExit('ERROR: token leaked into evidence: '+', '.join(hits))
print('credential scan: Open WebUI token not present in evidence')
PY
}

finalize() {
    local rc=$?
    trap - EXIT
    set +e
    printf '%s\n' "$rc" > "$OUT/post/test-script-rc.txt"
    if ! restore_original_preset; then
        printf '%s\n' 'ERROR: preset restoration failed.' > "$OUT/post/restoration-status.txt"
        rc=23
    fi
    unload_main >/dev/null 2>&1 || true
    capture_state "$OUT/post/state-after" 2>/dev/null || true
    journalctl -b --since "$START_ISO" --no-pager -u ollama.service -u open-webui.service \
        > "$OUT/post/service-journal.txt" 2>&1 || true
    journalctl -k -b --since "$START_ISO" --no-pager > "$OUT/post/kernel-journal.txt" 2>&1 || true
    grep -Ein 'out of memory|oom-kill|oom_reaper|killed process|device lost|gpu reset|amdgpu.*(reset|timeout|fault)|ring.*(timeout|reset|fault|error)' \
        "$OUT/post/service-journal.txt" "$OUT/post/kernel-journal.txt" \
        > "$OUT/post/serious-warnings.txt" 2>/dev/null || true
    python3 "$OUT/setup/evaluate.py" "$OUT" "$BENCH" "$FIXTURE" > "$OUT/aggregate.txt" 2>&1 || true
    if [[ -n "$HEADER_FILE" ]]; then sudo rm -f "$HEADER_FILE" || true; HEADER_FILE=''; fi
    if ! credential_scan > "$OUT/post/credential-scan.txt" 2>&1; then rc=24; fi
    local parent name tarball
    parent="$(dirname "$OUT")"; name="$(basename "$OUT")"; tarball="$HOME/${name}.tar.gz"
    tar -C "$parent" -czf "$tarball" "$name"
    sha256sum "$tarball" > "$tarball.sha256"
    printf '\nEvidence directory: %s\nTarball: %s\n' "$OUT" "$tarball"
    cat "$OUT/aggregate.txt" 2>/dev/null || true
    cat "$tarball.sha256"
    exit "$rc"
}
trap finalize EXIT

systemctl is-active --quiet ollama.service || { echo 'ERROR: ollama.service inactive' >&2; exit 1; }
systemctl is-active --quiet open-webui.service || { echo 'ERROR: open-webui.service inactive' >&2; exit 1; }
[[ -r "$FIXTURE" && -r "$BENCH" ]] || { echo 'ERROR: benchmark/fixture unavailable' >&2; exit 1; }

capture_state "$OUT/setup/state-before"
sha256sum "$FIXTURE" "$BENCH" > "$OUT/setup/benchmark-contract.sha256"
cp "$FIXTURE" "$OUT/setup/translation-office.json"

owui_get '/api/v1/models/export' | jq --arg id "$PRESET" '.[] | select(.id == $id)' \
    > "$OUT/setup/original-preset.json"
jq -e --arg id "$PRESET" '.id == $id' "$OUT/setup/original-preset.json" >/dev/null || {
    echo 'ERROR: translation preset not found' >&2; exit 1;
}
ORIGINAL_SAVED=1

# Reuse the already-packaged experiment; no new external model is introduced here.
sudo bc250-model install experiments "$CANDIDATE" 2>&1 | tee "$OUT/setup/model-install.txt"
curl -fsS "$MAIN_URL/api/tags" | jq -e --arg m "$CANDIDATE" \
    '.models | any(((.name // .model // "") | sub(":latest$"; "")) == $m)' >/dev/null || {
    echo 'ERROR: Ministral candidate not registered on main Ollama' >&2; exit 1;
}

cat > "$OUT/setup/candidate-system.txt" <<'EOF'
You are a dedicated professional German↔French translator for office and business documents.

First determine whether the source text is German or French before generating the translation.
When the user provides German text without another explicit task, translate it into French.
When the user provides French text without another explicit task, translate it into German.
A German source must produce French output. A French source must produce German output.

If the user explicitly requests a target language or a different translation direction, follow it.
For English input, do not guess a translation direction unless the target language is stated.

Translate directly and completely. Translate every ordinary-language source word; leave untranslated only names, identifiers, reference numbers, amounts, and dates. Preserve meaning, tone, register, terminology, negations, qualifications, lists, tables and formatting.

Do not summarize, explain, compare or add commentary unless the user explicitly requests it. Do not invent facts absent from the source.
Return only the translation unless the user asks for explanation or alternatives.
EOF
SYSTEM_PROMPT="$(cat "$OUT/setup/candidate-system.txt")"

# Change only the preset's base model + system prompt. Do not override Ministral sampling.
jq --arg base "${CANDIDATE}:latest" --arg system "$SYSTEM_PROMPT" '
    .base_model_id=$base |
    .params=((.params // {}) + {system:$system}) |
    del(.params.temperature)
' "$OUT/setup/original-preset.json" > "$OUT/setup/candidate-preset.json"
jq -n --slurpfile model "$OUT/setup/candidate-preset.json" '{models:[$model[0]]}' \
    > "$OUT/setup/candidate-import.json"
owui_post_file '/api/v1/models/import' "$OUT/setup/candidate-import.json" \
    > "$OUT/setup/candidate-import-response.json"

for n in $(seq 1 "$ROUNDS"); do
    printf '\n===== Ministral screen round %s/%s =====\n' "$n" "$ROUNDS"
    RUN="$OUT/runs/$n"; mkdir -p "$RUN"/{payloads,raw}
    unload_main
    while IFS=$'\t' read -r case_id text; do
        payload="$RUN/payloads/${case_id}.json"; raw="$RUN/raw/${case_id}.response.json"
        jq -n --arg model "$PRESET" --arg text "$text" '{model:$model,messages:[{role:"user",content:$text}],stream:false,background_tasks:{title_generation:false,tags_generation:false,follow_up_generation:false}}' \
            > "$payload"
        owui_post_file '/api/chat/completions' "$payload" | jq . > "$raw" || {
            printf 'ERROR: OWUI request failed round=%s case=%s\n' "$n" "$case_id" >&2; exit 20;
        }
        jq -e '.choices|type=="array" and length>0 and .[0].message.content != null' "$raw" >/dev/null || {
            printf 'ERROR: malformed response round=%s case=%s\n' "$n" "$case_id" >&2; exit 21;
        }
    done < <(jq -r '.[] | [.id,.input] | @tsv' "$FIXTURE")
    unload_main
done

python3 "$OUT/setup/evaluate.py" "$OUT" "$BENCH" "$FIXTURE" > "$OUT/aggregate.txt"
cat "$OUT/aggregate.txt"
