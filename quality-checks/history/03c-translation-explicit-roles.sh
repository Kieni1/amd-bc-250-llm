#!/usr/bin/env bash
# Reusable evidence script: Batch 3C fixed DE->FR / FR->DE role experiment.
# Result: 69/80, no net gain over 3B; do not infer that two fixed product presets
# are justified. Original preset is restored automatically.

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
OUT="$ROOT/batch3c-translation-explicit-roles-$STAMP"

HEADER_FILE=''
ORIGINAL_SAVED=0
START_ISO="$(date --iso-8601=seconds)"

mkdir -p "$OUT"/{setup,runs/post,post}
mkdir -p "$OUT/runs/de-fr" "$OUT/runs/fr-de"

printf '%s\n' "$START_ISO" > "$OUT/setup/start-time.txt"
cp "$0" "$OUT/batch3c-translation-explicit-roles.sh" 2>/dev/null || true


need() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'ERROR: required command unavailable: %s\n' "$1" >&2
        exit 1
    }
}


for cmd in \
    curl jq ollama python3 rpm systemctl journalctl \
    free tar sha256sum
do
    need "$cmd"
done


sudo -v


if ! sudo test -r "$TOKEN_FILE" || \
   ! sudo test -s "$TOKEN_FILE"
then
    printf 'ERROR: token file unavailable: %s\n' "$TOKEN_FILE" >&2
    exit 1
fi


HEADER_FILE="$(
    sudo mktemp /run/bc250-owui-header.XXXXXX
)"

sudo chmod 600 "$HEADER_FILE"

sudo bash -c '
    set -euo pipefail
    token="$(<"$1")"
    printf "Authorization: Bearer %s\n" "$token" > "$2"
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
    local count
    local i

    names="$(
        curl -fsS "$MAIN_URL/api/ps" |
            jq -r '.models[]? | (.name // .model // empty)'
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

        [[ "$count" == "0" ]] && return 0
        sleep 1
    done

    echo 'ERROR: main Ollama did not unload.' >&2
    curl -fsS "$MAIN_URL/api/ps" | jq . >&2 || true
    return 1
}


capture_state() {
    local dest="$1"

    mkdir -p "$dest"

    date --iso-8601=seconds > "$dest/time.txt"

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

    free -h > "$dest/free-h.txt"
    cat /proc/meminfo > "$dest/meminfo.txt"
    cat /proc/swaps > "$dest/swaps.txt"

    curl -fsS "$MAIN_URL/api/ps" |
        jq . > "$dest/main-ps.json"
}


apply_prompt() {
    local label="$1"
    local prompt_file="$2"
    local system
    local candidate
    local import_payload
    local live

    system="$(
        cat "$prompt_file"
    )"

    candidate="$OUT/setup/${label}-candidate-preset.json"
    import_payload="$OUT/setup/${label}-candidate-import.json"
    live="$OUT/setup/${label}-live-preset.json"

    jq \
        --arg system "$system" \
        '
        .params = (
            (.params // {})
            + {
                system: $system
            }
        )
        ' \
        "$OUT/setup/original-preset.json" \
        > "$candidate"

    jq -n \
        --slurpfile model "$candidate" \
        '{
            models: [
                $model[0]
            ]
        }' \
        > "$import_payload"

    owui_post_file \
        '/api/v1/models/import' \
        "$import_payload" \
        > "$OUT/setup/${label}-import-response.json"

    owui_get '/api/v1/models/export' |
        jq \
            --arg id "$PRESET" \
            '.[] | select(.id == $id)' \
            > "$live"

    if ! jq -e \
        --arg system "$system" \
        '.params.system == $system' \
        "$live" \
        >/dev/null
    then
        printf \
            'ERROR: candidate prompt was not retained: %s\n' \
            "$label" \
            >&2
        return 1
    fi
}


