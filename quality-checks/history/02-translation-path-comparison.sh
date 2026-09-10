#!/usr/bin/env bash
# Reusable evidence script: Batch 2 direct-vs-Open-WebUI translation comparison.
# The direct path adds explicit source/target direction; the OWUI path sends only
# the source text through the packaged translation preset. Credentials are kept
# out of the evidence tree and scanned before packaging.

set -Eeuo pipefail
umask 077

MODEL='prod-lfm25-8b-a1b-liquidai-q6-k'
PRESET='bc250-office-translation'

MAIN_URL='http://127.0.0.1:11434'
MAIN_HOST='127.0.0.1:11434'
OWUI_URL='http://127.0.0.1:3000'

TOKEN_FILE="${BC250_OWUI_TOKEN_FILE:-/root/owui-test.key}"

FIXTURE='/usr/share/bc250-llm-server/benchmark/translation-office.json'
BENCH='/usr/libexec/bc250-llm-server/category-benchmark.py'

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="${BC250_QUALITY_ROOT:-$HOME/bc250-quality}"
OUT="$ROOT/batch2-translation-$STAMP"

HEADER_FILE=''
START_ISO="$(date --iso-8601=seconds)"

mkdir -p "$OUT"/{setup,runs,post}

printf '%s\n' "$START_ISO" \
    > "$OUT/setup/start-time.txt"

cp "$0" "$OUT/batch2-translation.sh" 2>/dev/null || true


need() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'ERROR: required command not found: %s\n' "$1" >&2
        exit 1
    }
}


for cmd in \
    bc250-benchmark \
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


if ! sudo test -r "$TOKEN_FILE" || \
   ! sudo test -s "$TOKEN_FILE"
then
    printf \
        'ERROR: Open WebUI API token file is not readable/non-empty: %s\n' \
        "$TOKEN_FILE" \
        >&2
    exit 1
fi


#
# Keep the API credential outside the evidence directory.
# curl reads the Authorization header from this root-only /run file.
#
HEADER_FILE="$(
    sudo mktemp /run/bc250-owui-header.XXXXXX
)"

sudo chmod 600 "$HEADER_FILE"

sudo bash -c '
    set -euo pipefail

    token="$(<"$1")"

    printf \
        "Authorization: Bearer %s\n" \
        "$token" \
        > "$2"
' bash "$TOKEN_FILE" "$HEADER_FILE"


owui_get() {
    local path="$1"

    sudo curl \
        -fsS \
        --connect-timeout 10 \
        --max-time 900 \
        -H @"$HEADER_FILE" \
        "$OWUI_URL$path"
}


owui_post_file() {
    local path="$1"
    local payload="$2"

    sudo curl \
        -fsS \
        --connect-timeout 10 \
        --max-time 900 \
        -H @"$HEADER_FILE" \
        -H 'Content-Type: application/json' \
        --data-binary @"$payload" \
        "$OWUI_URL$path"
}


capture_state() {
    local dest="$1"

    mkdir -p "$dest"

    date --iso-8601=seconds \
        > "$dest/time.txt"

    uname -a \
        > "$dest/uname.txt"

    rpm -q \
        --qf '%{NAME} %{VERSION}-%{RELEASE} %{ARCH}\n' \
        bc250-llm-server \
        > "$dest/package.txt"

    systemctl is-active \
        ollama.service \
        ollama-task.service \
        ollama-embedding.service \
        open-webui.service \
        > "$dest/services-active.txt" \
        2>&1 || true

    free -h \
        > "$dest/free-h.txt"

    cat /proc/meminfo \
        > "$dest/meminfo.txt"

    cat /proc/swaps \
        > "$dest/swaps.txt"

    curl -fsS "$MAIN_URL/api/version" \
        | jq . \
        > "$dest/main-version.json"

    curl -fsS "$MAIN_URL/api/tags" \
        | jq . \
        > "$dest/main-tags.json"

    curl -fsS "$MAIN_URL/api/ps" \
        | jq . \
        > "$dest/main-ps.json"

    curl -fsS "$OWUI_URL/api/version" \
        | jq . \
        > "$dest/owui-version.json" \
        2>/dev/null || true
}


