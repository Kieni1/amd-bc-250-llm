# BC-250 maintenance companion contract

Contract version: **1**

This document defines the stable BC-250-facing interface for a small external
maintenance companion such as a Raspberry Pi. The BC-250 remains responsible
for office-service behavior and deciding whether shutdown is safe. The Pi may
wake and observe the appliance, request a safe shutdown, and optionally pull
published backup artifacts.

## Responsibility boundary

| Responsibility | Owner |
|---|---|
| Office LLM service | BC-250 |
| Decide whether shutdown is safe | BC-250 |
| Automatic after-hours shutdown | BC-250 |
| Morning Wake-on-LAN | External companion |
| Verify office readiness after wake | External companion |
| Produce local backups | BC-250 |
| Optional off-device backup copy/retention | External companion |

The external companion must not use raw `systemctl poweroff` as its normal
remote-control interface. Use the package safe-power request instead.

## Network/readiness contract

The office-facing readiness endpoint is:

```text
HTTP http://<BC250_HOST>/
TCP 80
```

Administrative/restricted maintenance SSH is TCP 22. The following are internal
appliance ports and are not part of the companion readiness contract:

```text
3000
11434
11435
11436
11437
```

Enabling the companion therefore needs only the existing office HTTP service and
SSH. Wake-on-LAN is an Ethernet magic packet and does not require opening a host
firewall UDP port.

## Wake-on-LAN contract

The BC-250 package owns NIC WOL configuration. A configured interface should
report:

```text
Wake-on: g
```

The external companion owns its wake schedule, retry policy and broadcast
address. Before automatic BC-250 poweroff is relied upon, perform a real
powered-off/S5 Wake-on-LAN test on the installed hardware.

## Safe shutdown contract

The stable external request is:

```bash
sudo bc250-maintenance request-shutdown
```

That request delegates to the package safe-power policy. The BC-250 may defer
shutdown while maintenance, SSH, UI or Ollama activity is present. A defer is a
normal safe outcome, not a reason for the external companion to force poweroff.

Prepare the restricted SSH side with:

```bash
sudo bc250-maintenance companion enable
sudo bc250-maintenance companion status
```

The package prints the exact forced-command `authorized_keys` template. The
power-control key is scoped to the package-internal
`restrict,command="/usr/bin/sudo /usr/bin/bc250-maintenance request-shutdown-companion"`
path. That path preserves the OpenSSH `SSH_CONNECTION` tuple and exempts only that
one authenticated control connection from the protected-TCP test; the tuple must be found exactly
once or the request fails closed. The companion path still uses the configured safe-power ports,
power action and WOL requirement, and any second SSH session still defers shutdown. Operators continue to use the public
`sudo bc250-maintenance request-shutdown` command. Do not use the internal companion
command as a general bypass.

Private keys remain on the external companion. If the Pi has a stable address,
the operator may additionally add an OpenSSH `from="PI_IP"` restriction. Pi-side
SSH should pin the BC-250 host key and use `IdentitiesOnly=yes`; those Pi-local
settings are not stored by this package.

## Local backup producer contract

Configuration backups are published under:

```text
/var/backups/bc250-llm-server/config/
  owui-config-YYYY-MM-DD_HHMMSS.tar.gz
  owui-config-YYYY-MM-DD_HHMMSS.tar.gz.sha256
```

Identity backups are published under:

```text
/var/backups/bc250-llm-server/users/
  owui-users-YYYY-MM-DD_HHMMSS.sql.gz
  owui-users-YYYY-MM-DD_HHMMSS.sql.gz.sha256
```

Only an artifact with its matching SHA-256 sidecar is a complete exportable
pair. Routine backups are intentionally not a full RAG/document/model image;
they exclude bulky uploads/vector/cache data and model stores.

Optional read-only export is prepared with:

```bash
sudo bc250-maintenance backup-export enable
sudo bc250-maintenance backup-export status
```

Fedora 44 supplies `/usr/bin/rrsync` in the `rsync-rrsync` package. The package
is not silently installed; when needed use:

```bash
sudo dnf install rsync-rrsync
```

The export account/group is `bc250-backup-export`. Export is read-only through
SSH/rrsync, uses separate config/users key scopes, does not expose rollback
backups or maintenance secrets, and does not require another firewall port. The
forced-command scopes are:

```text
restrict,command="/usr/bin/rrsync -ro /var/backups/bc250-llm-server/config"
restrict,command="/usr/bin/rrsync -ro /var/backups/bc250-llm-server/users"
```

Use independent Ed25519 keys for power control, config backup and users backup.
One compromised key should not silently expand into another maintenance scope.

## Backup permissions when export is enabled

| Path/artifact | Group | Mode |
|---|---|---:|
| `/var/backups/bc250-llm-server` | `bc250-backup-export` | `0710` |
| `config/` | `bc250-backup-export` | `0750` |
| `users/` | `bc250-backup-export` | `0750` |
| published config/users artifacts | `bc250-backup-export` | `0640` |

`rollback/` remains private. If backup export is not enabled, the reserved group has
no user members and config/users artifacts remain private `0600`; the `0750`
directories still retain the dormant group so later export enablement does not require
permission repair after every backup run.

## Open WebUI credentials

The external companion does not need an Open WebUI API key for WOL, readiness,
safe shutdown or backup transport. `OWUI_API_KEY` remains a BC-250-local
protected maintenance credential.

## Schedule and retention convention

Cross-machine schedules use local `Europe/Zurich` wall-clock time unless a site
deliberately configures otherwise. The BC-250 owns after-hours shutdown timing;
the external companion owns morning wake timing. Do not duplicate shutdown
policy on the companion.

Current BC-250 local backup defaults are configuration at 17:45 and identity at
18:00, with local retention counts of 7 and 14 respectively. These are producer
policy defaults, not proof that a new backup exists. A Pi should discover complete
artifact/sidecar pairs and may keep a different, longer off-device retention.

## Compatibility

Breaking this interface requires increasing the contract version. Deployment
values such as IP address, MAC address, public-key fingerprint, wake time and Pi
retention policy do not by themselves change the contract version.
