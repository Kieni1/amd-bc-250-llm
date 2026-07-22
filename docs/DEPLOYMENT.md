# Deployment notes

This package is a trusted-LAN testing profile, not an Internet-facing
appliance.

## Services

```bash
sudo systemctl status \
  cyan-skillfish-governor-smu.service \
  ollama.service tika.service open-webui.service nginx.service
```

Open WebUI is published only on `127.0.0.1:3000`; nginx exposes it through the
standard HTTP service. Tika remains private on the Podman network.

Ollama listens on `0.0.0.0:11434` so the rootful container can access the host.
Task and agent setup add `ollama-task.service` on `11435` and
`ollama-agent.service` on `11436`. The package does not open any of these ports
in firewalld. Verify the active firewall zone and do not expose the
unauthenticated APIs to untrusted networks. **If firewalld is inactive, enabled
Ollama instances are exposed on every configured host interface.**

## First login

Open `http://SERVER_IP/` from the trusted LAN and register the first account
immediately. It becomes the Open WebUI administrator.

## HTTPS

HTTP sends credentials and prompts in clear text. Follow `docs/HTTPS.md` before
using untrusted networks.

For a short set of closure options—remove LAN access, restrict it to a subnet,
add HTTPS or stop the stack—see `HARDENING.md`.

## Persistent data

```text
/var/lib/bc250-llm-server             GGUF files, rendered Modelfiles and Ollama stores
/var/cache/bc250-llm-server           Hugging Face cache and reusable 40-CU kernel source
/var/lib/open-webui                   Open WebUI state
/var/backups/bc250-llm-server         verified maintenance backups and rollback copies
```

The Open WebUI Quadlet uses a private `:Z,U` volume mount. Do not run
`restorecon -RF /var/lib/open-webui`; Podman applies the private container label
when the service starts.

## Verification

```bash
sudo bc250-verify
bc250-verify-lan SERVER_IP
sudo journalctl -u open-webui.service -b -n 100 --no-pager
```


## Memory and swap preflight

Before downloading multi-gigabyte models, check both filesystem and unified
memory configuration:

```bash
sudo bc250-memory-profile status
sudo bc250-swap-profile status
df -h / /var/lib/bc250-llm-server
```

Read `MEMORY.md` before changing kernel arguments. RPM scriptlets never apply
GTT/TTM, zram or disk-swap settings. The separate guided installer can invoke
the documented profiles and pauses for reboot.

## Sensor-driver preflight

The supported default is `nct6683`. An optional out-of-tree `nct6687` PWM driver
must not be loaded at the same time. See `SENSORS.md`.