model_present() {
    curl -fsS "$MAIN_URL/api/tags" \
        | jq -e \
            --arg model "$MODEL" \
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


unload_main() {
    local names
    local model
    local i
    local count

    names="$(
        curl -fsS "$MAIN_URL/api/ps" \
            | jq -r \
                '.models[]? | (.name // .model // empty)'
    )"

    if [[ -n "$names" ]]; then
        while IFS= read -r model; do
            [[ -n "$model" ]] || continue

            OLLAMA_HOST="$MAIN_HOST" \
                ollama stop "$model" \
                >/dev/null 2>&1 || true
        done <<< "$names"
    fi

    for i in $(seq 1 30); do
        count="$(
            curl -fsS "$MAIN_URL/api/ps" \
                | jq '.models | length'
        )"

        if [[ "$count" == "0" ]]; then
            return 0
        fi

        sleep 1
    done

    echo \
        'ERROR: main Ollama still has resident models after unload request.' \
        >&2

    curl -fsS "$MAIN_URL/api/ps" \
        | jq . \
        >&2 || true

    return 1
}


write_owui_evaluator() {
    cat > "$OUT/setup/evaluate-owui.py" <<'PY'
#!/usr/bin/env python3

import argparse
import csv
import importlib.util
import json
import pathlib
import sys


def load_benchmark(path: pathlib.Path):
    #
    # category-benchmark.py imports benchmark_common from the same
    # installed directory.
    #
    sys.path.insert(0, str(path.parent))

    spec = importlib.util.spec_from_file_location(
        "bc250_category_benchmark",
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"cannot import benchmark module: {path}"
        )

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    return module


def response_text(result):
    choices = (
        result.get("choices")
        if isinstance(result, dict)
        else None
    )

    if not isinstance(choices, list) or not choices:
        return ""

    first = (
        choices[0]
        if isinstance(choices[0], dict)
        else {}
    )

    message = (
        first.get("message")
        if isinstance(first.get("message"), dict)
        else {}
    )

    return str(message.get("content") or "")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--benchmark",
        required=True,
    )

    parser.add_argument(
        "--fixture",
        required=True,
    )

    parser.add_argument(
        "--round-dir",
        required=True,
    )

    parser.add_argument(
        "--model",
        required=True,
    )

    args = parser.parse_args()

    benchmark_path = pathlib.Path(args.benchmark)

    bench = load_benchmark(
        benchmark_path
    )

    fixture = json.loads(
        pathlib.Path(args.fixture).read_text(
            encoding="utf-8"
        )
    )

    round_dir = pathlib.Path(args.round_dir)

    results_path = (
        round_dir / "results.jsonl"
    )

    csv_path = (
        round_dir / "results.csv"
    )

    rows = []

    for case in fixture:
        case_id = case["id"]

        raw_path = (
            round_dir
            / "raw"
            / f"{case_id}.response.json"
        )

        result = json.loads(
            raw_path.read_text(
                encoding="utf-8"
            )
        )

        content = response_text(
            result
        )

        (
            required_ok,
            forbidden_ok,
            preserved_ok,
            meaningful_ok,
        ) = bench.translation_content_checks(
            content,
            case,
        )

        language_hint = (
            bench.task_language_hint(
                content,
                case["target_language"],
            )
        )

        language_ok = (
            language_hint == "match"
        )

        semantic_ok = (
            required_ok
            and meaningful_ok
        )

        ok = (
            bool(content.strip())
            and language_ok
            and semantic_ok
            and forbidden_ok
            and preserved_ok
        )

        failures = (
            bench.translation_failure_kinds(
                content,
                language_ok=language_ok,
                source_leakage_ok=forbidden_ok,
                semantic_ok=semantic_ok,
                preserved_ok=preserved_ok,
            )
        )

        usage = (
            result.get("usage")
            if isinstance(result, dict)
            else {}
        )

        if not isinstance(usage, dict):
            usage = {}

        row = {
            "result_type": "qualification",
            "path": "owui-preset",
            "model": args.model,
            "case_id": case_id,
            "source_language": case[
                "source_language"
            ],
            "target_language": case[
                "target_language"
            ],
            "outcome": (
                "pass"
                if ok
                else "quality-fail"
            ),
            "failure_kinds": failures,
            "checks": {
                "language": language_ok,
                "semantic": semantic_ok,
                "preservation": preserved_ok,
                "source_leakage": forbidden_ok,
                "meaningful": meaningful_ok,
                "required": required_ok,
            },
            "metrics": {
                "answer_chars": len(content),
                "prompt_tokens": usage.get(
                    "prompt_tokens"
                ),
                "completion_tokens": usage.get(
                    "completion_tokens"
                ),
                "total_tokens": usage.get(
                    "total_tokens"
                ),
                "load_duration": usage.get(
                    "load_duration"
                ),
                "eval_count": usage.get(
                    "eval_count"
                ),
                "eval_duration": usage.get(
                    "eval_duration"
                ),
            },
            "response": content,
        }

        rows.append(row)

    with results_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

    fields = [
        "case_id",
        "source_language",
        "target_language",
        "outcome",
        "failure_kinds",
        "language_ok",
        "semantic_ok",
        "preserved_ok",
        "source_leakage_ok",
        "answer_chars",
    ]

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()

        for row in rows:
            checks = row["checks"]

            writer.writerow({
                "case_id": row["case_id"],
                "source_language": row[
                    "source_language"
                ],
                "target_language": row[
                    "target_language"
                ],
                "outcome": row["outcome"],
                "failure_kinds": ",".join(
                    row["failure_kinds"]
                ),
                "language_ok": int(
                    checks["language"]
                ),
                "semantic_ok": int(
                    checks["semantic"]
                ),
                "preserved_ok": int(
                    checks["preservation"]
                ),
                "source_leakage_ok": int(
                    checks["source_leakage"]
                ),
                "answer_chars": row[
                    "metrics"
                ]["answer_chars"],
            })

    passed = sum(
        row["outcome"] == "pass"
        for row in rows
    )

    print(
        "Open WebUI preset acceptance: "
        f"{passed}/{len(rows)}"
    )

    for row in rows:
        print(
            f"  {row['case_id']}: "
            f"{row['outcome']} "
            "fail="
            f"{','.join(row['failure_kinds']) or '-'}"
        )

    return (
        0
        if passed == len(rows)
        else 3
    )


