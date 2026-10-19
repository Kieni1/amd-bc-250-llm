# Operations and package boundary

## Operator model

The user should see an appliance, not its engineering history.

Normal public paths should be understandable through:

```text
install / supported upgrade
bc250 status
bc250 health
bc250 verify
bc250 model ...
Web interface
supported maintenance/recovery commands
```

Keep internal helpers private unless there is a durable operator need for them.

## Package identity

Current line: `bc250-llm-server-0.14.1-1.2`.

Never reuse an already-published NVR for changed bytes.

## Package ownership rules

The RPM owns package files, service definitions and package configuration. It should not own experimental boot/kernel/Mesa state or development workbench metadata.

Keep scriptlets small and deterministic. Prefer systemd/RPM/Fedora mechanisms over custom orchestration when they already provide the needed behavior.

## Persistent data and operator state

Protect supported persistent state during upgrade, uninstall and recovery.

Operator-added model registrations are not package drift. Do not unregister them merely to satisfy a package test or manufacture an exact catalog count.

For destructive maintenance:

- identify what will change;
- establish rollback/backup material first when applicable;
- fail closed if the required current-state inspection is unavailable;
- verify cleanup/restoration afterward.

## Network boundary

Current intended shape includes:

- Open WebUI backend loopback-only on `127.0.0.1:3000`;
- Tika private to the application network;
- user-facing web traffic through nginx where configured;
- internal Ollama lanes protected according to current firewall policy.

Claims about external network exposure require an external vantage. Same-host `curl`/socket checks prove reachability/listening, not LAN isolation.

## Human output

Prefer:

- `Web interface` for user-facing UI language;
- concise cause before implementation detail;
- one required next action;
- JSON/diagnostic output for machine detail;
- TTY-only color and `NO_COLOR` support;
- text that remains complete without color.

## Recovery/uninstall boundary

A simplification pass may delete implementation complexity, but must not casually weaken:

- persistent-data preservation;
- backup/restore integrity;
- ownership/permission guarantees;
- deterministic uninstall behavior;
- safe recovery from interrupted operations.

When recovery behavior is touched, use the deeper playbook in `13_RESILIENCE_RECOVERY_AND_SECURITY_PLAYBOOK.md`.
