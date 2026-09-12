#!/usr/bin/env bash
# Lightweight post-install asset smoke check. It does not download models,
# exercise GPU runtime, or perform release qualification.
set -Eeuo pipefail

SHARE='/usr/share/bc250-llm-server'
MODEL_DIR="$SHARE/model-management/modelfiles"
QUALITY_DIR="$SHARE/quality-checks"

need_file() {
    [[ -f "$1" ]] || { printf 'MISSING: %s\n' "$1" >&2; return 1; }
    printf 'ok: %s\n' "$1"
}

need_exec() {
    need_file "$1"
    [[ -x "$1" ]] || { printf 'NOT EXECUTABLE: %s\n' "$1" >&2; return 1; }
}

rpm -q --qf 'package: %{NAME} %{VERSION}-%{RELEASE} %{ARCH}\n' bc250-llm-server
need_file "$SHARE/model-management/retired-models.json"

for name in \
  task-lfm25-1.2b-instruct-liquidai-q6-k.Modelfile \
  task-gemma3-1b-unsloth-ud-q4-k-xl.Modelfile \
  exp-hunyuan-mt-7b-mungert-q4-k-m.Modelfile \
  exp-translate-gemma4-sub-e4b-17s-q4-k-xl.Modelfile
do
    need_file "$MODEL_DIR/$name"
done

for path in \
  "$QUALITY_DIR/task/10-candidate-screen.sh" \
  "$QUALITY_DIR/translation/10-direct-candidate-screen.sh" \
  "$QUALITY_DIR/translation/11-ministral-direct.sh" \
  "$QUALITY_DIR/translation/12-hunyuan-direct.sh" \
  "$QUALITY_DIR/translation/13-translate-gemma-direct.sh" \
  "$QUALITY_DIR/translation/14-lfm-direct-reference.sh" \
  "$QUALITY_DIR/translation/20-owui-candidate-screen.sh" \
  "$QUALITY_DIR/translation/21-hunyuan-owui.sh" \
  "$QUALITY_DIR/translation/22-translate-gemma-owui.sh" \
  "$QUALITY_DIR/translation/23-lfm-owui-reference.sh" \
  "$QUALITY_DIR/utils/inspect-latest-evidence.sh"
do
    need_file "$path"
    [[ -x "$path" ]] || { printf 'NOT EXECUTABLE: %s\n' "$path" >&2; exit 1; }
done

need_exec "$QUALITY_DIR/translation/owui-provider-config.py"
need_file "$QUALITY_DIR/translation/prompts/auto-direction-minimal.txt"
need_file "$QUALITY_DIR/translation/prompts/auto-direction-translate-gemma.txt"

# Discovery is source-only here: no GGUF download and no registration mutation.
tmp_task=/tmp/bc250-quality-task-list.$$
tmp_exp=/tmp/bc250-quality-model-list.$$
sudo bc250-model list task > "$tmp_task" 2>&1
sudo bc250-model list experiments > "$tmp_exp" 2>&1
trap 'rm -f "$tmp_task" "$tmp_exp"' EXIT
for model in \
  task-lfm25-1.2b-instruct-liquidai-q6-k \
  task-gemma3-1b-unsloth-ud-q4-k-xl
do
    grep -Fq "$model" "$tmp_task" || {
        printf 'NOT DISCOVERED: %s\n' "$model" >&2
        exit 1
    }
done
for model in \
  exp-hunyuan-mt-7b-mungert-q4-k-m \
  exp-translate-gemma4-sub-e4b-17s-q4-k-xl
do
    grep -Fq "$model" "$tmp_exp" || {
        printf 'NOT DISCOVERED: %s\n' "$model" >&2
        exit 1
    }
done
for retired in \
  exp-lfm25-1.2b-instruct-liquidai-q6-k \
  exp-minicpm5-2b-openbmb-q4-k-m \
  exp-qwen3-1.7b-ggml-q4-k-m \
  exp-qwen38-2b-distill-empero-q6-k \
  exp-qwen38-4b-distill-empero-q6-k
do
    if grep -Fq "$retired" "$tmp_exp"; then
        printf 'RETIRED MODEL STILL DISCOVERABLE: %s\n' "$retired" >&2
        exit 1
    fi
done
jq -e '
  .task.TASK_MODEL == "task-lfm25-1.2b-instruct-liquidai-q6-k:latest"
  and (.task.TITLE_GENERATION_PROMPT_TEMPLATE | type == "string" and length > 0)
  and (.task.TAGS_GENERATION_PROMPT_TEMPLATE | type == "string" and length > 0)
  and (.task.QUERY_GENERATION_PROMPT_TEMPLATE | type == "string" and length > 0)
' "$SHARE/openwebui/desired-state.json" >/dev/null || {
    printf 'INVALID: package-owned task model/prompt desired state\n' >&2
    exit 1
}
printf 'PASS: packaged quality assets, task default, prompt policy and active candidate discovery are present.\n'
