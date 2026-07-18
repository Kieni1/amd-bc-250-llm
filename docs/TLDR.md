# BC-250 LLM server: fast setup and command reference

This is the short, command-first installation guide for the Fedora 44 testing
RPM. It assumes that Fedora is already installed, updated, reachable over SSH,
and that `bc250-llm-server-0.5.0-0.1.testing.fc44.x86_64.rpm` is in the current
directory.

The package provides the LLM software base. BIOS configuration, cooling,
power-supply sizing and board repair remain operator responsibilities.

The default web interface uses unencrypted HTTP. Use it only on a trusted LAN
until it has been restricted or HTTPS has been configured.

-Replace .rpm with your downloaded version

## Fast installation

Expand the Fedora root logical volume and XFS filesystem:

```bash
sudo lvextend -l +100%FREE /dev/mapper/fedora-root
sudo xfs_growfs /
df -h /
```

Expected: `/` uses the enlarged logical volume. If no free extents remain,
`lvextend` may report that no size change was possible; `xfs_growfs /` is still
safe to run.

Install the RPM:

```bash
sudo dnf in ./bc250-llm-server-0.5.0-0.1.testing.fc44.x86_64.rpm -y
```

Install the newest upstream Ollama release:

```bash
printf 'y\n' | sudo OLLAMA_VERSION=latest bc250-install-ollama
```

To install the version reviewed when v0.5.0 was created instead, use:

```bash
printf 'y\n' | sudo bc250-install-ollama
```

The reviewed v0.5.0 default is Ollama `0.32.1`. `OLLAMA_VERSION=latest` may
install a newer version. The helper does not downgrade or replace an existing
Ollama installation.

Ensure the application services are active:

```bash
sudo systemctl enable --now cyan-skillfish-governor-smu.service
sudo systemctl enable --now ollama.service
sudo systemctl enable --now tika.service
sudo systemctl enable --now open-webui.service
sudo systemctl enable --now nginx.service
```

Apply the reviewed unified-memory and swap profiles:

```bash
sudo BC250_ASSUME_YES=1 bc250-memory-profile apply-full
sudo BC250_ASSUME_YES=1 bc250-swap-profile apply
```

Expected after reboot:

- `ttm.pages_limit=4194304`, a 16 GiB TTM allocation ceiling;
- `ttm.page_pool_size=0`;
- `amdgpu.gttsize=-1`;
- 16 GiB disk swap at priority 10;
- 2 GiB zram at priority 100.

Enable and persist all 40 CUs with the packaged live manager:

```bash
sudo bc250-cu-live-manager --yes enable all
sudo bc250-cu-live-manager --yes write-service-table
sudo bc250-cu-live-manager --yes install-service
sudo reboot
```

Reconnect over SSH after reboot. The live-manager route does not need
`kernel-devel`, an out-of-tree `amdgpu` build or a separate manager download.

## Governor

Edit the operator-controlled governor configuration:

```bash
sudoedit /etc/cyan-skillfish-governor-smu/config.toml
```

The packaged starting range is:

```toml
[frequency-range]
min = 350
max = 2000
```

The packaged 2000 MHz safe point is:

```toml
[[safe-points]]
frequency = 2000
voltage = 960
```

Apply governor changes:

```bash
sudo systemctl restart cyan-skillfish-governor-smu.service
```

Clock, voltage and thermal policy belong to the operator. The CU helpers do not
inspect or restrict the governor configuration.

## Production models

No production model is enabled by default. Uncomment the desired `model` lines:

```bash
sudoedit /etc/bc250-llm-server/model-sources.sh
```

The revision field accepts `latest`, `main`, another branch, a tag or a commit.
`latest` follows the Hugging Face repository's default revision.

Download every enabled entry:

```bash
sudo bc250-fetch-models all </dev/null
```

The Hugging Face token prompt is read from the terminal even with redirected
standard input. Press Enter for public models.

Download selected enabled catalog entries:

```bash
sudo bc250-fetch-models 0
sudo bc250-fetch-models 0,2-4
```

Inspect the registrations:

```bash
ollama list
```

Expected: each name includes the model family, source and quantization.

