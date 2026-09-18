# Installed file structure

Use these commands for the exact state of an installed package:

```bash
rpm -qlv bc250-llm-server.x86_64
rpm -qc bc250-llm-server.x86_64
rpm -qd bc250-llm-server.x86_64
rpm -V bc250-llm-server.x86_64
```

## Package-owned interface

| Path | Purpose |
|---|---|
| `/usr/bin/bc250` | Multicall command dispatcher |
| `/usr/bin/bc250-*` | Stable command aliases |
| `/usr/bin/bc250-cu-live-manager` | Pinned live WGP manager |
| `/usr/bin/llm-run-diagnose` | Model-run diagnostic |
| `/usr/libexec/bc250-llm-server/` | Command implementations |
| `/usr/share/bc250-llm-server/model-management/` | Packaged Modelfiles and operator template |
| `/usr/share/bc250-llm-server/quality-checks/` | Current supported real-device candidate screens and evidence helpers; historical campaign recipes remain source-only under `quality-checks/history/` |
| `/usr/share/bc250-llm-server/40cu/` | Pinned unlock patch and source metadata |
| `/usr/share/doc/bc250-llm-server/` | Installed documentation preserving repository-relative paths, including `MODELS.md`, `docs/` and `cmd/benchmark/README.md` |
| `/usr/lib/systemd/system/` | Packaged services and timers |
| `/usr/share/containers/systemd/` | Open WebUI and Tika Quadlets |
| `/usr/share/bc250-llm-server/openwebui/` | Open WebUI desired state, additive model presets, reviewed package-owned Functions and exact prompt assets |

The package also owns its governor, nginx, sensor-module, sysusers, tmpfiles
and systemd-preset configuration in the standard Fedora directories.

## Operator configuration

| Path | Purpose |
|---|---|
| `/etc/bc250-llm-server/models.d/*.Modelfile` | Added or same-name overridden models |
| `/etc/bc250-llm-server/mtp-models.toml` | Download-only MTP catalog |
| `/etc/bc250-llm-server/maintenance.env` | Optional maintenance policy |
| `/etc/cyan-skillfish-governor-smu/config.toml` | Governor policy |
| `/etc/nginx/default.d/bc250-llm-server.conf` | Trusted-LAN HTTP endpoint |
| `/etc/systemd/system/ollama*.service.d/` | Runtime profile overrides |
| `/etc/sysctl.d/90-bc250-llm-server-swap.conf` | Optional swappiness override |
| `/etc/default/bc250-wol` | Optional Wake-on-LAN interface |

RPM upgrades preserve `%config(noreplace)` files and do not touch operator
Modelfiles. A same-name file in `models.d` overrides the packaged definition.

## Generated state

| Path | Contents |
|---|---|
| `/var/lib/bc250-llm-server/gguf/` | Source GGUFs and adjacent state JSON |
| `/var/lib/bc250-llm-server/modelfiles/` | Rendered runtime Modelfiles |
| `/var/lib/bc250-llm-server/ollama/main/` | Main store, port 11434 |
| `/var/lib/bc250-llm-server/ollama/task/` | Task store, port 11435 |
| `/var/lib/bc250-llm-server/ollama/embedding/` | Embedding store, port 11437 |
| `/var/lib/bc250-llm-server/ollama/agent/` | Exclusive agent store, port 11436 |
| `/var/lib/ollama/` | Persistent upstream/Ollama-owned state outside ordinary RPM file ownership |
| `/var/lib/bc250-llm-server/revalidation/` | Root-only revalidation work state; completed state remains inspectable until explicit cleanup or the next run |
| `/var/lib/bc250-llm-server/revalidation/results/` | Root-only final whole-appliance revalidation bundles |
| `/var/lib/bc250-llm-server/secrets/open-webui.env` | Persistent root-only Open WebUI signing secret |
| `/var/lib/bc250-llm-server/swap/` | Optional disk swap file |
| `/var/cache/bc250-llm-server/huggingface/` | Download cache and staging |
| `/var/cache/bc250-llm-server/40cu/` | Kernel-specific build cache |
| `/srv/bc250-documents/` | Operator-owned authoritative document tree, `root:root` mode `0750` |
| `/srv/bc250-documents/{public,confidential}/COLLECTION/sources/` | Original PDFs; never automatically uploaded by `bc250-rag-import` |
| `/srv/bc250-documents/{public,confidential}/COLLECTION/active/` | Canonical Markdown eligible for metadata-aware RAG sync |
| `/var/lib/open-webui/` | Open WebUI application data; treat as confidential |
| `/var/lib/open-webui/webui.db` | Accounts, chats, settings and knowledge metadata; confidential |
| `/var/lib/open-webui/uploads/` | Uploaded source documents; confidential |
| `/var/lib/open-webui/vector_db/` | Derived vector/RAG index data; confidential |
| `/var/backups/bc250-llm-server/` | Maintenance backups; config/users directories reserve the dormant `bc250-backup-export` group for optional read-only Pi export, while rollback data stays private |
| `/var/log/bc250-llm-install.log` | Guided-installer transcript |

Ordinary DNF removal retains persistent state. `sudo bc250-reset` is the
separately confirmed greenfield appliance reset; `bc250-uninstall` remains an alias. Read [`UNINSTALL.md`](UNINSTALL.md) first.

## Source-to-RPM mapping and packaging boundaries

`packaging/install-manifest.tsv` is the authoritative source-to-payload map. It drives
installation and RPM ownership and is intentionally limited to simple file, config,
directory, alias, generated-text and ghost entries. Repository-relative documentation
paths are preserved below `/usr/share/doc/bc250-llm-server/` so the same Markdown links
work in Git and on the appliance.

- RPM scriptlets integrate the package only; they do not provision models, replace
  AMDGPU, change CU routing, alter memory/swap policy, change firewall/SELinux policy
  or reboot.
- `bc250-install` owns explicit appliance provisioning and may prepare, but never
  silently activate, the running-kernel 40-CU replacement module.
- Model weights are never part of the binary RPM.
- Persistent state under `/var/lib`, `/var/cache`, `/var/backups` and Open WebUI is
  retained across ordinary package removal; `sudo bc250-reset` owns destructive
  greenfield cleanup.
- The RPM statically owns all four Ollama lane units. The upstream Ollama installer
  supplies the binary; `bc250-install-ollama` removes only the recognizable upstream
  base unit and restores the package-owned topology.
- Open WebUI base Quadlet installation does not boot-enable the UI. The installer adds
  the package enablement drop-in only after normal Ollama topology and baseline models
  are ready, then applies package-owned desired state through supported APIs.

`config/runtime.env` is the authoritative runtime version/digest pin set. See
[`../packaging/README.md`](../packaging/README.md) for maintainer source-refresh and
release policy.