if __name__ == "__main__":
    raise SystemExit(main())
PY

    chmod 700 \
        "$OUT/setup/evaluate-owui.py"
}


run_direct_round() {
    local n="$1"
    local dir="$OUT/runs/${n}-direct-explicit"
    local log="$OUT/runs/${n}-direct-explicit.console.txt"
    local rc

    mkdir -p "$dir"

    unload_main

    printf \
        '\n===== round %s / direct explicit-direction benchmark =====\n' \
        "$n" \
        | tee -a "$OUT/runs/order.txt"

    set +e

    bc250-benchmark translation \
        "$MODEL" \
        --ollama-url "$MAIN_URL" \
        --output-dir "$dir" \
        2>&1 | tee "$log"

    rc="${PIPESTATUS[0]}"

    set -e

    printf '%s\n' "$rc" \
        > "$OUT/runs/${n}-direct-explicit.rc"

    #
    # rc=3 is a legitimate quality failure.
    #
    if [[ "$rc" != "0" && "$rc" != "3" ]]; then
        printf \
            'ERROR: direct translation benchmark infrastructure failure rc=%s\n' \
            "$rc" \
            >&2
        return "$rc"
    fi

    unload_main
}


run_owui_round() {
    local n="$1"
    local dir="$OUT/runs/${n}-owui-preset"
    local payload_dir="$dir/payloads"
    local raw_dir="$dir/raw"

    local case_id
    local text
    local payload
    local raw
    local rc

    mkdir -p \
        "$payload_dir" \
        "$raw_dir"

    unload_main

    printf \
        '\n===== round %s / actual Open WebUI translation preset =====\n' \
        "$n" \
        | tee -a "$OUT/runs/order.txt"

    while IFS=$'\t' read -r case_id text; do

        payload="$payload_dir/${case_id}.json"
        raw="$raw_dir/${case_id}.response.json"

        #
        # IMPORTANT:
        #
        # Send only the real source text.
        # Do NOT inject explicit translation direction here.
        #
        jq -n \
            --arg model "$PRESET" \
            --arg text "$text" \
            '{
                model: $model,
                messages: [
                    {
                        role: "user",
                        content: $text
                    }
                ],
                stream: false,
                background_tasks: {
                    title_generation: false,
                    tags_generation: false,
                    follow_up_generation: false
                }
            }' \
            > "$payload"

        if ! owui_post_file \
            '/api/chat/completions' \
            "$payload" \
            | jq . \
            > "$raw"
        then
            printf \
                'ERROR: Open WebUI request failed: round=%s case=%s\n' \
                "$n" \
                "$case_id" \
                >&2
            return 20
        fi

        #
        # Missing completion content is an infrastructure/API failure,
        # not a model-quality failure.
        #
        if ! jq -e \
            '
            .choices
            | type == "array"
              and length > 0
              and .[0].message.content != null
            ' \
            "$raw" \
            >/dev/null
        then
            printf \
                'ERROR: malformed Open WebUI completion: round=%s case=%s\n' \
                "$n" \
                "$case_id" \
                >&2

            cat "$raw" >&2 || true

            return 21
        fi

    done < <(
        jq -r \
            '.[] | [.id, .input] | @tsv' \
            "$FIXTURE"
    )

    set +e

    python3 \
        "$OUT/setup/evaluate-owui.py" \
        --benchmark "$BENCH" \
        --fixture "$FIXTURE" \
        --round-dir "$dir" \
        --model "$MODEL" \
        2>&1 \
        | tee \
            "$OUT/runs/${n}-owui-preset.console.txt"

    rc="${PIPESTATUS[0]}"

    set -e

    printf '%s\n' "$rc" \
        > "$OUT/runs/${n}-owui-preset.rc"

    if [[ "$rc" != "0" && "$rc" != "3" ]]; then
        printf \
            'ERROR: Open WebUI evaluator infrastructure failure rc=%s\n' \
            "$rc" \
            >&2
        return "$rc"
    fi

    unload_main
}


