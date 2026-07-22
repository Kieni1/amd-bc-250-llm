# BC-250 LLM appliance: quick operations

This is the short operator path for the Fedora 44 testing package. Commands are
also available as `bc250 COMMAND`; for example, `bc250 verify` and
`bc250-verify` are equivalent.

## Install

```bash
git clone <repo-name>
make validate
sudo bash scripts/ci-local.sh
sudo dnf install ./dist/RPMS/bc250-llm-server-*.x86_64.rpm
sudo bc250-install-ollama
sudo bc250-verify
```

Or run `sudo ./install` for the guided filesystem-to-verification workflow.
Rerun it after the requested memory-profile reboot. Never install the
`dist/SRPMS/*.src.rpm`; it contains build sources, not runtime commands.
After an interrupted system-setup run, `sudo ./install --models-only` resumes
the optional production, task, agentic and embedding-model prompts without
reinstalling the package.

Full destructive removal is `sudo bc250-uninstall`; ordinary
`sudo dnf remove bc250-llm-server.x86_64` keeps persistent appliance data.

Open `http://SERVER_IP/` only from the trusted LAN and register the first Open
WebUI administrator immediately. The default endpoint is HTTP, not HTTPS.

Useful service checks:

```bash
systemctl status cyan-skillfish-governor-smu ollama nginx
systemctl status tika open-webui
curl -fsS http://127.0.0.1:11434/api/tags
```

## Models

Review and enable entries before downloading the main or experiment catalogs:

```bash
sudoedit /etc/bc250-llm-server/production-models.toml
sudo bc250-model list production --all
sudo bc250-fetch-models

sudoedit /etc/bc250-llm-server/experiments-models.toml
sudo bc250-fetch-experiments

# Explicit disk cleanup; review the list before selecting anything
sudo bc250-model cleanup production --list
sudo bc250-model cleanup production MODEL-ID
```

Dedicated instances and optional inputs:

```bash
sudo bc250-setup-task-model       # Ollama 11435
sudo bc250-setup-coding-agent     # Ollama 11436
sudo bc250-pull-embedding-model
sudo bc250-fetch-mtp
```

Task and agent instances have separate model stores below `/var/lib/bc250-llm-server` and do not
replace the main Ollama service. Keep ports 11434–11436 blocked from untrusted
networks. MTP entries are download-only llama.cpp inputs.

## Profiles and CU tools

```bash
sudo bc250-memory-profile recommend
sudo bc250-memory-profile status
sudo bc250-swap-profile status
sudo bc250-ollama-profile status
sudo bc250-cu-status
```

Memory, swap and Ollama profile changes are explicit and reversible. The guided
installer automatically prepares the matching replacement module, but never
enables experimental CUs:

```bash
sudo bc250-40cu status
sudo bc250-40cu enable          # only activation step; rebuilds initramfs and reboots
sudo bc250-40cu live-full       # route all 40 WGP/CU live
sudo bc250-40cu live-stock      # restore stock dispatch live
```

if you have less than 40 stable CUs you need to set them up over the live-manager 
script, start the live manager directly
```bash
sudo bc250-cu-live-manager menu
#[e] -> [w] -> [i] 
# Show status after a reboot to check persistence
sudo bc250-cu-live-manager status
```
kernel-update first prepare then enable the CUs again

```bash
sudo bc250-40cu prepare
sudo bc250-40cu enable
```

Read `docs/CU-UNLOCK.md` before changing CU routing.

## Verification, coding and experiments

```bash
sudo bc250-verify
bc250-verify-lan SERVER_IP
sudo llm-run-diagnose
bc250-benchmark
bc250-check-temp

bc250-code --help
bc250-code-commit --help
bc250-gitea-review --help
bc250-compare-experiments
bc250-run-mtp --help
```

Coding helpers generate local output or commits; they do not push, approve or
merge changes.

## Maintenance and Wake-on-LAN

Configure `/etc/bc250-llm-server/maintenance.env`, then enable only the timers
you need:

```bash
sudo systemctl enable --now owui-backup-config.timer
sudo systemctl enable --now owui-backup-users.timer
sudo systemctl enable --now owui-prune.timer
sudo systemctl enable --now owui-warmup.timer
sudo systemctl enable --now bc250-enable-wol.service
sudo systemctl enable --now bc250-night-shutdown.timer
```

Backups, restores, pruning and suspend logic remain operator-controlled. Prune
defaults to dry-run until configured.

## Detailed references

- `docs/COMMANDS.md`: complete command and override reference.
- `docs/DEPLOYMENT.md`: services, first login and persistent data.
- `docs/HARDENING.md` and `docs/HTTPS.md`: optional security work.
- `docs/OLLAMA.md` and `models/README.md`: model and storage behavior.
- `docs/RPM-LAYOUT.md`: installed files and state directories.
- `docs/UNINSTALL.md`: removal and retained state.
