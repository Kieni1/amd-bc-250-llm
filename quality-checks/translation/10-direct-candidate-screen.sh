#!/usr/bin/env bash
# Direct translation screen for one packaged experimental model. This uses the
# installed benchmark's explicit source/target direction and does not mutate OWUI.
set -Eeuo pipefail
umask 077

CANDIDATE="${1:-}"
ROUNDS="${2:-${BC250_SCREEN_ROUNDS:-3}}"
MAIN_URL='http://127.0.0.1:11434'
MAIN_HOST='127.0.0.1:11434'

[[ -n "$CANDIDATE" ]] || { echo "usage: $0 EXPERIMENT-MODEL [ROUNDS]" >&2; exit 2; }
[[ "$CANDIDATE" == exp-* ]] || { echo 'ERROR: candidate must be a packaged exp-* model.' >&2; exit 2; }
[[ "$ROUNDS" =~ ^[1-9][0-9]*$ ]] || { echo 'ERROR: rounds must be a positive integer.' >&2; exit 2; }

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="${BC250_QUALITY_ROOT:-$HOME/bc250-quality}"
SAFE_NAME="${CANDIDATE//[^a-zA-Z0-9._-]/_}"
OUT="$ROOT/translation-direct-${SAFE_NAME}-${STAMP}"
START_ISO="$(date --iso-8601=seconds)"
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
    unload_main
}

write_aggregate() {
    python3 - "$OUT" <<'PY' > "$OUT/aggregate.txt"
import json, pathlib, sys
from collections import Counter, defaultdict
root=pathlib.Path(sys.argv[1]); rows=[]
for p in sorted((root/'runs').glob('*/results.jsonl')):
    for line in p.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        r=json.loads(line)
        if r.get('result_type')=='qualification': rows.append(r)
passed=sum(r.get('outcome')=='pass' for r in rows)
failures=Counter(x for r in rows for x in r.get('failure_kinds',[]))
budget=sum('output-budget' in r.get('diagnostics',[]) for r in rows)
print(f"OVERALL: {passed}/{len(rows)}")
print('FAILURES:', dict(failures) or '-')
print('OUTPUT-BUDGET DIAGNOSTICS:', budget)
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
    print(f"\n[{r['case_id']}] fail={','.join(r.get('failure_kinds',[])) or '-'} diag={','.join(r.get('diagnostics',[])) or '-'}")
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
    write_aggregate || true
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
sudo bc250-model install experiments "$CANDIDATE" 2>&1 | tee "$OUT/setup/candidate-install.txt"
model_present || { echo 'ERROR: candidate is not registered on main Ollama.' >&2; exit 1; }
for n in $(seq 1 "$ROUNDS"); do run_round "$n"; done
write_aggregate