restore_original_preset() {
    local payload="$OUT/post/restore-payload.json"

    [[ "$ORIGINAL_SAVED" == "1" ]] || return 0

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


with open(sys.argv[1], encoding="utf-8") as f:
    original = json.load(f)

with open(sys.argv[2], encoding="utf-8") as f:
    restored = json.load(f)


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


if stable(original) != stable(restored):
    print(
        "ERROR: restored preset differs from original",
        file=sys.stderr,
    )
    raise SystemExit(1)


print("Preset restoration verified.")
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
from collections import Counter, defaultdict


def load_benchmark(path):
    path = pathlib.Path(path)

    sys.path.insert(0, str(path.parent))

    spec = importlib.util.spec_from_file_location(
        "bc250_category_benchmark",
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")

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

    return str(message.get("content") or "")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--model", required=True)

    args = parser.parse_args()

    bench = load_benchmark(args.benchmark)

    cases = json.loads(
        pathlib.Path(args.fixture).read_text(
            encoding="utf-8"
        )
    )

    case_map = {
        case["id"]: case
        for case in cases
    }

    root = pathlib.Path(args.root)

    rows = []

    for direction in ("de-fr", "fr-de"):
        for round_dir in sorted(
            (root / "runs" / direction).glob("*"),
            key=lambda p: int(p.name),
        ):
            if not round_dir.is_dir():
                continue

            round_no = int(round_dir.name)

            for raw_path in sorted(
                (round_dir / "raw").glob("*.response.json")
            ):
                case_id = raw_path.name.removesuffix(
                    ".response.json"
                )

                case = case_map[case_id]

                result = json.loads(
                    raw_path.read_text(
                        encoding="utf-8"
                    )
                )

                content = response_text(result)

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

                row = {
                    "result_type": "qualification",
                    "path": "owui-explicit-role",
                    "direction": direction,
                    "round": round_no,
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
                }

                rows.append(row)

    with (
        root / "results.jsonl"
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

    baseline_3b = {
        "de-fr-formal-office": 4,
        "de-fr-invoice": 10,
        "de-fr-negation": 10,
        "de-fr-reference-date": 10,
        "fr-de-invoice": 5,
        "fr-de-lease": 10,
        "fr-de-negation": 10,
        "fr-de-reference-date": 10,
    }

    passed = sum(
        row["outcome"] == "pass"
        for row in rows
    )

    failures = Counter(
        failure
        for row in rows
        for failure in row.get(
            "failure_kinds",
            [],
        )
    )

    by_case = defaultdict(list)

    for row in rows:
        by_case[row["case_id"]].append(row)

    print("BATCH 2 ORIGINAL AUTO OWUI: 45/80")
    print("BATCH 3A STRONG AUTO:       67/80")
    print("BATCH 3B MINIMAL AUTO:      69/80")
    print(
        f"BATCH 3C EXPLICIT ROLES:    "
        f"{passed}/{len(rows)}"
    )

    print()

    print(
        "FAILURES:",
        ", ".join(
            f"{name}={count}"
            for name, count in sorted(
                failures.items()
            )
        )
        or "-",
    )

    print()
    print(
        "case\tbatch3b-auto\t"
        "batch3c-explicit\tdelta"
    )

    for case_id in sorted(by_case):
        selected = by_case[case_id]

        p = sum(
            row["outcome"] == "pass"
            for row in selected
        )

        base = baseline_3b[case_id]

        print(
            f"{case_id}\t"
            f"{base}/10\t"
            f"{p}/10\t"
            f"{p-base:+d}"
        )

    print()
    print("DIRECTION TOTALS")

    for direction in ("de-fr", "fr-de"):
        selected = [
            row
            for row in rows
            if row["direction"] == direction
        ]

        p = sum(
            row["outcome"] == "pass"
            for row in selected
        )

        print(
            f"{direction}: "
            f"{p}/{len(selected)}"
        )

    print()
    print("PER ROUND")

    for direction in ("de-fr", "fr-de"):
        print(direction)

        for n in range(1, 11):
            selected = [
                row
                for row in rows
                if (
                    row["direction"] == direction
                    and row["round"] == n
                )
            ]

            p = sum(
                row["outcome"] == "pass"
                for row in selected
            )

            print(
                f"  {n}: "
                f"{p}/{len(selected)}"
            )

    print()
    print("FAILED RESPONSES")

    for row in rows:
        if row["outcome"] == "pass":
            continue

        print()

        print(
            f"direction={row['direction']} "
            f"round={row['round']} "
            f"case={row['case_id']} "
            "fail="
            f"{','.join(row.get('failure_kinds', [])) or '-'}"
        )

        print(
            row.get("response", "")
        )


if __name__ == "__main__":
    main()
PY

    chmod 700 "$OUT/setup/evaluate.py"

    python3 -m py_compile \
        "$OUT/setup/evaluate.py"
}


run_direction() {
    local direction="$1"
    local source_lang="$2"
    local prompt_file="$3"

    local n
    local dir
    local payload_dir
    local raw_dir
    local case_id
    local text
    local payload
    local raw

    printf '\n'
    printf \
        '===== applying explicit %s role =====\n' \
        "$direction"

    unload_main
    apply_prompt "$direction" "$prompt_file"
    unload_main

    for n in $(seq 1 10); do
        printf \
            '\n===== %s round %s =====\n' \
            "$direction" \
            "$n"

        dir="$OUT/runs/$direction/$n"
        payload_dir="$dir/payloads"
        raw_dir="$dir/raw"

        mkdir -p \
            "$payload_dir" \
            "$raw_dir"

        unload_main

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
                "$payload" |
                jq . \
                > "$raw"
            then
                printf \
                    'ERROR: request failed: %s round=%s case=%s\n' \
                    "$direction" \
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
                    'ERROR: malformed response: %s round=%s case=%s\n' \
                    "$direction" \
                    "$n" \
                    "$case_id" \
                    >&2

                cat "$raw" >&2 || true
                return 21
            fi

        done < <(
            jq -r \
                --arg lang "$source_lang" \
                '
                .[]
                | select(.source_language == $lang)
                | [.id, .input]
                | @tsv
                ' \
                "$FIXTURE"
        )

        unload_main
    done
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

root = Path(sys.argv[2])

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
        hits.append(str(path))


if hits:
    print(
        "ERROR: token found in evidence:",
        file=sys.stderr,
    )

    for hit in hits:
        print(hit, file=sys.stderr)

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

    unload_main >/dev/null 2>&1 || true

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

    python3 \
        "$OUT/setup/evaluate.py" \
        --benchmark "$BENCH" \
        --fixture "$FIXTURE" \
        --root "$OUT" \
        --model "$MODEL" \
        > "$OUT/aggregate.txt" \
        2>&1 || true

    if [[ -n "$HEADER_FILE" ]]; then
        sudo rm -f "$HEADER_FILE" || true
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
    printf \
        '================ BATCH 3C SUMMARY ================\n'

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
        printf \
            '\nCRITICAL: preset restoration FAILED.\n' \
            >&2
    fi

    exit "$rc"
}


trap finalize EXIT


if ! systemctl is-active --quiet ollama.service; then
    echo 'ERROR: ollama.service is not active.' >&2
    exit 1
fi


if ! systemctl is-active --quiet open-webui.service; then
    echo 'ERROR: open-webui.service is not active.' >&2
    exit 1
fi


if [[ ! -r "$FIXTURE" || ! -r "$BENCH" ]]; then
    echo 'ERROR: fixture/benchmark unavailable.' >&2
    exit 1
fi


capture_state "$OUT/setup/state-before"


sha256sum \
    "$FIXTURE" \
    "$BENCH" \
    > "$OUT/setup/benchmark-contract.sha256"


cp \
    "$FIXTURE" \
    "$OUT/setup/translation-office.json"


#
# Capture the model definition as seen by Ollama so that this experiment
# proves the underlying model parameters/system were not changed.
#
jq -n \
    --arg model "${MODEL}:latest" \
    '{model: $model}' \
    > "$OUT/setup/ollama-show-request.json"

curl -fsS \
    -H 'Content-Type: application/json' \
    --data-binary @"$OUT/setup/ollama-show-request.json" \
    "$MAIN_URL/api/show" |
    jq . \
    > "$OUT/setup/ollama-model-show.json"


#
# Save exact original Open WebUI preset.
#
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
        'ERROR: expected translation preset/base model not found.' \
        >&2

    exit 1
fi


ORIGINAL_SAVED=1


#
# Fixed-direction candidate prompts.
# No language auto-detection.
# No Erhalt/reception special case.
# No fixture-specific vocabulary.
#
cat > "$OUT/setup/system-de-fr.txt" <<'EOF'
You are a dedicated professional German-to-French translator for office and business documents.

Translate the user's German source text into French. The source language for this role is German and the target language is French. The final translation must be in French, never German.

Translate directly and completely. Translate every ordinary-language source word; leave untranslated only names, identifiers, reference numbers, amounts, and dates. Preserve meaning, tone, register, terminology, negations, qualifications, lists, tables, and formatting.

Do not summarize, explain, compare, correct, paraphrase, or add commentary. Do not invent facts absent from the source. Return only the French translation.
EOF


cat > "$OUT/setup/system-fr-de.txt" <<'EOF'
You are a dedicated professional French-to-German translator for office and business documents.

Translate the user's French source text into German. The source language for this role is French and the target language is German. The final translation must be in German, never French.

Translate directly and completely. Translate every ordinary-language source word; leave untranslated only names, identifiers, reference numbers, amounts, and dates. Preserve meaning, tone, register, terminology, negations, qualifications, lists, tables, and formatting.

Do not summarize, explain, compare, correct, paraphrase, or add commentary. Do not invent facts absent from the source. Return only the German translation.
EOF


cat > "$OUT/setup/README.txt" <<'EOF'
Batch 3C: explicit Open WebUI translation roles

Purpose:
- Test whether the product should stop auto-detecting DE/FR direction.
- Use a fixed German -> French system role for the four German fixtures.
- Use a fixed French -> German system role for the four French fixtures.
- 10 runs per fixture, 80 total translations.

Unchanged:
- LFM base model
- Ollama model parameters
- temperature/sampling
- installed fixture
- installed evaluator
- source inputs
- Open WebUI completion API

Not present:
- no Erhalt/reception hint
- no invoice-specific hint
- no fixture-specific terminology
- no evaluator change

The existing bc250-office-translation preset is modified only temporarily.
The exact original preset is restored automatically.
EOF


write_evaluator


run_direction \
    'de-fr' \
    'de' \
    "$OUT/setup/system-de-fr.txt"


run_direction \
    'fr-de' \
    'fr' \
    "$OUT/setup/system-fr-de.txt"


python3 \
    "$OUT/setup/evaluate.py" \
    --benchmark "$BENCH" \
    --fixture "$FIXTURE" \
    --root "$OUT" \
    --model "$MODEL" \
    > "$OUT/aggregate.txt"


cat "$OUT/aggregate.txt"
