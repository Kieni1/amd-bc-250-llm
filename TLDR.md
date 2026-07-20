# BC-250 LLM server: setup and command overview

This is the command-first index for the packaged BC-250 stack. It summarizes
initial setup, model management, optional features and checks; follow the linked
topic documents for rationale, recovery procedures and security details.
The complete switch and environment-variable reference is in
[`docs/COMMANDS.md`](docs/COMMANDS.md).

The default web endpoint is unencrypted HTTP. Use it only on a trusted LAN until
[`docs/HARDENING.md`](docs/HARDENING.md) and [`docs/HTTPS.md`](docs/HTTPS.md)
have been applied.

## Initial installation

Build on Fedora 44:

```bash
sudo dnf install -y make rpm-build rpmdevtools rust cargo gcc \
  systemd-rpm-macros libdrm-devel curl tar gzip xz python3
make validate
make sources
make rpm
```

Install and initialize the runtime:

```bash
sudo dnf install ./dist/bc250-llm-server-*.x86_64.rpm
sudo bc250-install-ollama
sudo systemctl enable --now cyan-skillfish-governor-smu.service
```

The package starts the web stack but does not download chat models, alter the
kernel memory profile, create swap or change CU routing automatically.

## Production models

Catalogs and Modelfiles are deliberately separated:

```text
/etc/bc250-llm-server/production-models.toml
/etc/bc250-llm-server/experiments-models.toml
/etc/bc250-llm-server/mtp-models.toml
/usr/share/bc250-llm-server/model-management/modelfiles/
```

Enable selected entries by setting `enabled = true`, then inspect or install:

```bash
sudoedit /etc/bc250-llm-server/production-models.toml
bc250-model list production
sudo bc250-fetch-models
sudo bc250-fetch-models all </dev/null
sudo bc250-fetch-models 0,2-4
ollama list
```

`bc250-fetch-models` remains a compatibility name for
`bc250 model install production`. Catalog revisions accept a commit, tag,
branch or `latest`. A full commit plus `sha256` provides the strongest
reproducibility.

Pull the Open WebUI embedding model separately:

```bash
sudo bc250-pull-embedding-model
```

See [`models/embedding/README.md`](models/embedding/README.md) for overrides.

See [`docs/OLLAMA.md`](docs/OLLAMA.md) for service settings and upgrades.

## Task and coding models

The task model uses an isolated Ollama instance on port `11435`:

```bash
sudo bc250-setup-task-model
curl -fsS http://127.0.0.1:11435/api/tags
```

Keep that port blocked from the LAN. Configure Open WebUI with
`http://host.containers.internal:11435`. Details and removal instructions are
in [`models/task-model/README.md`](models/task-model/README.md).

The coding models use an isolated Ollama instance on port `11436`:

```bash
sudo bc250-setup-coding-agent
curl -fsS http://127.0.0.1:11436/api/tags
bc250-code review src/app.py review.md
bc250-code refactor src/app.py src/app.refactored.py
bc250-code-commit
bc250-gitea-review --help
```

Keep port `11436` blocked from the LAN. These tools never push, approve or
merge. Review generated output and run the real project tests. See
[`models/coding-agent/README.md`](models/coding-agent/README.md).

## Experimental models

```bash
sudoedit /etc/bc250-llm-server/experiments-models.toml
bc250-model list experiments
sudo bc250-fetch-experiments --list
sudo bc250-fetch-experiments all
bc250-compare-experiments
```

See [`models/experiments/README.md`](models/experiments/README.md).

## MTP models

The separate MTP catalog contains disabled `download-only` llama.cpp inputs.
Enable one, fetch it, then start a local llama.cpp server:

```bash
sudoedit /etc/bc250-llm-server/mtp-models.toml
bc250-model list mtp --all
sudo bc250-fetch-mtp
LLAMACPP=/path/to/llama-server bc250-run-mtp 27b
```

See [`models/mtp/README.md`](models/mtp/README.md).

## Memory, swap and Ollama profiles

Inspect before changing anything:

```bash
sudo bc250-memory-profile status
bc250-memory-profile recommend
sudo bc250-swap-profile status
sudo bc250-ollama-profile status
```

Apply the reviewed profiles explicitly:

```bash
sudo bc250-memory-profile apply-full
sudo bc250-swap-profile apply
sudo bc250-ollama-profile balanced
sudo reboot
```

The memory profile changes all installed kernel entries and requires a reboot.
The swap profile creates disk-backed swap and a zram override. Read
[`docs/MEMORY.md`](docs/MEMORY.md) first.

## Governor and 40-CU tools

Inspect the governor and live CU state:

```bash
systemctl status cyan-skillfish-governor-smu.service
sudoedit /etc/cyan-skillfish-governor-smu/config.toml
sudo bc250-cu-status
sudo bc250-cu-live-manager status
```

Open the interactive CU manager with:

```bash
sudo bc250-40cu
```

Exposing harvested CUs can reveal defective hardware. No RPM scriptlet enables
them. Read [`docs/CU-UNLOCK.md`](docs/CU-UNLOCK.md) before making changes.

## Verification and diagnostics

These checks are intentionally separate:

```bash
sudo bc250-verify
bc250-verify-lan SERVER_IP
sudo llm-run-diagnose --no-load
MODEL=MODEL_NAME sudo llm-run-diagnose
bc250-benchmark
bc250-check-temp
```

- `bc250-verify` runs on the BC-250 after RPM installation.
- `bc250-verify-lan` runs from another LAN machine and checks that internal
  ports are not exposed.
- `llm-run-diagnose` is a model-performance diagnostic; its default mode adds a
  sustained generation load.

Deployment and LAN expectations are in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Open WebUI maintenance

The backup, prune and warmup timers are installed but disabled by default:

```bash
systemctl list-timers 'owui-*'
sudo systemctl enable --now owui-backup-config.timer
sudo systemctl enable --now owui-backup-users.timer
sudo systemctl enable --now owui-prune.timer
sudo systemctl enable --now owui-warmup.timer
```

Review `/etc/bc250-llm-server/maintenance.env` before enabling them. Restore
commands require Open WebUI to be stopped and create rollback data first.

## Command index

```text
bc250 --help                  All packaged command groups
bc250-model                   Unified model catalog manager
bc250-fetch-models            Production model compatibility command
bc250-fetch-experiments       Experiment compatibility command
bc250-fetch-mtp               MTP download compatibility command
bc250-install-ollama          Ollama installation/normalization
bc250-ollama-profile          Ollama runtime profile
bc250-memory-profile          Kernel TTM profile
bc250-swap-profile            Disk swap and zram profile
bc250-setup-task-model        Isolated task Ollama and model
bc250-setup-coding-agent      Isolated agent Ollama and models
bc250-code                    Local coding operations
bc250-benchmark               Model benchmark
bc250-verify                  Post-install server check
bc250-verify-lan              Remote LAN exposure check
llm-run-diagnose              Model-run performance diagnostic
bc250-40cu                    Experimental CU tools
bc250-uninstall-info          Retained-state and removal guide
```

## Documentation map

- [`docs/COMMANDS.md`](docs/COMMANDS.md): command forms, switches and overrides
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): services, persistence and first login
- [`docs/HARDENING.md`](docs/HARDENING.md): close or restrict the testing endpoint
- [`docs/HTTPS.md`](docs/HTTPS.md): encrypted front-end guidance
- [`docs/OLLAMA.md`](docs/OLLAMA.md): installation and runtime behavior
- [`docs/MEMORY.md`](docs/MEMORY.md): TTM, zram and disk-swap rationale
- [`docs/SENSORS.md`](docs/SENSORS.md): temperature and sensor drivers
- [`docs/CU-UNLOCK.md`](docs/CU-UNLOCK.md): experimental CU workflows and risk
- [`docs/REPACKAGING.md`](docs/REPACKAGING.md): source pins and release process
- [`docs/RPM-LAYOUT.md`](docs/RPM-LAYOUT.md): installed paths and ownership
- [`docs/UNINSTALL.md`](docs/UNINSTALL.md): removal and retained state