Remove an obsolete registration only after its replacement has been tested:

```bash
ollama rm OLD_MODEL_NAME
```

## Embedding model

Pull the default `nomic-embed-text` model:

```bash
sudo bc250-pull-embedding-model
```

Select another Ollama embedding model:

```bash
sudo EMBED_MODEL=mxbai-embed-large bc250-pull-embedding-model
```

## Separate task and title model

Install the default isolated task-model instance:

```bash
sudo bc250-setup-task-model
```

Defaults:

- model: `task-gemma3-1b-unsloth-ud-q4-k-xl`;
- bind address: `0.0.0.0` so the Open WebUI container can reach it;
- port: `11435`;
- context: 4096;
- KV cache: `q8_0`;
- keep-alive: zero, so the model unloads after each task.

Follow `main` rather than the default revision:

```bash
sudo TASK_MODEL_REVISION=main bc250-setup-task-model
```

Select a different port:

```bash
sudo TASK_PORT=11436 bc250-setup-task-model
```

Fully specified normal setup:

```bash
sudo TASK_BIND=0.0.0.0 TASK_PORT=11435 TASK_MODEL_REVISION=latest bc250-setup-task-model
```

Supported settings:

- `TASK_BIND`: default `0.0.0.0`;
- `TASK_PORT`: default `11435`;
- `TASK_MODEL_REVISION`: `latest`, branch, tag or commit;
- `TASK_MODEL_SHA256`: optional exact GGUF checksum;
- `TASK_MODEL_NAME`: normally unchanged because it must match the Modelfile;
- `HF_TOKEN`: optional Hugging Face token;
- `HF_HOME`: optional cache location.

In Open WebUI, add this Ollama connection:

```text
http://host.containers.internal:11435
```

Set **Task Model (Local)** to:

```text
task-gemma3-1b-unsloth-ud-q4-k-xl:latest
```

Verify the task instance:

```bash
systemctl is-active ollama-task.service
curl -fsS http://127.0.0.1:11435/api/tags | jq
curl -fsS http://127.0.0.1:11435/api/generate -H 'Content-Type: application/json' -d '{"model":"task-gemma3-1b-unsloth-ud-q4-k-xl:latest","prompt":"Create a short title for installing Fedora on a BC-250","stream":false,"keep_alive":0}'
sleep 2
OLLAMA_HOST=127.0.0.1:11435 ollama ps
```

Expected: the service is active, generation succeeds, and the final `ollama ps`
shows no resident task model.

Remove the task instance and its data:

```bash
sudo systemctl disable --now ollama-task.service
sudo rm -f /etc/systemd/system/ollama-task.service
sudo systemctl daemon-reload
sudo rm -rf /var/llm/ollama-task
```

The final command permanently deletes the separate task-model data.

## Coding model and agent

Install the coding model:

```bash
sudo bc250-setup-coding-agent
```

Expected: approximately 6.1 GB is downloaded, at least 8 GiB free space is
required, and Ollama registers
`coding-ministral3-8b-unsloth-ud-q5-k-xl`.

Follow `main` instead of `latest`:

```bash
sudo CODING_AGENT_REVISION=main bc250-setup-coding-agent
```

Require 12 GiB free space:

```bash
sudo CODING_AGENT_MIN_FREE_BYTES=12884901888 bc250-setup-coding-agent
```

Supported setup settings:

- `CODING_AGENT_REVISION`: `latest`, branch, tag or commit;
- `CODING_AGENT_SHA256`: optional exact GGUF checksum;
- `CODING_AGENT_GGUF_DIR`: default `/var/llm/gguf`;
- `CODING_AGENT_MIN_FREE_BYTES`: default `8589934592`;
- `CODING_AGENT_MODEL`: normally unchanged because it must match the Modelfile;
- `HF_TOKEN`: optional Hugging Face token.

Use the coding agent:

```bash
bc250-code --help
bc250-code review src/app.py review.md
bc250-code refactor src/app.py src/app.refactored.py "Keep the public API stable"
bc250-code document src/app.py docs.md
bc250-code test src/app.py test_app.py
printf '%s\n' 'Create a Python health endpoint' | bc250-code generate - health.py
```

