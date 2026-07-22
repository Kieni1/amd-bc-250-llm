# BC-250 local LLM server — testing RPM source

This repository packages a Fedora 44 software base for an AMD BC-250 local LLM
appliance. It targets office writing, email, documents, coding and
German–French translation. Board installation and operating-system provisioning
are outside the package.

The release is pre-production and assumes a trusted LAN. It enables an
unencrypted nginx/Open WebUI endpoint after installation. HTTPS and wider
hardening remain explicit operator choices; see [`docs/HARDENING.md`](docs/HARDENING.md).

## What is included

| Component | Purpose |
| --- | --- |
| Cyan Skillfish governor | Pinned BC-250 SMU governor, shipped at a 350 MHz minimum |
| Ollama integration | Vulkan-oriented service defaults and operator-run installer |
| Open WebUI and Tika | Rootful Quadlets with persistent local data |
| nginx | Trusted-LAN HTTP entry point |
| Model manager | Downloads GGUF files and registers long, traceable Ollama names |
| Task Ollama | Optional title-generation instance on port 11435 |
| Agent Ollama | Optional agentic instance on port 11436 |
| Operations tools | Verification, diagnostics, benchmark, maintenance and Wake-on-LAN |
| CU tools | Pinned live manager and explicit experimental 40-CU helper |

RPM scriptlets do not download chat models, enable 40 CUs, change memory/swap
profiles or install HTTPS. 
The separate guided `install` workflow applies the documented memory/swap profiles 
and prepares the replacement AMDGPU module for the running kernel. You have to 
unlock the known good CUs for your board and set up optional maintenance scripts. 

## Source layout

- `cmd/` contains host-side operational commands and units.
- `config/` contains shipped governor, nginx and Quadlet configuration.
- `examples/` contains operator-adapted integrations such as Raspberry Pi WOL.
- `models/` contains catalogs, Modelfiles and specialized model workflows.
- `packaging/` and `scripts/` contain RPM policy and deterministic build tools.
- `docs/` contains operator documentation.

## Build and install

On Fedora 44:

```bash
sudo dnf install -y make rpm-build rust cargo gcc \
  systemd-rpm-macros libdrm-devel curl tar gzip xz python3
make rpm
sudo dnf install ./dist/RPMS/bc250-llm-server-*.x86_64.rpm
```

`make rpm` validates the repository, creates the project Source0 archive,
reuses or downloads the four pinned external build inputs, and builds the
binary and source RPMs. `make clean` keeps that source cache. The installable 
package is under `dist/RPMS/`; the build-only source RPM is under `dist/SRPMS/`.
Installing a `.src.rpm` does not provide any `bc250-*` command.

For the guided workflow, including filesystem growth, profiles, model setup and
verification, copy the install script () besides the .rpm onto the bc250:

```bash
sudo ./install
```

The installer pauses for the required reboot and is then rerun. It prepares and
checks 40-CU support once, but leaves activation to the explicit
`sudo bc250-40cu enable` for 40 CUs or fewer than 40 over the live-manager 
command `sudo bc250-cu-live-manager` menu. It does not enable maintenance timers.
If system setup was interrupted after the RPM was installed, resume only the
interactive production, task, agentic and embedding-model prompts with:

```bash
sudo ./install --models-only
```

This mode does not grow filesystems, update Fedora, reinstall the RPM or change
the memory and CU setup.

The guided installer records the RPM packages it adds so the explicit full
purge can remove that bounded set later. To remove the complete appliance setup,
including models, Open WebUI data, Ollama, profiles and 40-CU persistence, run:

```bash
sudo bc250-uninstall
```

This is intentionally different from `dnf remove`, which retains persistent
state. Review [`docs/UNINSTALL.md`](docs/UNINSTALL.md) before purging.

GitHub Actions provides the same Fedora 44 `make rpm` build as a manually
started workflow.

## First setup with install script

Install Fedora 44 with additional packages for headless management
Log in and run 

```bash
sudo dnf up
```

