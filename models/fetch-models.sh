#!/usr/bin/env bash
# Select, download and register production models from the editable source list.
set -Eeuo pipefail
umask 0027

SOURCE_FILE="${SOURCE_FILE:-/etc/bc250-llm-server/model-sources.sh}"
MODELFILE_SOURCE_DIR="${MODELFILE_SOURCE_DIR:-/usr/share/bc250-llm-server/models}"
DEST="${DEST:-/var/llm/gguf}"
MODELFILE_DIR="${MODELFILE_DIR:-/var/llm/modelfiles}"
HF_HOME="${HF_HOME:-/var/llm/hf-cache}"
DOWNLOAD_DIR="${DOWNLOAD_DIR:-$HF_HOME/downloads/models}"
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"

[[ $EUID -eq 0 ]] || { echo "ERROR: run with sudo." >&2; exit 1; }
[[ -r "$SOURCE_FILE" ]] || { echo "ERROR: cannot read $SOURCE_FILE" >&2; exit 1; }

names=()
repos=()
revisions=()
files=()
modelfiles=()
model() {
  [[ $# -eq 5 ]] || { echo "ERROR: bad model entry in $SOURCE_FILE" >&2; exit 1; }
  names+=("$1")
  repos+=("$2")
  revisions+=("$3")
  files+=("$4")
  modelfiles+=("$5")
}
# shellcheck source=/dev/null
source "$SOURCE_FILE"

if ((${#names[@]} == 0)); then
  echo "No models are enabled. Uncomment examples in $SOURCE_FILE and run again."
  exit 0
fi

for cmd in awk curl hf ollama runuser; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $cmd" >&2
    exit 1
  }
done
id ollama >/dev/null 2>&1 || { echo "ERROR: ollama user missing." >&2; exit 1; }
OLLAMA_BIN="$(command -v ollama)"

declare -A seen_names=() seen_modelfiles=()
for i in "${!names[@]}"; do
  [[ -z "${seen_names[${names[$i]}]+x}" ]] || {
    echo "ERROR: duplicate model name: ${names[$i]}" >&2
    exit 1
  }
  [[ -z "${seen_modelfiles[${modelfiles[$i]}]+x}" ]] || {
    echo "ERROR: duplicate Modelfile: ${modelfiles[$i]}" >&2
    exit 1
  }
  seen_names["${names[$i]}"]=1
  seen_modelfiles["${modelfiles[$i]}"]=1
done

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

echo "Available models:"
for i in "${!names[@]}"; do
  printf '  %2d) %s\n' "$i" "${names[$i]}"
done
selection="${1:-}"
[[ -n "$selection" ]] || read -rp "Indices (e.g. 0,2-4) or Enter for all: " selection

selected=()
if [[ -z "${selection// }" || "$selection" == all ]]; then
  selected=("${!names[@]}")
else
  last_index=$((${#names[@]} - 1))
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
((${#selected[@]})) || { echo "No valid models selected." >&2; exit 1; }

curl -fsS "http://$OLLAMA_HOST/api/tags" >/dev/null || {
  echo "ERROR: Ollama is not reachable at $OLLAMA_HOST." >&2
  exit 1
}
install -d -o ollama -g ollama -m 0750 \
  "$DEST" "$HF_HOME" "$HF_HOME/hub" "$HF_HOME/downloads" "$DOWNLOAD_DIR"
install -d -o root -g ollama -m 0750 "$MODELFILE_DIR"

failures=()
for i in "${selected[@]}"; do
  name="${names[$i]}"
  repo="${repos[$i]}"
  revision="${revisions[$i]}"
  file="${files[$i]}"
  modelfile="${modelfiles[$i]}"
  source_modelfile="$MODELFILE_SOURCE_DIR/$modelfile"
  target_modelfile="$MODELFILE_DIR/$modelfile"
  output="$DEST/$file"
  staged="$DOWNLOAD_DIR/$file"

  echo
  echo ">>> $name"
  if [[ ! -r "$source_modelfile" ]]; then
    echo "    ERROR: missing $source_modelfile" >&2
    failures+=("$name")
    continue
  fi
  if [[ "$(awk '$1=="FROM" {print $2; exit}' "$source_modelfile")" != "$output" ]]; then
    echo "    ERROR: FROM path in $modelfile does not match $output" >&2
    failures+=("$name")
    continue
  fi
  declared_name="$(awk -F': ' '/^# Ollama model:/ {print $2; exit}' "$source_modelfile")"
  if [[ "$declared_name" != "$name" ]]; then
    echo "    ERROR: $modelfile declares '$declared_name', expected '$name'" >&2
    failures+=("$name")
    continue
  fi

  if [[ -s "$output" ]]; then
    echo "    GGUF exists, skipping download"
  else
    install -d -o ollama -g ollama -m 0750 "$(dirname "$staged")"
    revision_args=()
    [[ "$revision" == latest ]] || revision_args=(--revision "$revision")
    if ! runuser -u ollama -- env \
      HOME=/var/lib/ollama \
      HF_TOKEN="$HF_TOKEN" \
      HF_HOME="$HF_HOME" \
      HF_HUB_CACHE="$HF_HOME/hub" \
      HF_HUB_DISABLE_XET=1 \
      hf download "$repo" "$file" "${revision_args[@]}" --local-dir "$DOWNLOAD_DIR"; then
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
  install -o root -g ollama -m 0640 "$source_modelfile" "$target_modelfile"
  if runuser -u ollama -- env OLLAMA_HOST="$OLLAMA_HOST" \
      "$OLLAMA_BIN" create "$name" -f "$target_modelfile"; then
    echo "    installed"
  else
    echo "    ERROR: ollama create failed" >&2
    failures+=("$name")
  fi
done

env OLLAMA_HOST="$OLLAMA_HOST" "$OLLAMA_BIN" list
if ((${#failures[@]})); then
  printf '\nFailed: %s\n' "${failures[*]}" >&2
  exit 2
fi
printf '\nDone: %d model(s) downloaded and installed.\n' "${#selected[@]}"
