# Isolated Open WebUI task model

`bc250-setup-task-model` creates `ollama-task.service` on port `11435`, gives it
a separate model store, and registers
`task-gemma3-1b-unsloth-ud-q4-k-xl`. The model unloads after every request. The
RPM installs the helper but does not create or enable the service automatically.

```bash
sudo bc250-setup-task-model
```

From a source checkout:

```bash
sudo ./models/task-model/setup-ollama.sh
```

Supported overrides are `TASK_BIND` (`0.0.0.0`), `TASK_PORT` (`11435`),
`TASK_MODEL_REVISION`, `TASK_MODEL_SHA256`, `HF_TOKEN` and `HF_HOME`. A revision
may be a commit, tag, branch or `latest`.

Keep port `11435` blocked from the LAN. Add this Open WebUI connection:

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
sudo rm -rf /var/lib/bc250-llm-server/ollama/task \
  /var/lib/bc250-llm-server/gguf/task \
  /var/lib/bc250-llm-server/modelfiles/task
```
