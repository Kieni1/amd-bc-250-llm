# Installed file structure

This map separates RPM-owned files from state created later by the installer,
services and model commands. Use `rpm -qlv bc250-llm-server.x86_64` for the
exact payload on an installed host.

## Package-owned files

| Path | Purpose |
|---|---|
| `/usr/bin/bc250` and `/usr/bin/bc250-*` | Public dispatcher and command aliases |
| `/usr/bin/llm-run-diagnose` | Performance capture |
| `/usr/libexec/bc250-llm-server/` | Command implementations |
| `/usr/share/bc250-llm-server/model-management/modelfiles/` | Packaged Ollama Modelfiles |
| `/usr/share/bc250-llm-server/model-management/MODEL-TEMPLATE.Modelfile.example` | Operator model template |
| `/usr/share/bc250-llm-server/40cu/` | Pinned 40-CU patch and upstream metadata |
| `/usr/share/bc250-llm-server/cu-live-manager/` | Pinned live-manager metadata |
| `/usr/share/doc/bc250-llm-server/` | Installed documentation |
| `/usr/lib/systemd/system/` | Packaged services and timers |
| `/usr/share/containers/systemd/` | Open WebUI and Tika Quadlets |

The package also owns nginx, governor, sensor-module, tmpfiles, sysusers and
systemd-preset configuration in their normal Fedora directories. See
[`RPM-LAYOUT.md`](RPM-LAYOUT.md) for the detailed payload list.

## Operator configuration

| Path | Purpose |
|---|---|
| `/etc/bc250-llm-server/models.d/*.Modelfile` | Added or overridden Ollama models |
| `/etc/bc250-llm-server/mtp-models.toml` | Download-only MTP runtime entries; `%config(noreplace)` |
| `/etc/bc250-llm-server/maintenance.env` | Optional maintenance settings |
| `/etc/cyan-skillfish-governor-smu/config.toml` | Governor policy; `%config(noreplace)` |
| `/etc/nginx/default.d/bc250-llm-server.conf` | Trusted-LAN HTTP endpoint |
| `/etc/systemd/system/ollama*.service.d/` | Runtime profile overrides created by commands |
| `/etc/sysctl.d/90-bc250-llm-server-swap.conf` | Optional `SWAPPINESS` override created by `bc250-swap-profile` |

Package upgrades never replace operator Modelfiles in `models.d`. A same-name
operator Modelfile takes precedence over the packaged template.

## Persistent and generated state

| Path | Created by / contents |
|---|---|
| `/var/lib/bc250-llm-server/gguf/` | Downloaded chat, task, agentic, embedding and MTP GGUFs with adjacent state JSON |
| `/var/lib/bc250-llm-server/modelfiles/` | Rendered chat and embedding Modelfiles used for `ollama create` |
| `/var/lib/bc250-llm-server/ollama/main/` | Main Ollama blobs and manifests, port 11434 |
| `/var/lib/bc250-llm-server/ollama/task/` | Task-instance store, port 11435 |
| `/var/lib/bc250-llm-server/ollama/agent/` | Agent-instance store, port 11436 |
| `/var/lib/bc250-llm-server/install/` | Guided-installer state and bounded package record |
| `/var/lib/bc250-llm-server/swap/` | Optional appliance swap file |
| `/var/cache/bc250-llm-server/huggingface/` | Reusable Hugging Face cache and staging |
| `/var/cache/bc250-llm-server/40cu/` | Kernel-specific 40-CU build cache and backups |
| `/var/lib/open-webui/` | Open WebUI application data |
| `/var/backups/bc250-llm-server/` | Optional maintenance backups |
| `/var/log/bc250-llm-install.log` | Guided-installer transcript |

The RPM owns the parent-directory declarations but not the model weights,
service databases or operator-created contents. Ordinary `dnf remove` retains
that persistent state. `sudo bc250-uninstall` is the separately confirmed full
purge; review [`UNINSTALL.md`](UNINSTALL.md) first.

## Inspect an installed host

```bash
rpm -qlv bc250-llm-server.x86_64
rpm -qc bc250-llm-server.x86_64
rpm -qd bc250-llm-server.x86_64
rpm -V bc250-llm-server.x86_64

# Files below the setup's main trees that are not owned directly by an RPM:
sudo find /usr/local/bin /etc/bc250-llm-server /etc/systemd/system \
  /var/lib/bc250-llm-server /var/cache/bc250-llm-server \
  /var/lib/open-webui /var/backups/bc250-llm-server \
  \( -type f -o -type l \) -print0 2>/dev/null |
while IFS= read -r -d '' file; do
  rpm -qf "$file" >/dev/null 2>&1 || printf '%s\n' "$file"
done
```
