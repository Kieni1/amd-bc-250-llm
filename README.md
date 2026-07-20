# BC-250 local LLM server — testing RPM source

This repository packages a Fedora 44 integration for an AMD BC-250 local LLM
server. The main RPM installs the filippor Cyan Skillfish SMU governor, Ollama
service defaults, Open WebUI and Tika Quadlets, nginx, maintenance tools,
benchmarks, model templates, the pinned 40-CU helper and optional local agent
helpers.

Ollama itself is installed separately by an explicit operator command. Model
weights, HTTPS, Open WebUI settings and CU changes are never applied silently.

> **Testing package:** the default web interface uses plain HTTP. Login details,
> prompts and uploaded documents are not encrypted in transit. Use it only on a
> trusted LAN until HTTPS is configured as described in
> [`docs/HTTPS.md`](docs/HTTPS.md).

For a command-first installation and operations reference, see
[`TLDR.md`](TLDR.md). For switches and environment overrides, see
[`docs/COMMANDS.md`](docs/COMMANDS.md).

## Package setup

1. Build and install the RPM on an already prepared Fedora 44 BC-250 host.
2. Install or normalize Ollama:

   ```bash
   sudo bc250-install-ollama
   ```

3. Set `enabled = true` for selected entries in
   `/etc/bc250-llm-server/production-models.toml`, then run:

   ```bash
   sudo bc250-fetch-models
   ```

4. Tune `/etc/cyan-skillfish-governor-smu/config.toml` for the individual board,
   cooling and power supply.
5. Treat the 40-CU path as a separate experiment; read
   [`docs/CU-UNLOCK.md`](docs/CU-UNLOCK.md) first.

BIOS configuration, cooling design, power-supply sizing and board repair are
outside this package.

## Fast Setup, assumes 40 CU ok

1. Initial setup

   ```bash
   sudo lvextend -l +100%FREE /dev/mapper/fedora-root
   sudo xfs_growfs /
   sudo dnf upgrade --refresh -y
   sudo dnf install ./bc250-llm-server-*.x86_64.rpm -y
   sudo bc250-install-ollama
   sudo systemctl enable --now cyan-skillfish-governor-smu.service
   sudo BC250_ASSUME_YES=1 bc250-memory-profile apply-full
   sudo BC250_ASSUME_YES=1 bc250-swap-profile apply
   sudo bc250-cu-live-manager --yes enable all
   sudo bc250-cu-live-manager --yes write-service-table
   sudo bc250-cu-live-manager --yes install-service
   sudo reboot
   ```

2. After reconnecting
   
   ```bash
   sudoedit /etc/bc250-llm-server/production-models.toml
   sudo bc250-fetch-models all </dev/null
   ```

3. Fast verification

   ```bash
   rpm -q bc250-llm-server
   ollama --version
   ollama list
   grep -E '^(min|max)' /etc/cyan-skillfish-governor-smu/config.toml
   cat /sys/module/ttm/parameters/pages_limit
   cat /sys/module/ttm/parameters/page_pool_size
   sudo cat /sys/module/amdgpu/parameters/gttsize
   sudo bc250-cu-live-manager status
   sudo bc250-cu-status
   sudo systemctl is-active cyan-skillfish-governor-smu ollama tika open-webui nginx bc250-cu-live-manager
   sudo bc250-verify
   sudo llm-run-diagnose --no-load
   ```

## What the main RPM does

- Installs Fedora dependencies including Podman, nginx, Mesa/RADV utilities and
  Hugging Face tooling.
- Builds and bundles the SMU branch of
  `filippor/cyan-skillfish-governor`, pinned to release `v0.4.11` and commit
  `60ab6e5b354f01f287c73d920990dcd618a674cc`.
- Installs the pinned fduraibi 40-CU helper and source patch in the main RPM;
  using them remains an explicit operator action.
- Installs rootful Quadlets for private Tika networking and loopback-only Open
  WebUI exposure.
- Enables firewalld and opens the standard HTTP service.
- Starts the governor, Tika, Open WebUI and nginx. It starts Ollama only when an
  Ollama service is already installed.
- Provides optional helpers for Ollama, a title/task model, a coding model,
  model downloads, maintenance, benchmarks and verification.
- Creates no human login account.
- Leaves model downloads, first Open WebUI registration, HTTPS and CU changes
  under operator control.

The first account registered in Open WebUI becomes administrator. Register it
immediately from a trusted LAN.

## Build locally on Fedora 44

```bash
sudo dnf install -y make rpm-build rust cargo gcc \
  systemd-rpm-macros libdrm-devel curl tar gzip xz python3
make rpm
```

`make rpm` validates the source tree and prepares four immutable inputs: the
governor source, its Cargo vendor archive, the fduraibi 40-CU source and the
WinnieLV live manager. Once they exist, repeated RPM builds do not need to
download third-party source again.

Artifacts and their checksums are written to `dist/`.

## Build with GitHub Actions

The included `.github/workflows/build-rpm.yml` runs only when manually started
with **Actions → Build Fedora RPM → Run workflow**. RPM and SRPM files are
uploaded as workflow artifacts.

