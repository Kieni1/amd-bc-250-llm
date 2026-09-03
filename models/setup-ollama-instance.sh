#!/usr/bin/env bash
# Configure isolated task, embedding or exclusive agentic Ollama services and models.
set -Eeuo pipefail
umask 0027

usage() {
  echo "Usage: setup-ollama-instance.sh task|embedding|agentic [MODEL-SELECTION]" >&2
}

[[ ${EUID} -eq 0 ]] || { echo "ERROR: run with sudo." >&2; exit 1; }
[[ $# -ge 1 && $# -le 2 ]] || { usage; exit 2; }
kind="$1"
requested_selection="${2:-}"

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
    selection="${requested_selection:-${TASK_MODEL_SELECTION:-}}"
    enable_at_boot=1
    exclusive=0
    ;;
  embedding)
    label="embedding"
    category="embedding"
    bind="${EMBEDDING_BIND:-0.0.0.0}"
    port="${EMBEDDING_PORT:-11437}"
    service="ollama-embedding.service"
    gguf_root="/var/lib/bc250-llm-server/gguf/embedding"
    models_root="/var/lib/bc250-llm-server/ollama/embedding"
    modelfile_root="/var/lib/bc250-llm-server/modelfiles/embedding"
    context=4096
    keep_alive=10m
    selection="${requested_selection:-${EMBEDDING_MODEL_SELECTION:-}}"
    enable_at_boot=1
    exclusive=0
    ;;
  agentic|coding)
    label="coding-agent"
    category="agentic"
    bind="${CODING_AGENT_BIND:-0.0.0.0}"
    port="${CODING_AGENT_PORT:-11436}"
    service="ollama-agent.service"
    gguf_root="/var/lib/bc250-llm-server/gguf/agent"
    models_root="/var/lib/bc250-llm-server/ollama/agent"
    modelfile_root="/var/lib/bc250-llm-server/modelfiles/agent"
    context=32768
    keep_alive=5m
    selection="${requested_selection:-${CODING_AGENT_SELECTION:-}}"
    enable_at_boot=0
    exclusive=1
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
else
  manager="${MODEL_MANAGER:-$script_dir/modelctl.py}"
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
$(if ((exclusive)); then printf '%s\n' 'Conflicts=ollama.service ollama-task.service ollama-embedding.service'; fi)

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
Environment="OLLAMA_NO_CLOUD=1"
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
$(if ((enable_at_boot)); then printf '%s\n' 'WantedBy=multi-user.target'; fi)
EOF

systemctl daemon-reload
if ((enable_at_boot)); then
  systemctl enable --now "$service"
else
  # Agent mode is deliberately exclusive and opt-in. Starting the unit itself
  # stops conflicting normal lanes; setup restores them after registration.
  systemctl disable "$service" >/dev/null 2>&1 || true
  systemctl stop ollama.service ollama-task.service ollama-embedding.service >/dev/null 2>&1 || true
  restore_normal=1
  restore_normal_services() {
    local rc="${1:-0}" normal restore_failed=0
    if ((restore_normal)); then
      if ! systemctl stop "$service"; then
        echo "WARNING: could not stop $service during normal-service restoration." >&2
        restore_failed=1
      fi
      for normal in ollama.service ollama-task.service ollama-embedding.service; do
        systemctl cat "$normal" >/dev/null 2>&1 || continue
        if ! systemctl start "$normal"; then
          echo "WARNING: could not restart $normal during normal-service restoration." >&2
          restore_failed=1
        fi
      done
      restore_normal=0
      if ((restore_failed)); then
        if ((rc)); then
          echo "WARNING: normal-service restoration incomplete; original setup failure status $rc is preserved." >&2
        else
          echo "ERROR: normal-service restoration incomplete after model registration." >&2
        fi
      fi
    fi
    ((rc != 0)) && return "$rc"
    return "$restore_failed"
  }
  trap 'restore_normal_services "$?"' EXIT
  systemctl start "$service"
fi
for _ in {1..30}; do
  curl -fsS --connect-timeout 2 "http://$check_host:$port/api/tags" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "http://$check_host:$port/api/tags" >/dev/null || {
  systemctl status "$service" --no-pager
  exit 1
}

manager_args=(
  install "$category"
)
[[ -z "$selection" ]] || manager_args+=("$selection")
manager_args+=(--host "$check_host:$port")
if [[ "$kind" == task ]]; then
  [[ -n "${TASK_MODEL_REVISION:-}" ]] && manager_args+=(--revision "$TASK_MODEL_REVISION")
  [[ -n "${TASK_MODEL_SHA256:-}" ]] && manager_args+=(--sha256 "$TASK_MODEL_SHA256")
elif [[ "$kind" == embedding ]]; then
  [[ -n "${EMBEDDING_MODEL_REVISION:-}" ]] && manager_args+=(--revision "$EMBEDDING_MODEL_REVISION")
  [[ -n "${EMBEDDING_MODEL_SHA256:-}" ]] && manager_args+=(--sha256 "$EMBEDDING_MODEL_SHA256")
else
  [[ -n "${CODING_AGENT_REVISION:-}" ]] && manager_args+=(--revision "$CODING_AGENT_REVISION")
  [[ -n "${CODING_AGENT_SHA256:-}" ]] && manager_args+=(--sha256 "$CODING_AGENT_SHA256")
  [[ -n "${CODING_AGENT_GGUF_DIR:-}" ]] && manager_args+=(--destination "$CODING_AGENT_GGUF_DIR")
  [[ -n "${CODING_AGENT_MIN_FREE_BYTES:-}" ]] && manager_args+=(--min-free-bytes "$CODING_AGENT_MIN_FREE_BYTES")
fi
"$manager" "${manager_args[@]}"
if ((enable_at_boot)); then
  systemctl restart "$service"
else
  restore_normal_services 0
  trap - EXIT
fi

echo
echo "Installed $label on $bind:$port."
echo "Keep TCP port $port blocked from the LAN."
case "$kind" in
  task) echo "Open WebUI uses this enabled task-only provider for background title/tag work." ;;
  embedding) echo "Open WebUI RAG uses this endpoint directly; it is not exposed as a chat provider." ;;
  *) echo "Agent service is installed disabled and exclusive. Enter with: sudo bc250-agent-mode enter" ;;
esac
