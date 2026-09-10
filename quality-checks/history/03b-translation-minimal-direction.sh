#!/usr/bin/env bash
# Reusable evidence script: Batch 3B minimal direction-system-prompt experiment.
# This is the best LFM prompt result so far (69/80), but is NOT a production
# source change yet because two cases remain systematically unreliable.

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
OUT="$ROOT/batch3b-translation-minimal-direction-$STAMP"

HEADER_FILE=''
ORIGINAL_SAVED=0
START_ISO="$(date --iso-8601=seconds)"

mkdir -p "$OUT"/{setup,runs,post}

printf '%s\n' "$START_ISO" \
    > "$OUT/setup/start-time.txt"

cp "$0" \
    "$OUT/batch3b-translation-minimal-direction.sh" \
    2>/dev/null || true


need() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'ERROR: required command not found: %s\n' "$1" >&2
        exit 1
    }
}


for cmd in \
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
        'ERROR: token file missing/unreadable: %s\n' \
        "$TOKEN_FILE" \
        >&2
    exit 1
fi


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


unload_main() {
    local names
    local model
    local i
    local count

    names="$(
        curl -fsS "$MAIN_URL/api/ps" |
            jq -r \
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
            curl -fsS "$MAIN_URL/api/ps" |
                jq '.models | length'
        )"

        if [[ "$count" == "0" ]]; then
            return 0
        fi

        sleep 1
    done

    printf '%s\n' \
        'ERROR: main Ollama did not become empty.' \
        >&2

    curl -fsS "$MAIN_URL/api/ps" \
        | jq . \
        >&2 || true

    return 1
}


capture_state() {
    local dest="$1"

    mkdir -p "$dest"

    date --iso-8601=seconds \
        > "$dest/time.txt"

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

    curl -fsS "$MAIN_URL/api/ps" \
        | jq . \
        > "$dest/main-ps.json"
}


restore_original_preset() {
    local payload

    if [[ "$ORIGINAL_SAVED" != "1" ]]; then
        return 0
    fi

    payload="$OUT/post/restore-payload.json"

    jq -n \
        --slurpfile model "$OUT/setup/original-preset.json" \
        '{
            models: [
                $model[0]
            ]
        }' \
        > "$payload"

    owui_post_file \
        '/api/v1/models/import' \
        "$payload" \
        > "$OUT/post/restore-response.json"

    owui_get '/api/v1/models/export' |
        jq \
            --arg id "$PRESET" \
            '.[] | select(.id == $id)' \
            > "$OUT/post/restored-preset.json"

    python3 \
        - "$OUT/setup/original-preset.json" \
          "$OUT/post/restored-preset.json" <<'PY'
import json
import sys

a = json.load(
    open(sys.argv[1], encoding="utf-8")
)

b = json.load(
    open(sys.argv[2], encoding="utf-8")
)


def stable(model):
    return {
        "id": model.get("id"),
        "base_model_id": model.get("base_model_id"),
        "name": model.get("name"),
        "params": model.get("params"),
        "meta": model.get("meta"),
        "is_active": model.get("is_active", True),
        "access_grants": model.get("access_grants"),
    }


if stable(a) != stable(b):
    print(
        "ERROR: restored preset differs from original",
        file=sys.stderr,
    )

    raise SystemExit(1)


print(
    "Preset restoration verified."
)
PY

    printf '%s\n' \
        'Preset restoration verified.' \
        > "$OUT/post/restoration-status.txt"
}