write_aggregate() {
    python3 - "$OUT" \
        > "$OUT/aggregate.txt" <<'PY'
import json
import pathlib
import sys
from collections import defaultdict


root = pathlib.Path(
    sys.argv[1]
)

rows = []


#
# Canonical direct benchmark.
#
for path in sorted(
    (root / "runs").glob(
        "*-direct-explicit/results.jsonl"
    )
):
    round_no = int(
        path.parent.name.split("-", 1)[0]
    )

    for line in path.read_text(
        encoding="utf-8"
    ).splitlines():

        if not line.strip():
            continue

        row = json.loads(line)

        if (
            row.get("result_type")
            != "qualification"
        ):
            continue

        row = dict(row)
        row["path"] = "direct-explicit"
        row["round"] = round_no

        rows.append(row)


#
# Actual Open WebUI preset.
#
for path in sorted(
    (root / "runs").glob(
        "*-owui-preset/results.jsonl"
    )
):
    round_no = int(
        path.parent.name.split("-", 1)[0]
    )

    for line in path.read_text(
        encoding="utf-8"
    ).splitlines():

        if not line.strip():
            continue

        row = json.loads(line)

        if (
            row.get("result_type")
            != "qualification"
        ):
            continue

        row = dict(row)
        row["round"] = round_no

        rows.append(row)


if not rows:
    print(
        "No qualification rows found."
    )
    raise SystemExit(0)


print("OVERALL")
print(
    "path\tpass/total\tfailures"
)

for path_name in (
    "direct-explicit",
    "owui-preset",
):
    selected = [
        row
        for row in rows
        if row["path"] == path_name
    ]

    passed = sum(
        row.get("outcome") == "pass"
        for row in selected
    )

    failures = defaultdict(int)

    for row in selected:
        for failure in row.get(
            "failure_kinds",
            [],
        ):
            failures[failure] += 1

    failure_text = (
        ", ".join(
            f"{name}={count}"
            for name, count
            in sorted(failures.items())
        )
        or "-"
    )

    print(
        f"{path_name}\t"
        f"{passed}/{len(selected)}\t"
        f"{failure_text}"
    )


print()
print("PER CASE")
print(
    "case\t"
    "direct-explicit\t"
    "owui-preset\t"
    "delta_owui_minus_direct"
)

case_ids = sorted({
    row["case_id"]
    for row in rows
})

for case_id in case_ids:
    values = {}

    for path_name in (
        "direct-explicit",
        "owui-preset",
    ):
        selected = [
            row
            for row in rows
            if (
                row["path"] == path_name
                and row["case_id"] == case_id
            )
        ]

        passed = sum(
            row.get("outcome") == "pass"
            for row in selected
        )

        values[path_name] = (
            passed,
            len(selected),
        )

    direct_pass, direct_total = (
        values["direct-explicit"]
    )

    owui_pass, owui_total = (
        values["owui-preset"]
    )

    direct_rate = (
        direct_pass / direct_total
        if direct_total
        else 0.0
    )

    owui_rate = (
        owui_pass / owui_total
        if owui_total
        else 0.0
    )

    delta = (
        owui_rate - direct_rate
    )

    print(
        f"{case_id}\t"
        f"{direct_pass}/{direct_total}\t"
        f"{owui_pass}/{owui_total}\t"
        f"{delta:+.2f}"
    )


print()
print("PER ROUND")
print(
    "round\t"
    "direct-explicit\t"
    "owui-preset"
)

for round_no in sorted({
    row["round"]
    for row in rows
}):
    values = []

    for path_name in (
        "direct-explicit",
        "owui-preset",
    ):
        selected = [
            row
            for row in rows
            if (
                row["path"] == path_name
                and row["round"] == round_no
            )
        ]

        passed = sum(
            row.get("outcome") == "pass"
            for row in selected
        )

        values.append(
            f"{passed}/{len(selected)}"
        )

    print(
        f"{round_no}\t"
        f"{values[0]}\t"
        f"{values[1]}"
    )


#
# Always print the two previously observed weak cases.
#
print()
print("KNOWN WEAK CASE RESPONSES")

for case_id in (
    "fr-de-invoice",
    "de-fr-formal-office",
):
    print()
    print(
        f"## {case_id}"
    )

    selected = sorted(
        (
            row
            for row in rows
            if row["case_id"] == case_id
        ),
        key=lambda row: (
            row["round"],
            row["path"],
        ),
    )

    for row in selected:
        print(
            f"round={row['round']} "
            f"path={row['path']} "
            f"outcome={row['outcome']} "
            "fail="
            f"{','.join(row.get('failure_kinds', [])) or '-'}"
        )

        print(
            row.get(
                "response",
                "",
            )
        )
PY
}