`CODING_AGENT_MAX_INPUT_BYTES` changes the default 60,000-byte input limit:

```bash
CODING_AGENT_MAX_INPUT_BYTES=100000 bc250-code review src/app.py review.md
```

Generate a commit message for already staged changes:

```bash
git add path/to/files
bc250-code-commit
```

Create the proposed local commit without the confirmation prompt:

```bash
bc250-code-commit --yes
```

The coding helpers never stage files, push, approve or merge.

## Experimental models

Enable selected entries:

```bash
sudoedit /etc/bc250-llm-server/experiment-sources.sh
```

List enabled entries without downloading:

```bash
sudo bc250-fetch-experiments --list
```

Download all or selected enabled entries:

```bash
sudo bc250-fetch-experiments all
sudo bc250-fetch-experiments 0,2-4
ollama list
```

Expected: Ollama experiment names begin with `exp-` and contain source and
quantization information.

MTP entries require an external `llama-server`. After copying an example from
`/usr/share/bc250-llm-server/experiments/mtp-sources.example.sh` into the
editable experiment catalog and downloading it, run:

```bash
sudo LLAMACPP=/path/to/llama-server bc250-run-mtp 27b
```

Compare it from a second terminal:

```bash
BASELINE_MODEL=exp-qwen36-27b-unsloth-ud-q2-k-xl bc250-compare-experiments
```

Optional comparison settings are `OLLAMA_URL`, `MTP_URL`, `BASELINE_MODEL`,
`NUM_PREDICT` and `PROMPT`. Optional MTP server settings are `PORT`, `CTX` and
`DRAFT_N_MAX`.

## 40-CU live-manager commands

Open the interactive manager:

```bash
sudo bc250-40cu
```

Inspect kernel, RADV and live routing:

```bash
sudo bc250-40cu verify
sudo bc250-40cu live-status
```

Enable or revert the current live routing:

```bash
sudo bc250-40cu live-full
sudo bc250-40cu live-stock
```

Run Vulkan, sensor and model-generation smoke tests:

```bash
sudo bc250-40cu health-test MODEL_NAME
```

Disable or re-enable selected WGP pairs:

```bash
sudo bc250-40cu mask 1.0.4
sudo bc250-40cu unmask 1.0.4
```

These commands require the confirmation text `APPLY-WGP-TABLE`.

Normal output with the live-manager route can include:

```text
Kernel cc_write_mode: not exposed
Kernel or RADV CUs: 24
Live manager: CUs active & routed: 40/40
```

A live-manager `40/40` routing report can coexist with 24-CU kernel/RADV
enumeration. Validate repeated model output and representative benchmarks.

### Alternative replacement-module route

Do not casually combine the replacement-module route with live-manager boot
persistence.

```bash
sudo dnf in "kernel-devel-$(uname -r)" -y
sudo bc250-40cu build
sudo bc250-40cu status
sudo bc250-40cu enable
```

`enable` requires the exact confirmation `ENABLE-40CU` and reboots. The module
must be rebuilt after relevant kernel updates.

Replacement-module rollback commands:

```bash
sudo bc250-40cu disable
sudo bc250-40cu restore
```

## Ollama runtime profiles

Inspect the effective profile:

```bash
sudo bc250-ollama-profile status
```

Use the packaged balanced profile:

```bash
sudo bc250-ollama-profile balanced
```

Expected: 32,768 context, `q8_0` KV cache, flash attention, one parallel request
and one loaded model.

Use the larger-context profile:

```bash
sudo bc250-ollama-profile max-context
```

Expected: 65,536 context and `q4_0` KV cache. Verify `100% GPU` residency for
each intended workload.

Remove the local profile override:

```bash
sudo bc250-ollama-profile reset
```

## Memory and swap profile commands

Inspect or print the reviewed memory commands:

```bash
sudo bc250-memory-profile status
bc250-memory-profile recommend
```

`apply-safe` is an alias retained for existing automation:

```bash
sudo BC250_ASSUME_YES=1 bc250-memory-profile apply-safe
```

