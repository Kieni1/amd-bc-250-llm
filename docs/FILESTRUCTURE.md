# Installed file structure

The installed documentation root is `/usr/share/doc/bc250-llm-server/`. For day-to-day
operation start with `README.md`, `TLDR.md`, `MODELS.md` and `docs/OPERATIONS.md`; this file
is the detailed source-to-installed-path map.

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
| `/usr/bin/bc250-40cu` | Compact standalone live-CU status command |
| `/usr/bin/bc250-cu-live-manager` | Pinned live WGP manager |
| `/usr/bin/llm-run-diagnose` | Model-run diagnostic |
| `/usr/libexec/bc250-llm-server/` | Command implementations |
| `/usr/share/bc250-llm-server/model-management/` | Packaged Modelfiles and operator template |
| `/usr/share/doc/bc250-llm-server/` | Curated operator documentation: top-level quick/model/release files, canonical `docs/`, model component notes, examples and third-party notices |
| `/usr/lib/systemd/system/` | Packaged services and timers |
| `/usr/share/containers/systemd/` | Open WebUI and Tika Quadlets |
| `/usr/share/bc250-llm-server/openwebui/` | Open WebUI desired state, additive model presets, reviewed package-owned Functions and exact prompt assets |

The package also owns its governor, nginx, sensor-module, sysusers, tmpfiles
and systemd-preset configuration in the standard Fedora directories.

Package-owned `/usr` content is treated as immutable at runtime. The canonical `bc250`
dispatcher disables Python bytecode generation before launching package helpers, and guided
install/upgrade convergence removes stale BC-250 `__pycache__`, `*.pyc` and `*.pyo` residue
left by older releases from the package-owned libexec/share trees. Runtime-generated state
belongs under `/var`, `/run`, `/etc` operator configuration, or `/srv` document storage.

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
Modelfiles. A same-name file in `models.d` overrides the packaged definition. The directory is
intentionally empty on a stock install; packaged model definitions live under
`/usr/share/bc250-llm-server/model-management/modelfiles/`.

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
| `/srv/bc250-documents/` | Operator-owned authoritative document tree, `root:root` mode `0750` |
| `/srv/bc250-documents/{public,confidential}/COLLECTION/inbox/{german,french,bilingual}/` | Batch-preparation input lanes; files remain here when OCR/manual review is required |
| `/srv/bc250-documents/{public,confidential}/COLLECTION/sources/` | Immutable authoritative source files; never automatically indexed |
| `/srv/bc250-documents/{public,confidential}/COLLECTION/working/` | Local agent/editor drafts; never indexed |
| `/srv/bc250-documents/{public,confidential}/COLLECTION/active/` | Human-reviewed canonical Markdown eligible for RAG sync |
| `/srv/bc250-documents/{public,confidential}/COLLECTION/superseded/` | Previous source/Markdown revisions retained for audit |
| `/var/lib/open-webui/` | Open WebUI application data; treat as confidential |
| `/var/lib/open-webui/webui.db` | Accounts, chats, settings and knowledge metadata; confidential |
| `/var/lib/open-webui/uploads/` | Uploaded source documents; confidential |
| `/var/lib/open-webui/vector_db/` | Derived vector/RAG index data; confidential |
| `/var/backups/bc250-llm-server/` | Maintenance backups; config/users directories reserve the dormant `bc250-backup-export` group for optional read-only Pi export, while rollback data stays private |
| `/var/log/bc250-llm-install.log` | Guided-installer transcript |

Most generated package/application state under `/var/lib/bc250-llm-server` and
`/var/lib/open-webui` is intentionally root-managed. A normal operator shell may not be able to
`cd` into those trees; use package status/path commands for routine inspection and `sudo` only
for administrative diagnostics. An unprivileged status command should report protected state as
protected/unavailable rather than as an actual zero or missing value.

Ordinary DNF removal retains persistent state. `sudo bc250 reset` is the
separately confirmed greenfield appliance reset. Read [`UNINSTALL.md`](UNINSTALL.md) first.

## Source-to-RPM mapping and packaging boundaries

`packaging/install-manifest.tsv` is the authoritative source-to-payload map. It drives
installation and RPM ownership and is intentionally limited to simple file, config,
directory, generated-text and ghost entries. The installed documentation tree is intentionally operator-oriented rather than a mirror of the source repository. `packaging/install-manifest.tsv` maps canonical documents and examples to their installed locations.

- RPM scriptlets integrate the package only; they do not provision models, replace
  AMDGPU, change CU routing, alter memory/swap policy, change firewall/SELinux policy
  or reboot.
- CU routing remains operator-controlled through `bc250-cu-live-manager`; the RPM and guided installer do not patch AMDGPU or alter routing automatically.
- Model weights are never part of the binary RPM.
- Persistent state under `/var/lib`, `/var/cache`, `/var/backups` and Open WebUI is
  retained across ordinary package removal; `sudo bc250 reset` owns destructive
  greenfield cleanup.
- The RPM statically owns all four Ollama lane units. The upstream Ollama installer
  supplies the binary; the package installer removes only the recognizable upstream
  base unit and restores the package-owned topology.
- Open WebUI base Quadlet installation does not boot-enable the UI. The installer adds
  the package enablement drop-in only after normal Ollama topology and baseline models
  are ready, then applies package-owned desired state through supported APIs.

`config/runtime.env` is the authoritative runtime version/digest pin set. See
`packaging/README.md` remains source-only for maintainer source-refresh and release policy.