then set up remote acces of your choice. Basic is adding two lines to 
`/etc/ssh/sshd_config` for remote management:

```bash
PasswordAuthentication yes
AllowUsers <username>
```

reboot and access the bc250.

Download the .rpm from git

```bash
curl -L -O *rpm
```

copy the install script () besides the .rpm onto the bc250 and run it:

```bash
sudo ./install
```

After an automatic reboot you have to execute the script again. Choose then
models from the preselection for testing.

Finish with setting up optional workflows, the 40 CU unlock (recommended!) and 
optional maintenance scripts.

to enable all 40 cus execute:
```bash
sudo bc250-40cu enable
# if you have less than 40 stable CUs you need to set them up over the 
# live-manager script
# Start the live manager directly
sudo bc250-cu-live-manager menu
[e] -> [w] -> [i] 
# Show status after a reboot
sudo bc250-cu-live-manager status
```

No CU tool is activated by RPM installation or guided preparation. Read
[`docs/CU-UNLOCK.md`](docs/CU-UNLOCK.md) before using it.

## Optional workflows and commands

These are some examples, check [`docs/COMMANDS.md`](docs/COMMANDS.md)

```bash
# Dedicated title model and agentic models
sudo bc250-setup-task-model
sudo bc250-setup-coding-agent

# Embedding, experiments and MTP
sudo bc250-pull-embedding-model
sudo bc250-fetch-experiments
sudo bc250-fetch-mtp

# Diagnostics and benchmark
sudo bc250-verify
sudo llm-run-diagnose
bc250-benchmark

# Runtime profiles and explicit CU tools
sudo bc250-ollama-profile status
sudo bc250-memory-profile status
sudo bc250-swap-profile status
sudo bc250-cu-status
sudo bc250-40cu status
# The installer has already prepared the matching module. This is the only
# command that activates experimental additional CUs and it reboots the host:
sudo bc250-40cu enable
```

## Example Models 

The dedicated agent set are
`agentic-ornith1-9b-deepreinforce-q5-k-m` and
`agentic-qwable9b-empero-q6-k`. 
The dedicated task model is `task-gemma3-1b-unsloth-ud-q4-k-xl` to generate 
chat titles in openweb-ui.
The current production set is
- Translation: `prod-ministral3-8b-unsloth-ud-q5-k-xl` and
  `prod-qwen35-9b-hauhaucs-uncensored-q6-k`.
- Documents: `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` and
  `prod-gpt-oss20b-ggml-org-mxfp4`.
- Text generation: `prod-qwen3-4b-lmstudio-q6-k` and
  `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl`.

Model names deliberately expose family, source and quantization in `ollama
list` and Open WebUI. Catalogs, all current Modelfiles, storage behavior and
revision overrides are documented in [`models/README.md`](models/README.md).
In Ollama you must set by hand the recommendations in 
[`docs/openwebui-settings.md`](docs/openwebui-settings.md).

## Documentation

- [`TLDR.md`](TLDR.md): setup and command overview.
- [`docs/COMMANDS.md`](docs/COMMANDS.md): commands and environment overrides.
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): services, ports and persistent data.
- [`docs/OLLAMA.md`](docs/OLLAMA.md): Ollama installation and runtime profiles.
- [`docs/openwebui-settings.md`](docs/openwebui-settings.md): Open WebUI connections and model roles.
- [`docs/MEMORY.md`](docs/MEMORY.md): unified-memory profile.
- [`docs/CU-UNLOCK.md`](docs/CU-UNLOCK.md): live and replacement-module CU tools.
- [`docs/REPACKAGING.md`](docs/REPACKAGING.md): RPM source refresh and release process.
- [`docs/UNINSTALL.md`](docs/UNINSTALL.md): complete removal and retained state.

## License

The project is GPL-2.0-only. Pinned external sources retain their own licenses;
see [`licenses/THIRD_PARTY_NOTICES.md`](licenses/THIRD_PARTY_NOTICES.md).