credential_scan() {
    sudo python3 \
        - "$TOKEN_FILE" "$OUT" <<'PY'
from pathlib import Path
import sys


token = (
    Path(sys.argv[1])
    .read_text(
        encoding="utf-8"
    )
    .strip()
    .encode()
)

root = Path(
    sys.argv[2]
)

if not token:
    raise SystemExit(
        "token file unexpectedly empty"
    )


hits = []

for path in root.rglob("*"):
    if not path.is_file():
        continue

    try:
        data = path.read_bytes()
    except OSError:
        continue

    if token in data:
        hits.append(
            str(path)
        )


if hits:
    print(
        "ERROR: Open WebUI token leaked into evidence:",
        file=sys.stderr,
    )

    for hit in hits:
        print(
            hit,
            file=sys.stderr,
        )

    raise SystemExit(1)


print(
    "credential scan: "
    "Open WebUI token not present in evidence"
)
PY
}


finalize() {
    local rc=$?

    trap - EXIT
    set +e

    printf '%s\n' "$rc" \
        > "$OUT/post/script-exit-rc.txt"

    date --iso-8601=seconds \
        > "$OUT/post/end-time.txt"

    unload_main \
        >/dev/null 2>&1 || true

    capture_state \
        "$OUT/post/state" || true

    journalctl \
        -b \
        --since "$START_ISO" \
        --no-pager \
        -u ollama.service \
        -u open-webui.service \
        > "$OUT/post/service-journal.txt" \
        2>&1 || true

    journalctl \
        -k \
        -b \
        --since "$START_ISO" \
        --no-pager \
        > "$OUT/post/kernel-journal.txt" \
        2>&1 || true

    #
    # Deliberately avoid a bare "ring" expression.
    #
    grep -Ein \
        'out of memory|oom-kill|oom_reaper|killed process|device lost|gpu reset|amdgpu.*(reset|timeout|fault)|ring.*(timeout|reset|fault|error)' \
        "$OUT/post/service-journal.txt" \
        "$OUT/post/kernel-journal.txt" \
        > "$OUT/post/serious-warnings.txt" \
        2>/dev/null || true

    write_aggregate || true

    #
    # Delete the temporary Authorization header before
    # doing the evidence credential scan/tar.
    #
    if [[ -n "$HEADER_FILE" ]]; then
        sudo rm -f \
            "$HEADER_FILE" || true

        HEADER_FILE=''
    fi

    if ! credential_scan \
        > "$OUT/post/credential-scan.txt" \
        2>&1
    then
        cat \
            "$OUT/post/credential-scan.txt" \
            >&2

        rc=22
    fi

    PARENT="$(
        dirname "$OUT"
    )"

    NAME="$(
        basename "$OUT"
    )"

    TAR="$HOME/${NAME}.tar.gz"

    #
    # Tar only Batch 2 evidence.
    # No models/GGUFs and no API-token file are included.
    #
    tar \
        -C "$PARENT" \
        -czf "$TAR" \
        "$NAME"

    sha256sum "$TAR" \
        > "$TAR.sha256"

    printf '\n'
    printf \
        '================ BATCH 2 SUMMARY ================\n'

    cat "$OUT/aggregate.txt" \
        2>/dev/null || true

    printf \
        '=================================================\n'

    printf \
        'Evidence directory: %s\n' \
        "$OUT"

    printf \
        'Tarball: %s\n' \
        "$TAR"

    printf \
        'SHA256 file: %s\n' \
        "$TAR.sha256"

    cat "$TAR.sha256"

    exit "$rc"
}


