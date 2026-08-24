# Deployment

The default deployment is a pre-production service for one trusted office LAN.
It is not suitable for direct Internet exposure.

## Check the stack

```bash
sudo bc250-status
sudo bc250-verify
sudo systemctl status \
  cyan-skillfish-governor-smu.service \
  ollama.service open-webui.service tika.service nginx.service
bc250-verify-lan SERVER_IP
```

Open `http://SERVER_IP/` and register the first Open WebUI account immediately;
it becomes the administrator.

## Services and ports

| Service | Listener | Purpose |
|---|---|---|
| nginx | `SERVER_IP:80` | Trusted-LAN entry point |
| Open WebUI | `127.0.0.1:3000` | Local UI behind nginx |
| Ollama main | `0.0.0.0:11434` | Chat, experiments and embeddings |
| Ollama task | `0.0.0.0:11435` | Optional task model |
| Ollama agent | `0.0.0.0:11436` | Optional coding/agentic models |
| Tika | private container network | Document extraction |

The rootful Open WebUI container requires the host Ollama listeners. The RPM
does not open ports `11434`–`11436` in firewalld; keep them blocked from
untrusted networks. If firewalld is disabled, enabled Ollama instances are
reachable on all configured host interfaces.

## Persistent data

```text
/var/lib/bc250-llm-server      GGUFs, rendered Modelfiles and Ollama stores
/var/cache/bc250-llm-server    Hugging Face and 40-CU build caches
/var/lib/open-webui            Accounts, chats, uploads and vector state
/var/backups/bc250-llm-server  Verified local backups and rollback copies
```

Local backups contain private office data and share the appliance disk. Copy
them to encrypted office-controlled storage for protection against disk loss.
Take a complete stopped-service snapshot of `/var/lib/open-webui` before an
Open WebUI upgrade.

The Open WebUI Quadlet uses a private `:Z,U` volume mount. Let Podman apply the
container label when the service starts; do not recursively relabel the data as
ordinary host content.

## Preflight for large models

```bash
sudo bc250-memory-profile status
sudo bc250-swap-profile status
df -h / /var/lib/bc250-llm-server
```

See [`MEMORY.md`](MEMORY.md) for the reviewed unified-memory profile and
[`HARDENING.md`](HARDENING.md) for network closure options.