write_evaluator() {
    cat > "$OUT/setup/evaluate.py" <<'PY'
#!/usr/bin/env python3

import argparse
import importlib.util
import json
import pathlib
import sys


def load_benchmark(path):
    path = pathlib.Path(path)

    sys.path.insert(
        0,
        str(path.parent),
    )

    spec = importlib.util.spec_from_file_location(
        "bc250_category_benchmark",
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"cannot import {path}"
        )

    module = importlib.util.module_from_spec(spec)

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    return module


def response_text(result):
    choices = result.get("choices")

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

    return str(
        message.get("content") or ""
    )


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

    bench = load_benchmark(
        args.benchmark
    )

    cases = json.loads(
        pathlib.Path(args.fixture).read_text(
            encoding="utf-8"
        )
    )

    round_dir = pathlib.Path(
        args.round_dir
    )

    rows = []

    for case in cases:
        raw_path = (
            round_dir
            / "raw"
            / f"{case['id']}.response.json"
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

        passed = (
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

        rows.append({
            "result_type": "qualification",
            "path": "owui-minimal-direction",
            "model": args.model,
            "case_id": case["id"],
            "source_language": case[
                "source_language"
            ],
            "target_language": case[
                "target_language"
            ],
            "outcome": (
                "pass"
                if passed
                else "quality-fail"
            ),
            "failure_kinds": failures,
            "checks": {
                "language": language_ok,
                "semantic": semantic_ok,
                "preservation": preserved_ok,
                "source_leakage": forbidden_ok,
            },
            "response": content,
        })

    with (
        round_dir / "results.jsonl"
    ).open(
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

    passed = sum(
        row["outcome"] == "pass"
        for row in rows
    )

    print(
        f"Candidate acceptance: "
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
    raise SystemExit(
        main()
    )
PY

    chmod 700 \
        "$OUT/setup/evaluate.py"

    python3 -m py_compile \
        "$OUT/setup/evaluate.py"
}


run_round() {
    local n="$1"
    local dir="$OUT/runs/$n"
    local raw_dir="$dir/raw"
    local payload_dir="$dir/payloads"

    local case_id
    local text
    local payload
    local raw
    local rc

    mkdir -p \
        "$raw_dir" \
        "$payload_dir"

    unload_main

    printf \
        '\n===== minimal-direction round %s =====\n' \
        "$n"

    while IFS=$'\t' read -r case_id text; do
        payload="$payload_dir/${case_id}.json"
        raw="$raw_dir/${case_id}.response.json"

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
                'ERROR: request failed: round=%s case=%s\n' \
                "$n" \
                "$case_id" \
                >&2

            return 20
        fi

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
                'ERROR: malformed completion: round=%s case=%s\n' \
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
        "$OUT/setup/evaluate.py" \
        --benchmark "$BENCH" \
        --fixture "$FIXTURE" \
        --round-dir "$dir" \
        --model "$MODEL" \
        2>&1 |
        tee "$dir/console.txt"

    rc="${PIPESTATUS[0]}"

    set -e

    printf '%s\n' "$rc" \
        > "$dir/rc"

    if [[ "$rc" != "0" && "$rc" != "3" ]]; then
        printf \
            'ERROR: evaluator infrastructure failure rc=%s\n' \
            "$rc" \
            >&2

        return "$rc"
    fi

    unload_main
}


write_aggregate() {
    python3 - "$OUT" > "$OUT/aggregate.txt" <<'PY'
import json
import pathlib
import sys
from collections import Counter, defaultdict


root = pathlib.Path(
    sys.argv[1]
)


batch2 = {
    "de-fr-formal-office": 4,
    "de-fr-invoice": 10,
    "de-fr-negation": 10,
    "de-fr-reference-date": 10,
    "fr-de-invoice": 0,
    "fr-de-lease": 1,
    "fr-de-negation": 0,
    "fr-de-reference-date": 10,
}


batch3a = {
    "de-fr-formal-office": 1,
    "de-fr-invoice": 9,
    "de-fr-negation": 9,
    "de-fr-reference-date": 10,
    "fr-de-invoice": 8,
    "fr-de-lease": 10,
    "fr-de-negation": 10,
    "fr-de-reference-date": 10,
}


rows = []

for path in sorted(
    (root / "runs").glob(
        "*/results.jsonl"
    ),
    key=lambda p: int(
        p.parent.name
    ),
):
    round_no = int(
        path.parent.name
    )

    for line in path.read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip():
            continue

        row = json.loads(line)
        row["round"] = round_no
        rows.append(row)


passed = sum(
    row["outcome"] == "pass"
    for row in rows
)


print(
    "BATCH 2 ORIGINAL OWUI: 45/80"
)

print(
    "BATCH 3A STRONG PROMPT: 67/80"
)

print(
    f"BATCH 3B MINIMAL PROMPT: "
    f"{passed}/{len(rows)}"
)


failures = Counter(
    failure
    for row in rows
    for failure in row.get(
        "failure_kinds",
        [],
    )
)


print(
    "BATCH 3B FAILURES:",
    ", ".join(
        f"{name}={count}"
        for name, count
        in sorted(
            failures.items()
        )
    )
    or "-",
)


print()
print(
    "case\t"
    "batch2\t"
    "batch3a\t"
    "batch3b\t"
    "3b-vs-2\t"
    "3b-vs-3a"
)


by_case = defaultdict(list)

for row in rows:
    by_case[
        row["case_id"]
    ].append(row)


for case_id in sorted(by_case):
    case_rows = by_case[
        case_id
    ]

    p = sum(
        row["outcome"] == "pass"
        for row in case_rows
    )

    print(
        f"{case_id}\t"
        f"{batch2[case_id]}/10\t"
        f"{batch3a[case_id]}/10\t"
        f"{p}/10\t"
        f"{p-batch2[case_id]:+d}\t"
        f"{p-batch3a[case_id]:+d}"
    )


print()
print("PER ROUND")


for round_no in range(1, 11):
    selected = [
        row
        for row in rows
        if row["round"] == round_no
    ]

    p = sum(
        row["outcome"] == "pass"
        for row in selected
    )

    print(
        f"{round_no}: "
        f"{p}/{len(selected)}"
    )


print()
print("FAILED RESPONSES")


for row in rows:
    if row["outcome"] == "pass":
        continue

    print()

    print(
        f"round={row['round']} "
        f"case={row['case_id']} "
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
        "token unexpectedly empty"
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
        "ERROR: token found in evidence:",
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
    local restore_rc=0

    trap - EXIT
    set +e

    printf '%s\n' "$rc" \
        > "$OUT/post/test-script-rc.txt"

    if ! restore_original_preset; then
        printf '%s\n' \
            'ERROR: preset restoration failed.' \
            > "$OUT/post/restoration-status.txt"

        restore_rc=1
        rc=23
    fi

    unload_main \
        >/dev/null 2>&1 || true

    date --iso-8601=seconds \
        > "$OUT/post/end-time.txt"

    capture_state \
        "$OUT/post/state-after" \
        2>/dev/null || true

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

    grep -Ein \
        'out of memory|oom-kill|oom_reaper|killed process|device lost|gpu reset|amdgpu.*(reset|timeout|fault)|ring.*(timeout|reset|fault|error)' \
        "$OUT/post/service-journal.txt" \
        "$OUT/post/kernel-journal.txt" \
        > "$OUT/post/serious-warnings.txt" \
        2>/dev/null || true

    write_aggregate || true

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

        rc=24
    fi

    PARENT="$(
        dirname "$OUT"
    )"

    NAME="$(
        basename "$OUT"
    )"

    TAR="$HOME/${NAME}.tar.gz"

    tar \
        -C "$PARENT" \
        -czf "$TAR" \
        "$NAME"

    sha256sum "$TAR" \
        > "$TAR.sha256"

    printf '\n'
    printf \
        '================ BATCH 3B SUMMARY ================\n'

    cat "$OUT/aggregate.txt" \
        2>/dev/null || true

    printf \
        '==================================================\n'

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

    if [[ "$restore_rc" != "0" ]]; then
        printf '\nCRITICAL: preset restoration FAILED.\n' >&2
    fi

    exit "$rc"
}


trap finalize EXIT


if ! systemctl is-active --quiet ollama.service; then
    echo \
        'ERROR: ollama.service is not active.' \
        >&2

    exit 1
fi


if ! systemctl is-active --quiet open-webui.service; then
    echo \
        'ERROR: open-webui.service is not active.' \
        >&2

    exit 1
fi


if [[ ! -r "$FIXTURE" || ! -r "$BENCH" ]]; then
    echo \
        'ERROR: installed fixture/benchmark unavailable.' \
        >&2

    exit 1
fi


capture_state \
    "$OUT/setup/state-before"


sha256sum \
    "$FIXTURE" \
    "$BENCH" \
    > "$OUT/setup/benchmark-contract.sha256"


cp \
    "$FIXTURE" \
    "$OUT/setup/translation-office.json"


owui_get '/api/v1/models/export' |
    jq \
        --arg id "$PRESET" \
        '.[] | select(.id == $id)' \
        > "$OUT/setup/original-preset.json"


if ! jq -e \
    --arg id "$PRESET" \
    --arg base "${MODEL}:latest" \
    '
    .id == $id
    and .base_model_id == $base
    ' \
    "$OUT/setup/original-preset.json" \
    >/dev/null
then
    echo \
        'ERROR: expected translation preset not found/base differs.' \
        >&2

    exit 1
fi


ORIGINAL_SAVED=1


#
# Candidate 3B:
# Existing production SYSTEM text with only minimal,
# explicit source-language discipline added.
#
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


SYSTEM_PROMPT="$(
    cat "$OUT/setup/candidate-system.txt"
)"


jq \
    --arg system "$SYSTEM_PROMPT" \
    '
    .params = (
        (.params // {})
        + {
            system: $system
        }
    )
    ' \
    "$OUT/setup/original-preset.json" \
    > "$OUT/setup/candidate-preset.json"


jq -n \
    --slurpfile model "$OUT/setup/candidate-preset.json" \
    '{
        models: [
            $model[0]
        ]
    }' \
    > "$OUT/setup/candidate-import.json"


owui_post_file \
    '/api/v1/models/import' \
    "$OUT/setup/candidate-import.json" \
    > "$OUT/setup/candidate-import-response.json"


owui_get '/api/v1/models/export' |
    jq \
        --arg id "$PRESET" \
        '.[] | select(.id == $id)' \
        > "$OUT/setup/live-candidate-preset.json"


if ! jq -e \
    --arg system "$SYSTEM_PROMPT" \
    '
    .params.system == $system
    ' \
    "$OUT/setup/live-candidate-preset.json" \
    >/dev/null
then
    echo \
        'ERROR: live preset did not retain candidate system prompt.' \
        >&2

    exit 1
fi


write_evaluator


cat > "$OUT/setup/README.txt" <<'EOF'
Batch 3B: minimal Open WebUI translation direction reinforcement

Only one behavior is being tested:
- stronger explicit German/French source-direction discipline.

Unchanged:
- LFM base model
- model generation parameters
- temperature
- fixtures
- installed evaluator
- eight test cases
- Open WebUI completion path

The candidate intentionally contains:
- no Erhalt/reception special case
- no invoice special case
- no fixture-specific terminology
- no evaluator change

Comparison:
- Batch 2 original OWUI: 45/80
- Batch 3A stronger system prompt: 67/80

Original Open WebUI preset is restored automatically.
EOF


for n in $(seq 1 10); do
    run_round "$n"
done


write_aggregate