trap finalize EXIT


cat > "$OUT/setup/README.txt" <<EOF
Batch 2: translation path comparison
Started: $START_ISO

Purpose:
- 10 rounds of the canonical explicit-direction translation benchmark.
- 10 rounds of the actual authenticated Open WebUI translation preset.
- Same eight translation-office fixtures are evaluated on both paths.
- No production configuration is changed.
- No full release qualification is run.

Direct path:
- model: $MODEL
- endpoint: $MAIN_URL
- canonical benchmark adds explicit source/target direction.

Open WebUI path:
- preset: $PRESET
- endpoint: $OWUI_URL/api/chat/completions
- each fixture input is sent as ordinary user text with no explicit direction.
- background title/tag/follow-up tasks are disabled.

Each path is cold-isolated at the start/end of its round
by unloading main Ollama.
EOF


if ! systemctl is-active \
    --quiet ollama.service
then
    echo \
        'ERROR: ollama.service is not active.' \
        >&2
    exit 1
fi


if ! systemctl is-active \
    --quiet open-webui.service
then
    echo \
        'ERROR: open-webui.service is not active.' \
        >&2
    exit 1
fi


if ! model_present
then
    printf \
        'ERROR: translation model is not registered on 11434: %s\n' \
        "$MODEL" \
        >&2
    exit 1
fi


if [[ ! -r "$FIXTURE" ]]; then
    printf \
        'ERROR: translation fixture not readable: %s\n' \
        "$FIXTURE" \
        >&2
    exit 1
fi


if [[ ! -r "$BENCH" ]]; then
    printf \
        'ERROR: benchmark implementation not readable: %s\n' \
        "$BENCH" \
        >&2
    exit 1
fi


capture_state \
    "$OUT/setup/state-before"


#
# Preserve exact source/evaluator hashes used by this batch.
#
sha256sum \
    "$BENCH" \
    "$FIXTURE" \
    > "$OUT/setup/benchmark-contract.sha256"


cp \
    "$FIXTURE" \
    "$OUT/setup/translation-office.json"


write_owui_evaluator


python3 -m py_compile \
    "$OUT/setup/evaluate-owui.py"


#
# Capture only the selected preset, not the whole Open WebUI export.
#
owui_get '/api/v1/models/export' \
    | jq \
        --arg id "$PRESET" \
        '[
            .[]
            | select(.id == $id)
            | {
                id,
                name,
                base_model_id,
                params,
                meta
            }
        ]' \
    > "$OUT/setup/owui-translation-preset.json"


#
# Fail before testing if the real preset is not wired to the LFM model.
#
if ! jq -e \
    --arg id "$PRESET" \
    --arg base "${MODEL}:latest" \
    '
    length == 1
    and .[0].id == $id
    and .[0].base_model_id == $base
    ' \
    "$OUT/setup/owui-translation-preset.json" \
    >/dev/null
then
    echo \
        'ERROR: Open WebUI translation preset does not point to the expected LFM model.' \
        >&2

    cat \
        "$OUT/setup/owui-translation-preset.json" \
        >&2

    exit 1
fi


#
# Round-robin:
#
# direct 1 -> OWUI 1 -> direct 2 -> OWUI 2 ...
#
# This is preferable to doing all 10 direct runs first,
# because it reduces run-order/thermal bias.
#
for n in $(seq 1 10); do
    run_direct_round "$n"
    run_owui_round "$n"
done


write_aggregate
