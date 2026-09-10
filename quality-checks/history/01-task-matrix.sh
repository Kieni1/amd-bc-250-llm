#!/usr/bin/env bash
# Reusable evidence script: Batch 1 task-model matrix.
# NOTE: the installed category benchmark used KEEP_ALIVE=30m during this run;
# isolation is provided by unload_host() before/after each model run.
# Do not interpret this script as a production task-lane keep_alive=0 test.
# Run on the real BC-250 only; do not use Open WebUI interactively during it.

set -Eeuo pipefail
umask 077

GEMMA='task-gemma3-1b-unsloth-ud-q4-k-xl'
GRANITE='exp-granite42-3b-ibm-q6-k'
QWEN='exp-qwen38-4b-distill-empero-q6-k'

TASK_URL='http://127.0.0.1:11435'
MAIN_URL='http://127.0.0.1:11434'
TASK_HOST='127.0.0.1:11435'
MAIN_HOST='127.0.0.1:11434'

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="${BC250_QUALITY_ROOT:-$HOME/bc250-quality}"
OUT="$ROOT/batch1-task-matrix-$STAMP"

mkdir -p "$OUT"/{setup,runs,post}

SELF_COPY="$OUT/batch1-task-matrix.sh"
cp "$0" "$SELF_COPY" 2>/dev/null || true

START_ISO="$(date --iso-8601=seconds)"
printf '%s\n' "$START_ISO" > "$OUT/setup/start-time.txt"

need() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'ERROR: required command not found: %s\n' "$1" >&2
        exit 1
    }
}

for cmd in \
    bc250-benchmark \
    bc250-model \
    curl \
    jq \
    ollama \
    python3 \
    rpm \
    systemctl \
    journalctl \
    free \
    tar \
    sha256sum
do
    need "$cmd"
done

sudo -v

capture_state() {
    local dest="$1"

    mkdir -p "$dest"

    date --iso-8601=seconds > "$dest/time.txt"
    uname -a > "$dest/uname.txt"

    rpm -q \
        --qf '%{NAME} %{VERSION}-%{RELEASE} %{ARCH}\n' \
        bc250-llm-server \
        > "$dest/package.txt"

    systemctl is-active \
        ollama.service \
        ollama-task.service \
        ollama-embedding.service \
        open-webui.service \
        > "$dest/services-active.txt" 2>&1 || true

    systemctl show \
        ollama.service \
        ollama-task.service \
        -p Id \
        -p ActiveState \
        -p SubState \
        -p MainPID \
        -p Environment \
        > "$dest/ollama-units.txt" 2>&1 || true

    free -h > "$dest/free-h.txt"
    cat /proc/meminfo > "$dest/meminfo.txt"
    cat /proc/swaps > "$dest/swaps.txt"

    curl -fsS "$MAIN_URL/api/version" \
        | jq . \
        > "$dest/main-version.json"

    curl -fsS "$TASK_URL/api/version" \
        | jq . \
        > "$dest/task-version.json"

    curl -fsS "$MAIN_URL/api/tags" \
        | jq . \
        > "$dest/main-tags.json"

    curl -fsS "$TASK_URL/api/tags" \
        | jq . \
        > "$dest/task-tags.json"

    curl -fsS "$MAIN_URL/api/ps" \
        | jq . \
        > "$dest/main-ps.json"

    curl -fsS "$TASK_URL/api/ps" \
        | jq . \
        > "$dest/task-ps.json"
}

model_present() {
    local url="$1"
    local model="$2"

    curl -fsS "$url/api/tags" |
        jq -e \
            --arg model "$model" \
            '
            .models
            | any(
                (
                    (.name // .model // "")
                    | sub(":latest$"; "")
                ) == $model
            )
            ' \
            >/dev/null
}

unload_host() {
    local url="$1"
    local host="$2"
    local names
    local model
    local i
    local count

    names="$(
        curl -fsS "$url/api/ps" |
            jq -r '.models[]? | (.name // .model // empty)'
    )"

    if [[ -n "$names" ]]; then
        while IFS= read -r model; do
            [[ -n "$model" ]] || continue

            OLLAMA_HOST="$host" \
                ollama stop "$model" \
                >/dev/null 2>&1 || true
        done <<< "$names"
    fi

    for i in $(seq 1 30); do
        count="$(
            curl -fsS "$url/api/ps" |
                jq '.models | length'
        )"

        if [[ "$count" == "0" ]]; then
            return 0
        fi

        sleep 1
    done

    printf \
        'ERROR: models remained resident on %s after unload request\n' \
        "$url" \
        >&2

    curl -fsS "$url/api/ps" | jq . >&2 || true
    return 1
}

