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

rpm -q --qf 'package: %{NAME} %{VERSION}-%{RELEASE} %{ARCH}\n' bc250-llm-server

for name in \
  exp-lfm25-1.2b-instruct-liquidai-q6-k.Modelfile \
  exp-minicpm5-2b-openbmb-q4-k-m.Modelfile \
  exp-qwen3-1.7b-ggml-q4-k-m.Modelfile \
  exp-qwen38-2b-distill-empero-q6-k.Modelfile \
  exp-hunyuan-mt-7b-mungert-q4-k-m.Modelfile \
  exp-translate-gemma4-sub-e4b-17s-q4-k-xl.Modelfile
do
    need_file "$MODEL_DIR/$name"
done

for path in \
  "$QUALITY_DIR/task/10-candidate-screen.sh" \
  "$QUALITY_DIR/task/11-lfm12b.sh" \
  "$QUALITY_DIR/task/12-minicpm5-2b.sh" \
  "$QUALITY_DIR/task/13-qwen3-1p7b.sh" \
  "$QUALITY_DIR/task/14-qwen38-2b.sh" \
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

need_file "$QUALITY_DIR/translation/prompts/auto-direction-minimal.txt"
need_file "$QUALITY_DIR/translation/prompts/auto-direction-translate-gemma.txt"

# Discovery is source-only here: no GGUF download and no registration mutation.
sudo bc250-model list experiments > /tmp/bc250-quality-model-list.$$ 2>&1
trap 'rm -f /tmp/bc250-quality-model-list.$$' EXIT
for model in \
  exp-lfm25-1.2b-instruct-liquidai-q6-k \
  exp-minicpm5-2b-openbmb-q4-k-m \
  exp-qwen3-1.7b-ggml-q4-k-m \
  exp-qwen38-2b-distill-empero-q6-k \
  exp-hunyuan-mt-7b-mungert-q4-k-m \
  exp-translate-gemma4-sub-e4b-17s-q4-k-xl
do
    grep -Fq "$model" /tmp/bc250-quality-model-list.$$ || {
        printf 'NOT DISCOVERED: %s\n' "$model" >&2
        exit 1
    }
done
printf 'PASS: packaged quality assets and candidate discovery are present.\n'