Custom swap sizes:

```bash
sudo SWAP_GIB=32 ZRAM_MIB=2048 BC250_ASSUME_YES=1 bc250-swap-profile apply
```

This example creates 32 GiB disk swap and configures 2 GiB zram.

Remove the package-managed profiles:

```bash
sudo BC250_ASSUME_YES=1 bc250-memory-profile remove
sudo BC250_ASSUME_YES=1 bc250-swap-profile remove
sudo reboot
```

## Verification

Check installed versions:

```bash
rpm -q bc250-llm-server
ollama --version
cyan-skillfish-governor-smu --version
```

Expected package and governor versions for this guide:

```text
bc250-llm-server-0.5.0-0.1.testing.fc44.x86_64
cyan-skillfish-governor-smu 0.4.11
```

The Ollama version depends on whether the reviewed default or `latest` was
selected.

Check governor and memory values:

```bash
sudo grep -A3 '^\[frequency-range\]' /etc/cyan-skillfish-governor-smu/config.toml
sudo cat /sys/module/ttm/parameters/pages_limit
sudo cat /sys/module/ttm/parameters/page_pool_size
sudo cat /sys/module/amdgpu/parameters/gttsize
swapon --show
zramctl
```

Expected reference values:

```text
Governor minimum: 350 MHz
Governor maximum: 2000 MHz
TTM pages_limit: 4194304
TTM page_pool_size: 0
amdgpu.gttsize: -1
Disk swap: 16 GiB, priority 10
zram: 2 GiB, priority 100
```

Check CU routing and services:

```bash
sudo bc250-cu-status
systemctl is-active cyan-skillfish-governor-smu.service
systemctl is-active ollama.service
systemctl is-active tika.service
systemctl is-active open-webui.service
systemctl is-active nginx.service
systemctl is-active bc250-cu-live-manager.service
```

Expected: live routing reports `40/40` and each installed service reports
`active`.

Check model residency after generating a response:

```bash
ollama ps
```

Expected for a fitting production model: `100% GPU`.

Run the standard verification:

```bash
sudo bc250-verify
```

Run generation tests for every registered chat model:

```bash
sudo RUN_MODEL_TESTS=1 bc250-verify
```

Run static parity diagnostics:

```bash
sudo llm-run-diagnose --no-load
```

A warning that no model is resident is normal with `--no-load`.

Run the full 60-second load diagnostic with the first installed model:

```bash
sudo llm-run-diagnose
```

Select a model and test duration explicitly:

```bash
sudo MODEL=MODEL_NAME LOAD_SECONDS=120 NUM_PREDICT=2000 llm-run-diagnose
```

Reference diagnostic values from the tested boards:

```text
TTM pages_limit: 4194304
GPU residency: 100% GPU
mclk: 450 MHz
fclk: 450 MHz
socclk: 1254 MHz
live routing: 40/40
governor maximum: 2000 MHz or the operator's chosen cap
gpt-oss-20b MXFP4 decode: approximately 73-84 tokens/s
```

## LAN verification and first login

Run this from another LAN machine, not from the BC-250 itself:

```bash
bc250-verify-lan SERVER_IP
```

Expected trusted-LAN testing profile:

```text
Port 80 reachable
Port 3000 blocked
Port 11434 blocked
Port 11435 blocked
Port 9998 blocked
```

Open the UI:

```text
http://SERVER_IP/
```

The first Open WebUI account registered becomes administrator. Register it
immediately from the trusted LAN.

## Benchmarking

Run the interactive benchmark:

```bash
bc250-benchmark
```

The prompts select regular, experimental or all models, sustained throttle
testing, and a context curve.

Thinking modes:

```bash
THINK_MODE=false bc250-benchmark
THINK_MODE=true bc250-benchmark
THINK_MODE=low bc250-benchmark
THINK_MODE=medium bc250-benchmark
THINK_MODE=high bc250-benchmark
THINK_MODE=max bc250-benchmark
```

Shorter benchmark examples:

```bash
RUN_LATENCY=0 REPEATS=1 bc250-benchmark
LATENCY_REPEATS=0 bc250-benchmark
```

