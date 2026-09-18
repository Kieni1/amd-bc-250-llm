# Office maintenance

Maintenance is optional and disabled by the RPM. It is designed to preserve
local privacy, bound storage growth and avoid unnecessary power use on a small
office appliance.

## Fast safe setup

```bash
sudo bc250-maintenance setup --defaults
sudo bc250-maintenance run backup
sudo bc250-maintenance status
```

This enables verified local configuration and identity backups only. It does
not delete uploads, warm a model, configure Wake-on-LAN or schedule a power
action.

For those optional choices, use the guided setup:

```bash
sudo bc250-maintenance setup
```

A full interactive `sudo bc250-install` now offers this maintenance setup near
the end of installation, followed by optional Raspberry Pi companion setup. The
companion path deliberately uses only office HTTP :80 and restricted SSH :22;
Wake-on-LAN itself does not require a host firewall port.

Re-running setup updates the existing private configuration. Disable all
maintenance and power timers without deleting data with:

```bash
sudo bc250-maintenance disable
```

## Backups and privacy

`backup-config` uses SQLite's online backup API, verifies integrity and writes a
SHA-256 sidecar. It includes Open WebUI accounts, settings and chats but excludes
bulky uploads, vector data and caches. It is therefore **not a complete RAG
backup** and cannot restore an ingested document library by itself. `backup-users` is a selective identity
export and contains password hashes, API keys and access-control data.

Backups under `/var/backups/bc250-llm-server` remain local by default. Treat
them as confidential recovery points, not protection against theft or disk
failure. Optional Pi export can be prepared later without changing the backup
format or using an Open WebUI API key:

```bash
sudo bc250-maintenance backup-export status
sudo dnf install rsync-rrsync       # only if export is actually wanted
sudo bc250-maintenance backup-export enable
```

The export uses read-only `/usr/bin/rrsync` over the same restricted SSH :22
path. It exposes only the normal config/users backup directories, never rollback
data or `/etc/bc250-llm-server/maintenance.env`. Private SSH keys stay on the Pi.
The package reserves the export group for stable directory permissions, and the
backup producers preserve those directory modes on every run. Until the export
account is explicitly enabled, the reserved group has no members and newly published
artifacts remain private `0600`; after enablement they are published `0640`.

Before upgrading Open WebUI or moving the complete instance, take a stopped
filesystem snapshot:

```bash
sudo systemctl stop open-webui.service
sudo tar --xattrs --acls --numeric-owner -C /var/lib \
  -czf /ENCRYPTED-BACKUP/open-webui-full-$(date +%F).tar.gz open-webui
sudo systemctl start open-webui.service
```

Restore helpers require confirmation, verify checksum sidecars and create
rollback data before replacement.

## Open WebUI package baseline

Open WebUI package-owned provider/task/RAG/model-preset state is now managed by
`bc250-openwebui-setup`, not the maintenance scheduler:

```bash
sudo bc250-openwebui-setup init
OWUI_API_KEY=TEMPORARY_ADMIN_KEY sudo -E bc250-openwebui-setup status
```

The Qwen3.5 workspace preset is imported additively with request-level
`custom_params.think=false`; unrelated operator models and settings are not synchronized away.
The temporary administrator credential is not stored by this helper.

## Storage and retention

```bash
sudo bc250-status
sudo bc250-storage status
sudo bc250-model status production
sudo bc250-maintenance clean-cache
sudo bc250-maintenance run prune
sudo journalctl -u owui-maintenance@prune-uploads.service -n 100 --no-pager
```

`bc250-status` is the shared storage view for GGUFs, the main/task/embedding/agent Ollama stores,
Hugging Face cache, Open WebUI, Podman and journal usage. `clean-cache` requires
confirmation and removes rebuildable Hugging Face cache, dangling container
images and old system-wide journal archives; it does not delete GGUFs, Ollama
models or Open WebUI data. The journal vacuum affects archived logs for the
whole host, not only BC-250 services.