run_task() {
    local label="$1"
    local model="$2"
    local url="$3"
    local host="$4"
    local run_no="$5"

    local dir="$OUT/runs/${run_no}-${label}"
    local log="$OUT/runs/${run_no}-${label}.console.txt"
    local rc

    printf \
        '\n===== repeat %s / %s / %s =====\n' \
        "$run_no" \
        "$label" \
        "$model" \
        | tee -a "$OUT/runs/order.txt"

    unload_host "$url" "$host"

    set +e

    bc250-benchmark task \
        "$model" \
        --ollama-url "$url" \
        --output-dir "$dir" \
        2>&1 | tee "$log"

    rc="${PIPESTATUS[0]}"

    set -e

    printf '%s\n' "$rc" \
        > "$OUT/runs/${run_no}-${label}.rc"

    # rc=3 is a genuine quality failure and must be retained as evidence.
    # Anything else nonzero is infrastructure failure.
    if [[ "$rc" != "0" && "$rc" != "3" ]]; then
        printf \
            'ERROR: infrastructure failure: %s returned rc=%s\n' \
            "$label" \
            "$rc" \
            >&2
        return "$rc"
    fi

    unload_host "$url" "$host"
}

write_aggregate() {
    python3 - "$OUT" > "$OUT/aggregate.txt" <<'PY'
import json
import pathlib
import statistics
import sys
from collections import defaultdict

root = pathlib.Path(sys.argv[1])

records = []

for path in sorted((root / "runs").glob("*/results.jsonl")):
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        row = json.loads(line)

        if row.get("result_type") == "qualification":
            records.append(row)

if not records:
    print("No qualification records found.")
    raise SystemExit(0)

by_model = defaultdict(list)

for row in records:
    model = row["model"].removesuffix(":latest")
    by_model[model].append(row)

print("MODEL SUMMARY")
print(
    "model\tpass/total\tformat_fail\tlanguage_fail\t"
    "relevance_fail\tbudget_diag\tmedian_wall_s\t"
    "min_mem_avail_mib\tmax_swap_used_mib"
)

for model in sorted(by_model):
    rows = by_model[model]

    passed = sum(
        row.get("outcome") == "pass"
        for row in rows
    )

    format_fail = sum(
        "format-contract" in row.get("failure_kinds", [])
        for row in rows
    )

    language_fail = sum(
        "language" in row.get("failure_kinds", [])
        for row in rows
    )

    relevance_fail = sum(
        "relevance" in row.get("failure_kinds", [])
        for row in rows
    )

    budget_diag = sum(
        "output-budget" in row.get("diagnostics", [])
        for row in rows
    )

    walls = [
        float(row["metrics"]["wall_s"])
        for row in rows
        if row.get("metrics", {}).get("wall_s") is not None
    ]

    mem_values = [
        float(row["telemetry"]["mem_available_min_mib"])
        for row in rows
        if row.get("telemetry", {}).get("mem_available_min_mib")
        is not None
    ]

    swap_values = [
        float(row["telemetry"]["swap_used_max_mib"])
        for row in rows
        if row.get("telemetry", {}).get("swap_used_max_mib")
        is not None
    ]

    median_wall = (
        f"{statistics.median(walls):.3f}"
        if walls
        else "NA"
    )

    min_mem = (
        f"{min(mem_values):.1f}"
        if mem_values
        else "NA"
    )

    max_swap = (
        f"{max(swap_values):.1f}"
        if swap_values
        else "NA"
    )

    print(
        f"{model}\t"
        f"{passed}/{len(rows)}\t"
        f"{format_fail}\t"
        f"{language_fail}\t"
        f"{relevance_fail}\t"
        f"{budget_diag}\t"
        f"{median_wall}\t"
        f"{min_mem}\t"
        f"{max_swap}"
    )

print()
print("PER-CASE PASS RATE")
print("model\tcase\tpass/total\tfailures")

case_rows = defaultdict(list)

for row in records:
    key = (
        row["model"].removesuffix(":latest"),
        row["case_id"],
    )
    case_rows[key].append(row)

for (model, case), rows in sorted(case_rows.items()):
    passed = sum(
        row.get("outcome") == "pass"
        for row in rows
    )

    failures = sorted({
        failure
        for row in rows
        for failure in row.get("failure_kinds", [])
    })

    print(
        f"{model}\t"
        f"{case}\t"
        f"{passed}/{len(rows)}\t"
        f"{','.join(failures) or '-'}"
    )

print()
print("FAILED RESPONSES")

for row in records:
    if row.get("outcome") == "pass":
        continue

    print()
    print(
        f"[{row['model']} / {row['case_id']}]"
    )

    print(
        "failure_kinds:",
        ", ".join(row.get("failure_kinds", [])) or "-"
    )

    print(
        "diagnostics:",
        ", ".join(row.get("diagnostics", [])) or "-"
    )

    print(
        "checks:",
        json.dumps(
            row.get("checks", {}),
            ensure_ascii=False,
            sort_keys=True,
        ),
    )

    print(
        "response:",
        row.get("response", ""),
    )

    thinking = row.get("thinking", "")

    if thinking:
        print(
            "thinking:",
            thinking,
        )
PY
}