Include embedding models in the selection:

```bash
ALLOW_EMBED=1 bc250-benchmark
```

Customize context pressure and generation lengths:

```bash
CTX_POINTS='10 55 110 220' bc250-benchmark
NUM_PREDICT_SHORT=512 NUM_PREDICT_LONG=4096 NUM_PREDICT_LATENCY=96 bc250-benchmark
```

The default context points represent approximately 0.25K, 1.25K, 2.5K and 5K
prompt tokens.

Other useful benchmark settings:

- `OLLAMA_URL`: default `http://localhost:11434`;
- `CHAT_SYSTEM_PROMPT` and `CHAT_PROMPT`: latency-test prompts;
- `REPEATS`: default 3;
- `LATENCY_REPEATS`: default 2;
- `RUN_LATENCY`: 0 or 1;
- `THROTTLE_WINDOWS`: default 3;
- `KEEP_ALIVE`: default `30m`;
- `REQUEST_TIMEOUT`: default 900 seconds;
- `CONNECT_TIMEOUT`: default 10 seconds;
- `MAX_RETRIES`: default 3;
- `EARLY_EOS_FRACTION`: default 0.90.

Example with a one-hour keep-alive and longer request timeout:

```bash
KEEP_ALIVE=1h REQUEST_TIMEOUT=1800 bc250-benchmark
```

Expected output in the current directory:

```text
results_YYYYMMDD_HHMMSS.csv
results_YYYYMMDD_HHMMSS.meta.txt
```

## Temperature and sensor logging

Show the current matching sensors:

```bash
bc250-check-temp
```

Refresh once per second:

```bash
bc250-check-temp --watch
```

Write timestamped sensor readings until interrupted:

```bash
SENSOR_INTERVAL=2 /usr/libexec/bc250-llm-server/log_sensors.sh sensors.log
```

## Optional Open WebUI maintenance

Edit the root-only maintenance configuration:

```bash
sudoedit /etc/bc250-llm-server/maintenance.env
```

Review at least these values:

```text
OWUI_API_KEY=an Open WebUI administrator API key
DRY_RUN=1
WARMUP_MODEL=an exact name from ollama list
WARMUP_KEEP_ALIVE=3h
MAX_AGE_DAYS=90
MAX_TOTAL_GB=100
```

Keep `DRY_RUN=1` until pruning output has been reviewed.

Enable selected timers:

```bash
sudo systemctl enable --now owui-backup-config.timer
sudo systemctl enable --now owui-backup-users.timer
sudo systemctl enable --now owui-prune.timer
sudo systemctl enable --now owui-warmup.timer
systemctl list-timers --all | grep -E 'owui|bc250'
```

Packaged schedules:

- configuration backup: daily at 17:45;
- user backup: daily at 18:00;
- upload pruning: daily at 18:10;
- model warm-up: Monday through Friday at 07:35.

## Optional Wake-on-LAN and idle suspend

Install and edit the BC-250 Wake-on-LAN example:

```bash
sudo cp /usr/share/bc250-llm-server/examples/raspi-wol/bc250-wol.env.example /etc/default/bc250-wol
ip link
sudoedit /etc/default/bc250-wol
sudo systemctl enable --now bc250-enable-wol.service
```

Set `BC250_NIC` to the actual network-interface name shown by `ip link`.

Enable weekday idle-suspend attempts:

```bash
sudo systemctl enable --now bc250-night-shutdown.timer
```

The timer checks at 18:30, 18:45, 19:00, 19:15 and 19:30. Active SSH, web,
task-model or Ollama connections defer suspension.

## Close or restrict the testing endpoint

Remove all LAN HTTP access:

```bash
sudo firewall-cmd --permanent --remove-service=http
sudo firewall-cmd --reload
```

Restore trusted-LAN HTTP later:

```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --reload
```

Before using an untrusted or routed network, follow `docs/HARDENING.md` and
`docs/HTTPS.md`. Ollama listens on `0.0.0.0:11434` so the rootful Open WebUI
container can reach it. Keep firewalld active because the Ollama API has no
built-in authentication in this deployment.
