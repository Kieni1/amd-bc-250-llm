#!/usr/bin/env bash
# Configure an isolated task or coding-agent Ollama service and its models.
set -Eeuo pipefail
umask 0027

usage() {
  echo "Usage: setup-ollama-instance.sh task|coding" >&2
}

[[ ${EUID} -eq 0 ]] || { echo "ERROR: run with sudo." >&2; exit 1; }
[[ $# -eq 1 ]] || { usage; exit 2; }
kind="$1"

case "$kind" in
  task)
    label="task-model"
    category="task"
    bind="${TASK_BIND:-0.0.0.0}"
    port="${TASK_PORT:-11435}"
    service="ollama-task.service"
    gguf_root="/var/lib/bc250-llm-server/gguf/task"
    models_root="/var/lib/bc250-llm-server/ollama/task"
    modelfile_root="/var/lib/bc250-llm-server/modelfiles/task"
    context=4096
    keep_alive=0
    selection="${TASK_MODEL_SELECTION:-all}"
    ;;
  coding)
    label="coding-agent"
    category="coding"
    bind="${CODING_AGENT_BIND:-0.0.0.0}"
    port="${CODING_AGENT_PORT:-11436}"
    service="ollama-agent.service"
    gguf_root="/var/lib/bc250-llm-server/gguf/agent"
    models_root="/var/lib/bc250-llm-server/ollama/agent"
    modelfile_root="/var/lib/bc250-llm-server/modelfiles/agent"
    context=32768
    keep_alive=5m
    selection="${CODING_AGENT_SELECTION:-all}"
    ;;
  *) usage; exit 2 ;;
esac

[[ "$port" =~ ^[0-9]{1,5}$ ]] && ((port >= 1 && port <= 65535)) || {
  echo "ERROR: invalid $label port: $port" >&2
  exit 1
}

for command in curl getent install ollama readlink systemctl usermod; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $command" >&2
    exit 1
  }
done
id ollama >/dev/null 2>&1 || {
  echo "ERROR: ollama user missing; run bc250-install-ollama first." >&2
  exit 1
}
for group in render video; do
  getent group "$group" >/dev/null || {
    echo "ERROR: required GPU group missing: $group" >&2
    exit 1
  }
  usermod -aG "$group" ollama
done

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x /usr/libexec/bc250-llm-server/modelctl ]]; then
  manager="${MODEL_MANAGER:-/usr/libexec/bc250-llm-server/modelctl}"
  source_file="${SOURCE_FILE:-/usr/share/bc250-llm-server/model-management/sources/$category.toml}"
  modelfile_dir="${MODELFILE_SOURCE_DIR:-/usr/share/bc250-llm-server/model-management/modelfiles}"
else
  manager="${MODEL_MANAGER:-$script_dir/modelctl.py}"
  source_file="${SOURCE_FILE:-$script_dir/sources/$category.toml}"
  modelfile_dir="${MODELFILE_SOURCE_DIR:-$script_dir/modelfiles}"
fi
[[ -x "$manager" ]] || { echo "ERROR: model manager is not executable: $manager" >&2; exit 1; }

ollama_bin="$(readlink -f "$(command -v ollama)")"
check_host="$bind"
[[ "$check_host" == 0.0.0.0 ]] && check_host=127.0.0.1
install -d -o ollama -g ollama -m 0750 "$gguf_root" "$models_root"
install -d -o root -g ollama -m 0750 "$modelfile_root"

cat > "/etc/systemd/system/$service" <<EOF
[Unit]
Description=Ollama $label instance
After=cyan-skillfish-governor-smu.service
Wants=cyan-skillfish-governor-smu.service

[Service]
Type=simple
User=ollama
Group=ollama
SupplementaryGroups=render video
ExecStart=$ollama_bin serve
Restart=always
RestartSec=3
PrivateTmp=true
ProtectHome=true
ProtectSystem=full
NoNewPrivileges=true
Environment="HOME=/var/lib/ollama"
Environment="OLLAMA_VULKAN=1"
Environment="GGML_VK_VISIBLE_DEVICES=0"
Environment="OLLAMA_IGPU_ENABLE=1"
Environment="OLLAMA_HOST=$bind:$port"
Environment="OLLAMA_MODELS=$models_root"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_KEEP_ALIVE=$keep_alive"
Environment="OLLAMA_CONTEXT_LENGTH=$context"
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "$service"
for _ in {1..30}; do
  curl -fsS --connect-timeout 2 "http://$check_host:$port/api/tags" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "http://$check_host:$port/api/tags" >/dev/null || {
  systemctl status "$service" --no-pager
  exit 1
}

manager_args=(
  install "$category" "$selection"
  --source "$source_file"
  --modelfile-dir "$modelfile_dir"
  --host "$check_host:$port"
)
if [[ "$kind" == task ]]; then
  [[ -n "${TASK_MODEL_REVISION:-}" ]] && manager_args+=(--revision "$TASK_MODEL_REVISION")
  [[ -n "${TASK_MODEL_SHA256:-}" ]] && manager_args+=(--sha256 "$TASK_MODEL_SHA256")
else
  [[ -n "${CODING_AGENT_REVISION:-}" ]] && manager_args+=(--revision "$CODING_AGENT_REVISION")
  [[ -n "${CODING_AGENT_SHA256:-}" ]] && manager_args+=(--sha256 "$CODING_AGENT_SHA256")
  [[ -n "${CODING_AGENT_GGUF_DIR:-}" ]] && manager_args+=(--destination "$CODING_AGENT_GGUF_DIR")
  [[ -n "${CODING_AGENT_MIN_FREE_BYTES:-}" ]] && manager_args+=(--min-free-bytes "$CODING_AGENT_MIN_FREE_BYTES")
fi
"$manager" "${manager_args[@]}"
systemctl restart "$service"

echo
echo "Installed $label on $bind:$port."
echo "Keep TCP port $port blocked from the LAN."
echo "Open WebUI connection: http://host.containers.internal:$port"
