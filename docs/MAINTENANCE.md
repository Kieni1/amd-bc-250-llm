# Office maintenance

The maintenance tools are optional and disabled by the RPM. They are designed
for one small trusted-LAN office appliance: keep private data local, bound disk
growth, avoid unnecessary model residency and power the host down when nobody
is using it.

## Fast safe setup

Enable only the two verified local backups:

```bash
sudo bc250-maintenance setup --defaults
sudo bc250-maintenance run backup
sudo bc250-maintenance status
```

This does **not** enable upload deletion, model warm-up, Wake-on-LAN or an
automatic power action. For a guided setup of those choices, run:

```bash
sudo bc250-maintenance setup
```

The interactive command asks for the pruning policy, optional warm-up, and the
weekday power time/action. It does not assume office hours. Re-running setup is
safe; it edits the existing private configuration and preserves backup data.

Disable every optional schedule without deleting configuration or data:

```bash
sudo bc250-maintenance disable
```

## Privacy and backups

`backup-config` uses SQLite's online backup API, verifies the copied database,
excludes the live WAL/SHM files and writes a SHA-256 sidecar. It contains Open
WebUI configuration, chats and account data, but deliberately excludes bulky
`uploads`, `vector_db` and `cache` directories. `backup-users` is a
schema-matched identity export for selective account recovery; it includes
password hashes, API keys and access-control data.

Both backup directories are root-only. Treat every archive as confidential.
The default destination is on the same disk as Open WebUI, so it protects
against application mistakes but not theft or disk failure. Periodically copy
`/var/backups/bc250-llm-server` and a complete stopped-service snapshot of
`/var/lib/open-webui` to encrypted office-controlled storage. Open WebUI's own
guidance likewise recommends backing up the complete persistent data directory
and storing a copy on a different disk.

Before an Open WebUI upgrade or complete migration, take the full snapshot:

```bash
sudo systemctl stop open-webui.service
sudo tar --xattrs --acls --numeric-owner -C /var/lib \
  -czf /ENCRYPTED-BACKUP/open-webui-full-$(date +%F).tar.gz open-webui
sudo systemctl start open-webui.service
```

Do not place that archive in an unencrypted consumer cloud account. Restore
commands reject a missing checksum by default, require Open WebUI to be
stopped, verify SQLite integrity and create rollback data before replacement.

## Storage and upload retention

`bc250-maintenance status` reports GGUF sources, Ollama stores, the Hugging Face
cache, Open WebUI data, local backups and free filesystem space. Model weights
are never deleted automatically; review and remove test models explicitly with
`bc250-model cleanup`.

Upload pruning calls Open WebUI's authenticated file-delete API so database,
stored file and vector state are handled together. It starts with `DRY_RUN=1`.
The administrator API key acts with that administrator's permissions and is
stored only in root-readable `/etc/bc250-llm-server/maintenance.env`.

```bash
sudo bc250-maintenance run prune
sudo journalctl -u owui-maintenance@prune-uploads.service -n 100 --no-pager
sudoedit /etc/bc250-llm-server/maintenance.env  # set DRY_RUN=0 after review
```

- `MAX_AGE_DAYS=0` disables only the age rule.
- `MAX_TOTAL_GB=0` disables only the known-size ceiling.
- Both rules cannot be zero.
- Files with an unknown timestamp or size are preserved from ceiling-based
  deletion and reported for manual review.
- `MIN_FREE_GB` is a status warning threshold; it never deletes data.

The prune operation is not a backup policy. A deleted upload may still be
referenced by office work, so use a generous retention period and review the
dry-run log with users first.

## Electricity use

Warm-up remains disabled by default because it performs inference and keeps a
model resident even if no user arrives. When explicitly enabled, the packaged
default is the current standard office model with only `15m` keep-alive.

After-hours power saving is also opt-in. `poweroff` is the guided default and
normally saves more energy than suspend; `suspend` is available when it has
been tested on the board. The helper retries five times at 15-minute intervals
and defers whenever a backup, prune, warm-up, SSH, web or Ollama TCP session is
active. Wake-on-LAN can be required; if required setup fails, the power action
is refused.

Automatic power-off needs a deliberate restart plan: tested Wake-on-LAN,
firmware scheduling, a managed smart plug or a person on site. The package does
not provide the external morning wake host.

## Timers and manual operation

```bash
systemctl list-timers 'owui-*' 'bc250-night-shutdown.timer'
sudo bc250-maintenance run backup
sudo bc250-maintenance run all
sudo bc250-maintenance status
```

Backup timers are persistent, so a backup missed while the machine was powered
off runs after the next boot. All backup/prune jobs share one lock and use idle
I/O scheduling, preventing simultaneous database and storage maintenance.
Prune, warm-up and power timers are deliberately non-persistent.

Default timer times are local system time:

| Task | Schedule | Default state |
|---|---|---|
| Configuration backup | Daily 17:45 | Disabled until setup |
| Identity backup | Daily 18:00 | Disabled until setup |
| Upload prune | Daily 18:10 | Disabled; dry-run |
| Model warm-up | Weekdays 07:35 | Disabled |
| Idle power action | Weekdays from 18:30, five attempts | Disabled |

Configuration and retention paths are in
`/etc/bc250-llm-server/maintenance.env`. The generated power schedule override
is `/etc/systemd/system/bc250-night-shutdown.timer.d/schedule.conf`.

References: [Open WebUI backups](https://docs.openwebui.com/tutorials/maintenance/backups/),
[Open WebUI API-key permissions](https://docs.openwebui.com/features/authentication-access/api-keys/),
and [systemd timer persistence](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html).
