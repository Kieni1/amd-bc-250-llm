#!/usr/bin/env bash
# Fully automated BC-250 main-model screen against production GPT-OSS.
#
# Intended to run on the real appliance after these four experimental Modelfiles
# are installed by the package. It downloads/registers one candidate at a time,
# runs the package-owned generation compare + edge profiles, unloads all normal
# lanes between runs, records journal/resource evidence, and removes only
# registrations created by this script. By default candidate GGUF source files
# are retained for cheap follow-up testing.
#
# Environment knobs:
#   BC250_QUALITY_ROOT=$HOME/bc250-quality
#   BC250_KEEP_GGUF=1          # 1 keeps downloaded candidate GGUFs after each run
#   BC250_RUN_EDGE=1           # 0 skips the memory-edge profile
#   BC250_REQUEST_TIMEOUT=1200 # seconds per Ollama request
#
# No Open WebUI state is changed. Task/embedding services remain running, but any
# resident models on those lanes are unloaded before each main-model benchmark.
set -Eeuo pipefail
umask 077

BASELINE='prod-gpt-oss20b-ggml-org-mxfp4'
CANDIDATES=(
  'exp-qwen36-35b-a3b-unsloth-ud-iq3-s'
  'exp-qwen38-27b-ista-gsq-rco-iq3-s'
  'exp-gemma4-26b-a4b-mradermacher-i1-iq3-s'
  'exp-qwen38-27b-unsloth-ud-iq3-s'
)

MAIN_URL='http://127.0.0.1:11434'
TASK_URL='http://127.0.0.1:11435'
EMBED_URL='http://127.0.0.1:11437'
MAIN_HOST='127.0.0.1:11434'
TASK_HOST='127.0.0.1:11435'
EMBED_HOST='127.0.0.1:11437'
KEEP_GGUF="${BC250_KEEP_GGUF:-1}"
RUN_EDGE="${BC250_RUN_EDGE:-1}"
REQUEST_TIMEOUT="${BC250_REQUEST_TIMEOUT:-1200}"

