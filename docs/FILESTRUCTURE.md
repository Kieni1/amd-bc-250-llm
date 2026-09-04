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
| `/usr/share/bc250-llm-server/40cu/` | Pinned unlock patch and source metadata |
| `/usr/share/doc/bc250-llm-server/` | Installed documentation, including `MODELS.md` and `BENCHMARK.md` |
| `/usr/lib/systemd/system/` | Packaged services and timers |
| `/usr/share/containers/systemd/` | Open WebUI and Tika Quadlets |
| `/usr/share/bc250-llm-server/openwebui/` | Open WebUI desired state and additive model presets |

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
| `/var/backups/bc250-llm-server/` | Maintenance backups |
| `/var/log/bc250-llm-install.log` | Guided-installer transcript |

Ordinary DNF removal retains persistent state. `sudo bc250-reset` is the
separately confirmed greenfield appliance reset; `bc250-uninstall` remains an alias. Read [`UNINSTALL.md`](UNINSTALL.md) first.

[`RPM-LAYOUT.md`](RPM-LAYOUT.md) documents the source-to-RPM mapping for
maintainers.

- `config/runtime.env`: authoritative runtime version/digest pins.