finalize() {
    local rc=$?

    set +e

    printf '%s\n' "$rc" \
        > "$OUT/post/script-exit-rc.txt"

    date --iso-8601=seconds \
        > "$OUT/post/end-time.txt"

    capture_state \
        "$OUT/post/state"

    journalctl \
        -b \
        --since "$START_ISO" \
        --no-pager \
        -u ollama.service \
        -u ollama-task.service \
        > "$OUT/post/ollama-journal.txt" \
        2>&1 || true

    journalctl \
        -k \
        -b \
        --since "$START_ISO" \
        --no-pager \
        > "$OUT/post/kernel-journal.txt" \
        2>&1 || true

    grep -Ei \
        'oom|out of memory|killed process|amdgpu|ring|gpu reset|device lost' \
        "$OUT/post/ollama-journal.txt" \
        "$OUT/post/kernel-journal.txt" \
        > "$OUT/post/warnings.txt" \
        2>/dev/null || true

    write_aggregate || true

    PARENT="$(dirname "$OUT")"
    NAME="$(basename "$OUT")"
    TAR="$HOME/${NAME}.tar.gz"

    tar \
        -C "$PARENT" \
        -czf "$TAR" \
        "$NAME"

    sha256sum "$TAR" \
        > "$TAR.sha256"

    printf '\n'
    printf 'Evidence directory: %s\n' "$OUT"
    printf 'Tarball: %s\n' "$TAR"
    printf 'SHA256 file: %s\n' "$TAR.sha256"
    printf '\n'
    cat "$TAR.sha256"

    exit "$rc"
}

trap finalize EXIT

cat > "$OUT/setup/README.txt" <<EOF
Batch 1: task-model quality matrix
Started: $START_ISO

Purpose:
- Compare current Gemma 1B task default against Granite 4.2 3B
  and Qwen3.8 4B Distill.
- Exercise the current packaged benchmark prompt and token budgets.
- Do not change production prompts/settings.
- Do not run full release qualification.

Topology:
- Gemma task model: 127.0.0.1:11435
- Granite experiment: 127.0.0.1:11434
- Qwen38 experiment: 127.0.0.1:11434

Important:
- Do not use Open WebUI interactively during this batch.
- Experimental main-lane models are explicitly unloaded between runs.
- rc=3 from bc250-benchmark is retained as quality evidence.
EOF

capture_state \
    "$OUT/setup/state-before"

if ! systemctl is-active --quiet ollama.service; then
    echo 'ERROR: ollama.service is not active.' >&2
    exit 1
fi

if ! systemctl is-active --quiet ollama-task.service; then
    echo 'ERROR: ollama-task.service is not active.' >&2
    exit 1
fi

if ! model_present "$TASK_URL" "$GEMMA"; then
    printf \
        'ERROR: packaged task model is not registered on 11435: %s\n' \
        "$GEMMA" \
        >&2
    exit 1
fi

# Preserve the exact installed benchmark contract being exercised.
sha256sum \
    /usr/libexec/bc250-llm-server/category-benchmark.py \
    /usr/share/bc250-llm-server/benchmark/task-cases.json \
    > "$OUT/setup/benchmark-contract.sha256"

cp \
    /usr/share/bc250-llm-server/benchmark/task-cases.json \
    "$OUT/setup/task-cases.json"

sudo bc250-model list task \
    > "$OUT/setup/task-models-before.txt" \
    2>&1

sudo bc250-model list experiments \
    > "$OUT/setup/experiment-models-before.txt" \
    2>&1

printf '\nInstalling/reusing packaged experimental candidates...\n'

sudo bc250-model install experiments \
    "$GRANITE,$QWEN" \
    2>&1 | tee "$OUT/setup/experiment-install.txt"

if ! model_present "$MAIN_URL" "$GRANITE"; then
    printf \
        'ERROR: Granite is not registered on 11434: %s\n' \
        "$GRANITE" \
        >&2
    exit 1
fi

if ! model_present "$MAIN_URL" "$QWEN"; then
    printf \
        'ERROR: Qwen38 is not registered on 11434: %s\n' \
        "$QWEN" \
        >&2
    exit 1
fi

curl -fsS "$MAIN_URL/api/tags" \
    | jq . \
    > "$OUT/setup/main-tags-after-install.json"

curl -fsS "$TASK_URL/api/tags" \
    | jq . \
    > "$OUT/setup/task-tags-after-install.json"

#
# Run round-robin rather than AAA / BBB / CCC.
# This reduces simple thermal/run-order bias.
#
for n in 1 2 3; do
    run_task \
        gemma \
        "$GEMMA" \
        "$TASK_URL" \
        "$TASK_HOST" \
        "$n"

    #
    # Qwen38 must not overlap a resident GPT-OSS.
    # The main lane is deliberately emptied before the experiments.
    #
    unload_host \
        "$MAIN_URL" \
        "$MAIN_HOST"

    run_task \
        granite \
        "$GRANITE" \
        "$MAIN_URL" \
        "$MAIN_HOST" \
        "$n"

    run_task \
        qwen38 \
        "$QWEN" \
        "$MAIN_URL" \
        "$MAIN_HOST" \
        "$n"
done

write_aggregate

printf '\n'
printf '================ BATCH 1 SUMMARY ================\n'
cat "$OUT/aggregate.txt"
printf '=================================================\n'