[[ "$KEEP_GGUF" == 0 || "$KEEP_GGUF" == 1 ]] || {
    echo 'ERROR: BC250_KEEP_GGUF must be 0 or 1.' >&2
    exit 2
}
[[ "$RUN_EDGE" == 0 || "$RUN_EDGE" == 1 ]] || {
    echo 'ERROR: BC250_RUN_EDGE must be 0 or 1.' >&2
    exit 2
}
[[ "$REQUEST_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || {
    echo 'ERROR: BC250_REQUEST_TIMEOUT must be a positive integer.' >&2
    exit 2
}

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

if systemctl is-active --quiet ollama-agent.service; then
    echo 'ERROR: ollama-agent.service is active. Leave agent mode before running this matrix.' >&2
    exit 1
fi
for svc in ollama.service ollama-task.service ollama-embedding.service; do
    systemctl is-active --quiet "$svc" || {
        printf 'ERROR: required normal-mode service is inactive: %s\n' "$svc" >&2
        exit 1
    }
done

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="${BC250_QUALITY_ROOT:-$HOME/bc250-quality}"
OUT="$ROOT/main-model-matrix-$STAMP"
mkdir -p "$OUT"/{setup,runs,status,journal,post}
printf '%s\n' "$(date --iso-8601=seconds)" > "$OUT/setup/start-time.txt"
printf '%s\n' "$BASELINE" > "$OUT/setup/baseline.txt"
printf '%s\n' "${CANDIDATES[@]}" | tr ' ' '\n' > "$OUT/setup/candidates.txt"
printf 'keep_gguf=%s\nrun_edge=%s\nrequest_timeout=%s\n' \
    "$KEEP_GGUF" "$RUN_EDGE" "$REQUEST_TIMEOUT" > "$OUT/setup/options.txt"
cp "$0" "$OUT/setup/$(basename "$0")" 2>/dev/null || true
rpm -q --qf '%{NAME} %{VERSION}-%{RELEASE} %{ARCH}\n' bc250-llm-server \
    > "$OUT/setup/package.txt"
curl -fsS "$MAIN_URL/api/version" | jq . > "$OUT/setup/ollama-version.json"

OLLAMA_BIN="$(command -v ollama)"
CREATED=()
declare -A CLEANED=()
FINALIZED=0

model_present() {
    local url="$1" model="$2"
    curl -fsS "$url/api/tags" | jq -e --arg model "$model" '
      .models | any(((.name // .model // "") | sub(":latest$"; "")) == $model)
    ' >/dev/null
}

unload_lane() {
    local url="$1" host="$2" model count i
    while IFS= read -r model; do
        [[ -n "$model" ]] || continue
        OLLAMA_HOST="$host" "$OLLAMA_BIN" stop "$model" >/dev/null 2>&1 || true
    done < <(curl -fsS "$url/api/ps" | jq -r '.models[]? | (.name // .model // empty)')
    for i in $(seq 1 30); do
        count="$(curl -fsS "$url/api/ps" | jq '.models | length')"
        [[ "$count" == 0 ]] && return 0
        sleep 1
    done
    printf 'ERROR: models remained resident on %s\n' "$url" >&2
    return 1
}

unload_normal_lanes() {
    unload_lane "$MAIN_URL" "$MAIN_HOST"
    unload_lane "$TASK_URL" "$TASK_HOST"
    unload_lane "$EMBED_URL" "$EMBED_HOST"
}

restore_normal_services() {
    sudo systemctl start ollama.service ollama-task.service ollama-embedding.service
    if systemctl is-active --quiet ollama-agent.service; then
        echo 'WARNING: agent service became active unexpectedly; refusing to stop it automatically.' >&2
        return 1
    fi
    for svc in ollama.service ollama-task.service ollama-embedding.service; do
        systemctl is-active --quiet "$svc" || return 1
    done
}

capture_state() {
    local dest="$1"
    mkdir -p "$dest"
    date --iso-8601=seconds > "$dest/time.txt"
    cat /proc/meminfo > "$dest/meminfo.txt"
    cat /proc/swaps > "$dest/swaps.txt"
    systemctl is-active ollama.service ollama-task.service ollama-embedding.service ollama-agent.service \
        > "$dest/services-active.txt" 2>&1 || true
    curl -fsS "$MAIN_URL/api/ps" | jq . > "$dest/main-ps.json" 2>/dev/null || true
    curl -fsS "$TASK_URL/api/ps" | jq . > "$dest/task-ps.json" 2>/dev/null || true
    curl -fsS "$EMBED_URL/api/ps" | jq . > "$dest/embedding-ps.json" 2>/dev/null || true
}

install_candidate() {
    local model="$1"
    if model_present "$MAIN_URL" "$model"; then
        printf 'Candidate already registered; leaving it installed after the matrix: %s\n' "$model"
        return 0
    fi
    printf '\n=== install %s ===\n' "$model"
    sudo env BC250_HF_ANONYMOUS=1 bc250-model install experiments "$model" \
        2>&1 | tee "$OUT/setup/${model}.install.txt"
    model_present "$MAIN_URL" "$model" || {
        printf 'ERROR: candidate did not appear after installation: %s\n' "$model" >&2
        return 1
    }
    CREATED+=("$model")
}

cleanup_candidate() {
    local model="$1" created=0 item
    for item in "${CREATED[@]:-}"; do
        [[ "$item" == "$model" ]] && created=1
    done
    [[ "$created" == 1 ]] || return 0

    unload_normal_lanes || true
    if [[ "$KEEP_GGUF" == 1 ]]; then
        sudo bc250-model cleanup experiments "$model" --keep-gguf --yes
    else
        sudo bc250-model cleanup experiments "$model" --yes
    fi
    CLEANED["$model"]=1
}

run_generation() {
    local label="$1" model="$2" profile="$3"
    local dir="$OUT/runs/${label}-${profile}" rc start
    start="$(date --iso-8601=seconds)"
    printf '\n===== %s | %s | profile=%s =====\n' "$label" "$model" "$profile"

    restore_normal_services || true
    unload_normal_lanes
    set +e
    env \
        REQUEST_TIMEOUT="$REQUEST_TIMEOUT" \
        KEEP_ALIVE='10m' \
        BOARD_NOTE='BC-250 main-model candidate matrix; task/embedding services active, resident companion models unloaded' \
        bc250-benchmark generation \
            --profile "$profile" \
            --mode neutral \
            --think omit \
            --output-dir "$dir" \
            "$model" \
        2>&1 | tee "$OUT/runs/${label}-${profile}.console.txt"
    rc="${PIPESTATUS[0]}"
    set -e
    printf '%s\n' "$rc" > "$OUT/status/${label}-${profile}.rc"

    journalctl --since "$start" --no-pager -u ollama.service \
        > "$OUT/journal/${label}-${profile}.ollama.log" 2>&1 || true
    journalctl --since "$start" --no-pager -k \
        > "$OUT/journal/${label}-${profile}.kernel.log" 2>&1 || true
    grep -Eai 'oom|out of memory|killed process|device lost|error.*device|radv|amdgpu.*(fault|reset|error)|ring.*timeout' \
        "$OUT/journal/${label}-${profile}.ollama.log" \
        "$OUT/journal/${label}-${profile}.kernel.log" \
        > "$OUT/journal/${label}-${profile}.warnings.txt" || true

    unload_normal_lanes || true
    if [[ "$rc" != 0 ]]; then
        printf 'WARNING: %s/%s exited rc=%s; continuing matrix after service recovery.\n' \
            "$label" "$profile" "$rc" >&2
        restore_normal_services || true
        unload_normal_lanes || true
    fi
    return 0
}

write_aggregate() {
    python3 - "$OUT" <<'PY'
import csv
import pathlib
import statistics
import sys

root = pathlib.Path(sys.argv[1])
status = root / "status"
rows = []

for csv_path in sorted((root / "runs").glob("*/results.csv")):
    label_profile = csv_path.parent.name
    if label_profile.endswith("-compare"):
        label = label_profile[:-8]
        profile = "compare"
    elif label_profile.endswith("-edge"):
        label = label_profile[:-5]
        profile = "edge"
    else:
        continue
    data = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    if not data:
        continue
    model = data[0].get("model", "")

    def nums(field, test=None):
        out = []
        for row in data:
            if test is not None and row.get("test") != test:
                continue
            value = row.get(field, "")
            try:
                out.append(float(value))
            except (TypeError, ValueError):
                pass
        return out

    def mean(field, test=None):
        xs = nums(field, test)
        return statistics.fmean(xs) if xs else None

    def maxv(field):
        xs = nums(field)
        return max(xs) if xs else None

    def minv(field):
        xs = nums(field)
        return min(xs) if xs else None

    rc_path = status / f"{label_profile}.rc"
    rc = rc_path.read_text().strip() if rc_path.exists() else "?"
    resident = maxv("resident_size_bytes")
    rows.append({
        "label": label,
        "profile": profile,
        "model": model,
        "rc": rc,
        "cold_load_s": mean("load_duration_s", "cold_chat"),
        "warm_chat_wall_s": mean("wall_duration_s", "warm_chat"),
        "short_decode_tok_s": mean("tokens_per_second", "short"),
        "prefill_tok_s": mean("prompt_tokens_per_second", "prefill"),
        "resident_gib": resident / (1024 ** 3) if resident is not None else None,
        "mem_available_min_mib": minv("mem_available_min_mib"),
        "swap_used_max_mib": maxv("swap_used_max_mib"),
        "temp_max_c": maxv("temp_max_c"),
    })

fields = [
    "label", "profile", "model", "rc", "cold_load_s", "warm_chat_wall_s",
    "short_decode_tok_s", "prefill_tok_s", "resident_gib",
    "mem_available_min_mib", "swap_used_max_mib", "temp_max_c",
]
out = root / "comparison.tsv"
with out.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            key: (f"{value:.3f}" if isinstance(value, float) else value)
            for key, value in row.items()
        })

print("\n=== comparison.tsv ===")
print(out.read_text(encoding="utf-8"), end="")
PY
}

finalize() {
    local rc="$?" tarball name parent model
    [[ "$FINALIZED" == 0 ]] || exit "$rc"
    FINALIZED=1
    trap - EXIT

    for model in "${CREATED[@]:-}"; do
        [[ "${CLEANED[$model]:-0}" == 1 ]] || cleanup_candidate "$model" || true
    done
    restore_normal_services || true
    unload_normal_lanes || true
    capture_state "$OUT/post/state-after" || true
    date --iso-8601=seconds > "$OUT/post/end-time.txt"
    printf '%s\n' "$rc" > "$OUT/post/script-exit-rc.txt"
    write_aggregate || true

    parent="$(dirname "$OUT")"
    name="$(basename "$OUT")"
    tarball="$HOME/${name}.tar.gz"
    tar -C "$parent" -czf "$tarball" "$name"
    sha256sum "$tarball" > "$tarball.sha256"
    printf '\nEvidence: %s\nTarball: %s\n' "$OUT" "$tarball"
    cat "$tarball.sha256"
    exit "$rc"
}
trap finalize EXIT

capture_state "$OUT/setup/state-before"
model_present "$MAIN_URL" "$BASELINE" || {
    printf 'ERROR: production GPT-OSS baseline is not registered: %s\n' "$BASELINE" >&2
    exit 1
}

# Start and end GPT-OSS references make thermal/runtime drift visible without
# forcing GPT-OSS to remain resident while a 12-14 GB candidate is loaded.
run_generation 'gpt-oss-start' "$BASELINE" compare
if [[ "$RUN_EDGE" == 1 ]]; then
    run_generation 'gpt-oss-start' "$BASELINE" edge
fi

for candidate in "${CANDIDATES[@]}"; do
    install_candidate "$candidate" || {
        printf '1\n' > "$OUT/status/${candidate}-install.rc"
        restore_normal_services || true
        unload_normal_lanes || true
        continue
    }
    printf '0\n' > "$OUT/status/${candidate}-install.rc"
    run_generation "$candidate" "$candidate" compare
    if [[ "$RUN_EDGE" == 1 ]]; then
        run_generation "$candidate" "$candidate" edge
    fi
    cleanup_candidate "$candidate" || true
done

run_generation 'gpt-oss-end' "$BASELINE" compare
if [[ "$RUN_EDGE" == 1 ]]; then
    run_generation 'gpt-oss-end' "$BASELINE" edge
fi

write_aggregate
