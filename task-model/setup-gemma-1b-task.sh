#!/usr/bin/env bash
# Optional isolated Ollama instance for Open WebUI task/title generation.
set -Eeuo pipefail
umask 0027

[[ ${EUID} -eq 0 ]] || {
  echo "ERROR: run with sudo." >&2
  exit 1
}

# Defaults:
# TASK_BIND=0.0.0.0
# TASK_PORT=11435
BIND="${TASK_BIND:-0.0.0.0}"
PORT="${TASK_PORT:-11435}"

SERVICE="ollama-task.service"
MODEL_NAME="${TASK_MODEL_NAME:-task-gemma3-1b-unsloth-ud-q4-k-xl}"
MODEL_DIR="/var/llm/ollama-task"
MODEL_REPO="unsloth/gemma-3-1b-it-GGUF"
MODEL_REVISION="${TASK_MODEL_REVISION:-latest}"
MODEL_FILE="gemma-3-1b-it-UD-Q4_K_XL.gguf"
MODEL_SHA256="${TASK_MODEL_SHA256:-}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MODELFILE="$SCRIPT_DIR/Modelfile"

for cmd in awk curl getent hf install ollama readlink runuser sha256sum systemctl usermod; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $cmd" >&2
    exit 1
  }
done

id ollama >/dev/null 2>&1 || {
  echo "ERROR: ollama user missing." >&2
  exit 1
}

[[ -r "$MODELFILE" ]] || {
  echo "ERROR: missing Modelfile: $MODELFILE" >&2
  exit 1
}

[[ "$PORT" =~ ^[0-9]{1,5}$ ]] && ((PORT >= 1 && PORT <= 65535)) || {
  echo "ERROR: invalid TASK_PORT: $PORT" >&2
  exit 1
}

OLLAMA_BIN="$(readlink -f "$(command -v ollama)")"
CHECK_HOST="$BIND"
[[ "$CHECK_HOST" == "0.0.0.0" ]] && CHECK_HOST="127.0.0.1"

for group in render video; do
  getent group "$group" >/dev/null || {
    echo "ERROR: required GPU group missing: $group" >&2
    exit 1
  }
  usermod -aG "$group" ollama
done

install -d -o ollama -g ollama -m 0750 "$MODEL_DIR" /var/llm/hf-cache
MODEL_PATH="$MODEL_DIR/$MODEL_FILE"
verify_model() {
  [[ -z "$MODEL_SHA256" ]] || printf '%s  %s\n' "$MODEL_SHA256" "$MODEL_PATH" | sha256sum --check --strict -
}
if [[ -s "$MODEL_PATH" ]]; then
  verify_model || {
    echo "ERROR: existing task-model GGUF has the wrong checksum: $MODEL_PATH" >&2
    exit 1
  }
else
  revision_args=()
  [[ "$MODEL_REVISION" == latest ]] || revision_args=(--revision "$MODEL_REVISION")
  runuser -u ollama -- env \
    HOME=/var/lib/ollama \
    HF_TOKEN="${HF_TOKEN:-}" \
    HF_HOME=/var/llm/hf-cache \
    HF_HUB_CACHE=/var/llm/hf-cache/hub \
    HF_HUB_DISABLE_XET=1 \
    hf download "$MODEL_REPO" "$MODEL_FILE" \
      "${revision_args[@]}" --local-dir "$MODEL_DIR"
  verify_model
fi
[[ -n "$MODEL_SHA256" ]] || echo "No checksum configured; using revision '$MODEL_REVISION'."
chown root:ollama "$MODEL_PATH"
chmod 0640 "$MODEL_PATH"

cat > "/etc/systemd/system/$SERVICE" <<EOF
[Unit]
Description=Ollama task-model instance
After=cyan-skillfish-governor-smu.service
Wants=cyan-skillfish-governor-smu.service

[Service]
Type=simple
User=ollama
Group=ollama
SupplementaryGroups=render video
ExecStart=$OLLAMA_BIN serve
Restart=always
RestartSec=3
PrivateTmp=true
ProtectHome=true
ProtectSystem=full
NoNewPrivileges=true
Environment="HOME=$MODEL_DIR"
Environment="OLLAMA_VULKAN=1"
Environment="GGML_VK_VISIBLE_DEVICES=0"
Environment="OLLAMA_IGPU_ENABLE=1"
Environment="OLLAMA_HOST=$BIND:$PORT"
Environment="OLLAMA_MODELS=$MODEL_DIR"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_KEEP_ALIVE=0"
Environment="OLLAMA_CONTEXT_LENGTH=4096"
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "$SERVICE"

for _ in {1..30}; do
  curl -fsS "http://$CHECK_HOST:$PORT/api/tags" >/dev/null && break
  sleep 1
done

curl -fsS "http://$CHECK_HOST:$PORT/api/tags" >/dev/null || {
  systemctl status "$SERVICE" --no-pager
  exit 1
}

export OLLAMA_HOST="$CHECK_HOST:$PORT"
declared_name="$(awk -F': ' '/^# Ollama model:/ {print $2; exit}' "$MODELFILE")"
[[ "$declared_name" == "$MODEL_NAME" ]] || {
  echo "ERROR: Modelfile declares '$declared_name', expected '$MODEL_NAME'." >&2
  exit 1
}
runuser -u ollama -- env HOME="$MODEL_DIR" OLLAMA_HOST="$OLLAMA_HOST" \
  "$OLLAMA_BIN" create "$MODEL_NAME" -f "$MODELFILE"

systemctl restart "$SERVICE"

echo
echo "Installed $MODEL_NAME on $BIND:$PORT."
echo "Keep TCP port $PORT blocked from the LAN."
echo "Open WebUI connection: http://host.containers.internal:$PORT"