## Install the main package

```bash
sudo dnf install ./dist/bc250-llm-server-*.x86_64.rpm
```

Then open:

```text
http://SERVER_IP/
```

## Models

No model download is enabled by default.

```bash
sudoedit /etc/bc250-llm-server/production-models.toml
bc250-model list production
sudo bc250-fetch-models
```

Each source entry accepts a commit, tag, branch such as `main`, or `latest` for
the repository default. Packaged Ollama names include model family, source and
quantization so `ollama list` and Open WebUI remain unambiguous.

On package upgrades, merge any `.rpmnew` source catalog before fetching. Old
Ollama registrations are not renamed; remove them with `ollama rm NAME` after
the replacement model has been created and tested.

The TOML catalogs replace the former executable shell catalogs. Because this is
a pre-production package, those old catalogs are not migrated automatically;
copy any wanted selections into the TOML files before removing RPM-save files.

Model catalogs and Modelfiles are maintained in separate installed directories
under `/usr/share/bc250-llm-server/model-management/`. Experimental models have
a separate editable catalog and compatibility command:

```bash
sudoedit /etc/bc250-llm-server/experiments-models.toml
bc250-model list experiments
sudo bc250-fetch-experiments
```

Download-only MTP inputs are isolated from Ollama experiments:

```bash
sudoedit /etc/bc250-llm-server/mtp-models.toml
bc250-model list mtp --all
sudo bc250-fetch-mtp
```

See [`models/README.md`](models/README.md) for the feature layout and Ollama
storage behavior.

When upgrading from 0.6.2, `%config(noreplace)` retains the old experiment
catalog, including any MTP tables in it. Merge the new experiment `.rpmnew`
file and move wanted MTP enablement to `mtp-models.toml`; no automatic catalog
migration is run.

Modern architectures may require a newer Ollama release; see
[`docs/OLLAMA.md`](docs/OLLAMA.md).


## Optional memory and runtime profiles

The RPM does not alter the boot command line, zram or disk swap automatically.
Inspect and apply reviewed profiles explicitly:

```bash
sudo bc250-memory-profile status
bc250-memory-profile recommend
sudo bc250-ollama-profile status
sudo bc250-swap-profile status
```

The Ollama packaged default is the balanced 32K/q8_0 profile. A 64K/q4_0
profile is available with `sudo bc250-ollama-profile max-context`. The reviewed
kernel profile uses a 16 GiB TTM limit; details are in
[`docs/MEMORY.md`](docs/MEMORY.md).

## Optional task model

A separate Gemma 3 1B Ollama instance handles lightweight title generation:

```bash
sudo bc250-setup-task-model
```

The setup command creates `ollama-task.service` on port `11435`; RPM installation
does not enable it automatically. Keep that port blocked from the LAN.

## Optional coding agent

The coding agent uses `ollama-agent.service` on port `11436` and the current
Ornith/Qwable agentic models:

```bash
sudo bc250-setup-coding-agent
bc250-code review path/to/file review.md
```

It can generate, refactor, review and document code, propose local commit
messages and review Gitea pull requests. It never pushes, approves or merges.
Keep port `11436` blocked from the LAN. See
[`models/coding-agent/README.md`](models/coding-agent/README.md).

## Experimental 40-CU unlock

The main RPM contains the pinned live manager, requires `umr`, and contains the
fduraibi helper. The simplest route is the interactive live manager; no separate
download is needed:

```bash
sudo bc250-40cu
```

The replacement-module route remains available but is not run during package
installation:

```bash
sudo dnf install "kernel-devel-$(uname -r)"
sudo bc250-40cu build
sudo bc250-40cu enable
```

The feature can expose defective harvested CUs, replaces a kernel module for
the running kernel and requires a reboot. Governor policy belongs to the
operator; the wrapper imposes no clock limit. Read
[`docs/CU-UNLOCK.md`](docs/CU-UNLOCK.md).

## Useful commands

```bash
sudo bc250-verify
sudo bc250-cu-status
sudo llm-run-diagnose --no-load
sudo bc250-memory-profile status
sudo bc250-ollama-profile status
sudo bc250-swap-profile status
sudo bc250-install-ollama
sudo bc250-40cu
sudo bc250-setup-task-model
sudo bc250-setup-coding-agent
sudo bc250-fetch-models
sudo bc250-fetch-experiments
sudo bc250-fetch-mtp
sudo bc250-pull-embedding-model
bc250-code --help
bc250-gitea-review --help
bc250-benchmark
bc250-check-temp
bc250-verify-lan SERVER_IP
bc250-uninstall-info
```

Deployment, hardening, HTTPS, Ollama, memory, sensors, CU, uninstall and
repackaging details are under `docs/`. Start with
[`docs/HARDENING.md`](docs/HARDENING.md) when closing the testing profile.

## License

The integration project is licensed under GPL-2.0-only. The bundled governor is
MIT-licensed, and the bundled 40-CU source declares GPL-2.0-only. The pinned CU
live-manager repository has no explicit license; see
`licenses/THIRD_PARTY_NOTICES.md`.