Model weights are never deleted automatically. Use `sudo bc250-model unregister` when source should be retained, or
`sudo bc250-model remove` when manager-owned source/state should also be deleted. `bc250-storage dedupe` requires the affected model/UI
services to quiesce successfully and reports any restoration failure. It retains both a validated
source GGUF and its Ollama blob while sharing identical XFS extents; `df` shows
reclaimed physical capacity even if `du` counts both logical files. The separate
`bc250-storage prune-sources` command removes only hash-verified source copies
after matching an Ollama blob, and requires explicit confirmation. `prune-40cu`
removes build caches only for kernels no longer installed.

Upload pruning calls Open WebUI's authenticated delete API so database, file
and vector state stay aligned. A manual `run prune`/`run all` preflights the protected
API key before starting the prune unit and reports the current age/ceiling/dry-run
policy without exposing the credential. It starts with `DRY_RUN=1`; review the current
run output before setting `DRY_RUN=0` in root-readable
`/etc/bc250-llm-server/maintenance.env`.

- `MAX_AGE_DAYS=0` disables the age rule.
- `MAX_TOTAL_GB=0` disables the known-size ceiling.
- Both rules cannot be disabled together.
- Unknown timestamps or sizes are preserved and reported.
- `MIN_FREE_GB` is the warning threshold shown by `sudo bc250-status`; it never
  deletes data.

Use generous retention and agree the policy with office users before enabling
deletion.

## Raspberry Pi maintenance companion

The Pi is primarily an availability/power companion, not a second appliance
controller. The BC-250 owns the decision whether shutdown is safe. Prepare the
server side with:

```bash
sudo bc250-maintenance companion enable
sudo bc250-maintenance companion status
sudo bc250-maintenance contract
```

`companion enable` enables the existing SSH server/firewall service, keeps HTTP
`:80` available as the office-readiness endpoint, and prepares a dedicated
`bc250-power-control` account whose authorized key must use the forced command
printed by the helper. It does **not** open `3000` or Ollama ports
`11434`-`11437`.

The stable remote request is:

```bash
sudo bc250-maintenance request-shutdown
```

That request runs the same package safe-power policy as the night timer. Active
maintenance, SSH, UI or Ollama traffic can therefore defer shutdown. A Pi should
never replace this with an unconditional remote `systemctl poweroff`.

The external machine owns its weekday morning WOL schedule and readiness retry
policy. Verify a real poweroff-to-WOL boot before relying on unattended nightly
poweroff. The complete shared interface is in
[`MAINTENANCE-CONTRACT.md`](MAINTENANCE-CONTRACT.md).

## Electricity use

Model warm-up is off by default because it runs inference and keeps a model
resident. When enabled, the default warm-up uses the standard office model with
a 15-minute keep-alive.

After-hours `poweroff` or `suspend` is also opt-in. The helper defers while
backup, prune, warm-up, SSH, web or Ollama activity is detected and retries up
to five times. `poweroff` normally saves more energy; `suspend` must first be
tested on the board. Requiring Wake-on-LAN makes the power action refuse to run
when WOL setup is not verified.

An automatic power action needs a deliberate morning restart path: tested WOL,
firmware scheduling, a managed smart plug or someone on site. When guided power
saving is enabled, configuring WOL is now the default recommendation and sets
`REQUIRE_WOL=1`; the power action then refuses to run if WOL setup cannot be
verified.

## Timers

```bash
systemctl list-timers 'owui-*' 'bc250-night-shutdown.timer'
sudo bc250-maintenance run backup
sudo bc250-maintenance run all
sudo bc250-maintenance status
```

| Task | Default schedule | State after `setup --defaults` |
|---|---|---|
| Configuration backup | Daily 17:45 | Enabled |
| Identity backup | Daily 18:00 | Enabled |
| Upload prune | Daily 18:10 | Disabled, dry-run |
| Model warm-up | Weekdays 07:35 | Disabled |
| Idle power action | Weekdays from 18:30 | Disabled |

Backup timers are persistent and run after the next boot if missed. Prune,
warm-up and power timers are non-persistent. Manual `run` output is scoped to the
just-completed systemd invocation, so older journal history does not bury the result.
All storage jobs share one lock and use idle I/O scheduling.
