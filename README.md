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

## Package setup

1. Build and install the RPM on an already prepared Fedora 44 BC-250 host.
2. Install or normalize Ollama:

   ```bash
   sudo bc250-install-ollama
   ```

3. Select models in `/etc/bc250-llm-server/model-sources.sh`, then run:

   ```bash
   sudo bc250-fetch-models
   ```

4. Tune `/etc/cyan-skillfish-governor-smu/config.toml` for the individual board,
   cooling and power supply.
5. Treat the 40-CU path as a separate experiment; read
   [`docs/CU-UNLOCK.md`](docs/CU-UNLOCK.md) first.

BIOS configuration, cooling design, power-supply sizing and board repair are
outside this package.

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
sudo dnf install -y make rpm-build rpmdevtools rust cargo gcc \
  systemd-rpm-macros libdrm-devel curl tar gzip xz python3
make sources
make rpm
```

`make sources` prepares four immutable inputs: the governor source, its Cargo
vendor archive, the fduraibi 40-CU source and the WinnieLV live manager. Once
they exist, repeated RPM builds do not need to download third-party source again.

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
sudoedit /etc/bc250-llm-server/model-sources.sh
sudo bc250-fetch-models
```

Each source entry accepts a commit, tag, branch such as `main`, or `latest` for
the repository default. Packaged Ollama names include model family, source and
quantization so `ollama list` and Open WebUI remain unambiguous.

On package upgrades, merge any `.rpmnew` source catalog before fetching. Old
Ollama registrations are not renamed; remove them with `ollama rm NAME` after
the replacement model has been created and tested.

Production Modelfiles are installed under
`/usr/share/bc250-llm-server/models/`. Experimental models have a separate
configuration and command:

```bash
sudoedit /etc/bc250-llm-server/experiment-sources.sh
sudo bc250-fetch-experiments
```

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

A separate Gemma 3 1B Ollama instance can handle lightweight title generation:

```bash
sudo bc250-setup-task-model
```

It listens on port `11435` and is not enabled automatically. Keep that port
blocked from the LAN.

## Optional coding agent

The coding agent uses the main Ollama service and a local Ministral 3 8B GGUF:

```bash
sudo bc250-setup-coding-agent
bc250-code review path/to/file review.md
```

It can generate, refactor, review and document code, propose local commit
messages and review Gitea pull requests. It never pushes, approves or merges.
See [`coding-agent/README.md`](coding-agent/README.md).

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
