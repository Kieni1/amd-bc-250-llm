# Optional isolated Open WebUI task model

This add-on creates a second Ollama instance for short Open WebUI tasks such as
chat-title generation. It uses a separate model store and unloads after every
request. The RPM installs the files but does not enable the service.

The setup helper follows the repository's default revision and creates the task
model from the local GGUF. Set `TASK_MODEL_REVISION` to a commit, tag or branch
such as `main`; `latest` follows the default revision. Set `TASK_MODEL_SHA256`
when a checksum must be enforced.

## Install

From the RPM:

```bash
sudo bc250-setup-task-model
```

From a source checkout:

```bash
sudo ./task-model/setup-gemma-1b-task.sh
```

Defaults are left here for reference:

```bash
# TASK_BIND=0.0.0.0
# TASK_PORT=11435
sudo TASK_BIND=0.0.0.0 TASK_PORT=11435 bc250-setup-task-model
```

Keep port `11435` blocked from the LAN. In Open WebUI, add:

```text
http://host.containers.internal:11435
```

Set **Task Model (Local)** to
`task-gemma3-1b-unsloth-ud-q4-k-xl:latest`.

## Verify

```bash
curl -fsS http://127.0.0.1:11435/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"model":"task-gemma3-1b-unsloth-ud-q4-k-xl:latest","prompt":"Installing Fedora on a BC-250","stream":false,"keep_alive":0}'
sleep 2
OLLAMA_HOST=127.0.0.1:11435 ollama ps
```

The final command should show no resident task model.

## Remove

```bash
sudo systemctl disable --now ollama-task.service
sudo rm -f /etc/systemd/system/ollama-task.service
sudo systemctl daemon-reload
sudo rm -rf /var/llm/ollama-task
```
