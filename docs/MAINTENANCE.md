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

Backups under `/var/backups/bc250-llm-server` are root-only but remain on the
same disk. Treat them as confidential recovery points, not protection against
theft or disk failure. Copy them to encrypted storage controlled by the office.

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
sudo bc250-model cleanup production --list
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

Model weights are never deleted automatically. Use `bc250-model cleanup` for
model lifecycle operations. `bc250-storage dedupe` requires the affected model/UI
services to quiesce successfully and reports any restoration failure. It retains both a validated
source GGUF and its Ollama blob while sharing identical XFS extents; `df` shows
reclaimed physical capacity even if `du` counts both logical files. The separate
`bc250-storage prune-sources` command removes only hash-verified source copies
after matching an Ollama blob, and requires explicit confirmation. `prune-40cu`
removes build caches only for kernels no longer installed.

Upload pruning calls Open WebUI's authenticated delete API so database, file
and vector state stay aligned. It starts with `DRY_RUN=1`; review the journal
before setting `DRY_RUN=0` in root-readable
`/etc/bc250-llm-server/maintenance.env`.

- `MAX_AGE_DAYS=0` disables the age rule.
- `MAX_TOTAL_GB=0` disables the known-size ceiling.
- Both rules cannot be disabled together.
- Unknown timestamps or sizes are preserved and reported.
- `MIN_FREE_GB` is the warning threshold shown by `sudo bc250-status`; it never
  deletes data.

Use generous retention and agree the policy with office users before enabling
deletion.

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
firmware scheduling, a managed smart plug or someone on site.

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
warm-up and power timers are non-persistent. All storage jobs share one lock and
use idle I/O scheduling.
