#!/usr/bin/env bash
# Select, download and register entries from the editable experiment source list.
set -Eeuo pipefail
umask 0027

SOURCE_FILE="${SOURCE_FILE:-/etc/bc250-llm-server/experiment-sources.sh}"
MODELFILE_SOURCE_DIR="${MODELFILE_SOURCE_DIR:-/usr/share/bc250-llm-server/experiments}"
DEST="${DEST:-/var/llm/gguf-experiments}"
MODELFILE_DIR="${MODELFILE_DIR:-/var/llm/modelfiles-experiments}"
HF_HOME="${HF_HOME:-/var/llm/hf-cache}"
DOWNLOAD_DIR="${DOWNLOAD_DIR:-$HF_HOME/downloads/experiments}"
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"

[[ $EUID -eq 0 ]] || { echo "ERROR: run with sudo." >&2; exit 1; }
[[ -r "$SOURCE_FILE" ]] || { echo "ERROR: cannot read $SOURCE_FILE" >&2; exit 1; }

kinds=()
ids=()
names=()
repos=()
revisions=()
files=()
modelfiles=()
contexts=()
drafts=()
add_entry() {
  kinds+=("$1"); ids+=("$2"); names+=("$3"); repos+=("$4")
  revisions+=("$5"); files+=("$6"); modelfiles+=("$7")
  contexts+=("$8"); drafts+=("$9")
}
ollama_model() {
  [[ $# -eq 6 ]] || { echo "ERROR: bad ollama_model entry in $SOURCE_FILE" >&2; exit 1; }
  add_entry ollama "$1" "$2" "$3" "$4" "$5" "$6" "" ""
}
mtp_model() {
  [[ $# -eq 6 ]] || { echo "ERROR: bad mtp_model entry in $SOURCE_FILE" >&2; exit 1; }
  add_entry mtp "$1" "$1" "$2" "$3" "$4" "" "$5" "$6"
}
# shellcheck source=/dev/null
source "$SOURCE_FILE"

if ((${#ids[@]} == 0)); then
  echo "No experiments are enabled. Uncomment examples in $SOURCE_FILE and run again."
  exit 0
fi

for cmd in awk hf runuser; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $cmd" >&2
    exit 1
  }
done

declare -A seen_ids=() seen_names=() seen_modelfiles=()
for i in "${!ids[@]}"; do
  id="${ids[$i]}"
  name="${names[$i]}"
  kind="${kinds[$i]}"
  [[ -z "${seen_ids[$id]+x}" ]] || { echo "ERROR: duplicate experiment ID: $id" >&2; exit 1; }
  seen_ids["$id"]=1

  if [[ "$kind" == ollama ]]; then
    modelfile="${modelfiles[$i]}"
    source_modelfile="$MODELFILE_SOURCE_DIR/$modelfile"
    [[ "$name" == exp-* ]] || { echo "ERROR: name must start with exp-: $name" >&2; exit 1; }
    [[ -z "${seen_names[$name]+x}" ]] || { echo "ERROR: duplicate model name: $name" >&2; exit 1; }
    [[ -z "${seen_modelfiles[$modelfile]+x}" ]] || { echo "ERROR: duplicate Modelfile: $modelfile" >&2; exit 1; }
    seen_names["$name"]=1
    seen_modelfiles["$modelfile"]=1
    [[ -r "$source_modelfile" ]] || { echo "ERROR: missing $source_modelfile" >&2; exit 1; }
    declared_name="$(awk -F': ' '/^# Ollama model:/ {print $2; exit}' "$source_modelfile")"
    [[ "$declared_name" == "$name" ]] || {
      echo "ERROR: $modelfile declares '$declared_name', expected '$name'" >&2
      exit 1
    }
  fi
done

echo "Available experiments:"
for i in "${!ids[@]}"; do
  printf '  %2d) %-48s [%s]\n' "$i" "${names[$i]}" "${kinds[$i]}"
done
[[ "${1:-}" == --list ]] && exit 0

HF_TOKEN="${HF_TOKEN:-}"
if [[ -z "$HF_TOKEN" ]] && { exec 3<>/dev/tty; } 2>/dev/null; then
  read -r -s -u 3 -p "Hugging Face token (Enter for none): " HF_TOKEN || true
  printf '\n' >&3
  exec 3>&-
fi
if [[ -n "$HF_TOKEN" ]] && ! env HF_TOKEN="$HF_TOKEN" hf auth whoami >/dev/null 2>&1; then
  echo "WARNING: token was not accepted; continuing without it." >&2
  HF_TOKEN=""
fi

selection="${1:-}"
[[ -n "$selection" ]] || read -rp "Indices (e.g. 0,2-4) or Enter for all: " selection
selected=()
if [[ -z "${selection// }" || "$selection" == all ]]; then
  selected=("${!ids[@]}")
else
  last_index=$((${#ids[@]} - 1))
  IFS=',' read -ra parts <<< "$selection"
  for part in "${parts[@]}"; do
    part="${part// }"
    if [[ "$part" =~ ^([0-9]+)-([0-9]+)$ ]]; then
      start=$((10#${BASH_REMATCH[1]}))
      end=$((10#${BASH_REMATCH[2]}))
      ((start <= end)) || { tmp=$start; start=$end; end=$tmp; }
      if ((start > last_index)); then
        echo "WARNING: selection '$part' is outside 0-$last_index; ignoring it." >&2
        continue
      fi
      if ((end > last_index)); then
        echo "WARNING: selection '$part' extends beyond $last_index; truncating it." >&2
        end=$last_index
      fi
      for ((i=start; i<=end; i++)); do
        selected+=("$i")
      done
    elif [[ "$part" =~ ^[0-9]+$ ]]; then
      i=$((10#$part))
      if ((i <= last_index)); then
        selected+=("$i")
      else
        echo "WARNING: selection '$part' is outside 0-$last_index; ignoring it." >&2
      fi
    else
      echo "WARNING: invalid selection '$part'; ignoring it." >&2
    fi
  done
fi
mapfile -t selected < <(printf '%s\n' "${selected[@]}" | awk 'NF && !seen[$0]++')
((${#selected[@]})) || { echo "No valid experiments selected." >&2; exit 1; }

needs_ollama=0
for i in "${selected[@]}"; do
  [[ "${kinds[$i]}" == ollama ]] && needs_ollama=1
done
if ((needs_ollama)); then
  for cmd in curl ollama; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: missing $cmd" >&2; exit 1; }
  done
  id ollama >/dev/null 2>&1 || { echo "ERROR: ollama user missing." >&2; exit 1; }
  curl -fsS "http://$OLLAMA_HOST/api/tags" >/dev/null || {
    echo "ERROR: Ollama unavailable at $OLLAMA_HOST" >&2
    exit 1
  }
  OLLAMA_BIN="$(command -v ollama)"
  install -d -o root -g ollama -m 0750 "$MODELFILE_DIR"
fi
install -d -o ollama -g ollama -m 0750 \
  "$DEST" "$HF_HOME" "$HF_HOME/hub" "$HF_HOME/downloads" "$DOWNLOAD_DIR"

failures=()
for i in "${selected[@]}"; do
  kind="${kinds[$i]}"
  id="${ids[$i]}"
  name="${names[$i]}"
  repo="${repos[$i]}"
  revision="${revisions[$i]}"
  file="${files[$i]}"
  model_dir="$DEST/$id"
  output="$model_dir/$file"
  download_model_dir="$DOWNLOAD_DIR/$id"
  staged="$download_model_dir/$file"
  install -d -o ollama -g ollama -m 0750 "$model_dir"

  echo
  echo ">>> $name [$kind]"
  if [[ "$kind" == ollama ]]; then
    modelfile="${modelfiles[$i]}"
    source_modelfile="$MODELFILE_SOURCE_DIR/$modelfile"
    target_modelfile="$MODELFILE_DIR/$modelfile"
    if [[ "$(awk '$1=="FROM" {print $2; exit}' "$source_modelfile")" != "$output" ]]; then
      echo "    ERROR: FROM path mismatch" >&2
      failures+=("$name")
      continue
    fi
  fi

  if [[ -s "$output" ]]; then
    echo "    GGUF exists, skipping download"
  else
    install -d -o ollama -g ollama -m 0750 "$download_model_dir" "$(dirname "$staged")"
    revision_args=()
    [[ "$revision" == latest ]] || revision_args=(--revision "$revision")
    if ! runuser -u ollama -- env \
      HOME=/var/lib/ollama \
      HF_TOKEN="$HF_TOKEN" \
      HF_HOME="$HF_HOME" \
      HF_HUB_CACHE="$HF_HOME/hub" \
      HF_HUB_DISABLE_XET=1 \
      hf download "$repo" "$file" "${revision_args[@]}" --local-dir "$download_model_dir"; then
      echo "    ERROR: download failed" >&2
      failures+=("$name")
      continue
    fi
    [[ -s "$staged" ]] || {
      echo "    ERROR: download completed without $staged" >&2
      failures+=("$name")
      continue
    }
    mv -f "$staged" "$output"
  fi

  chown root:ollama "$output"
  chmod 0640 "$output"
  if [[ "$kind" == mtp ]]; then
    echo "    downloaded for llama.cpp"
    continue
  fi

  install -o root -g ollama -m 0640 "$source_modelfile" "$target_modelfile"
  if runuser -u ollama -- env OLLAMA_HOST="$OLLAMA_HOST" \
      "$OLLAMA_BIN" create "$name" -f "$target_modelfile"; then
    echo "    installed"
  else
    echo "    ERROR: ollama create failed" >&2
    failures+=("$name")
  fi
done

((needs_ollama)) && env OLLAMA_HOST="$OLLAMA_HOST" "$OLLAMA_BIN" list
if ((${#failures[@]})); then
  printf '\nFailed: %s\n' "${failures[*]}" >&2
  exit 2
fi
printf '\nDone: %d experiment(s) processed.\n' "${#selected[@]}"
