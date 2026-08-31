# Hardening the testing deployment

The default profile is for a trusted LAN. Choose the controls below before the
host enters a shared, guest, routed or otherwise untrusted network.

## Close LAN web access

```bash
sudo firewall-cmd --get-active-zones
sudo firewall-cmd --permanent --remove-service=http
sudo firewall-cmd --reload
```

Open WebUI remains local at `http://127.0.0.1:3000`.

## Restrict HTTP to one subnet

Replace both examples with the active zone and intended office subnet:

```bash
ZONE=public
TRUSTED_CIDR=192.168.1.0/24
sudo firewall-cmd --zone="$ZONE" --permanent --remove-service=http
sudo firewall-cmd --zone="$ZONE" --permanent \
  --add-rich-rule="rule family=ipv4 source address=$TRUSTED_CIDR service name=http accept"
sudo firewall-cmd --reload
sudo firewall-cmd --zone="$ZONE" --list-all
```

## Check Ollama exposure

```bash
sudo systemctl is-active firewalld
sudo firewall-cmd --list-all
bc250-verify-lan SERVER_IP
```

Ollama ports `11434`–`11436` have no authentication and must remain blocked
from untrusted networks. The wildcard host listeners are intentional so the
rootful Open WebUI container can use `host.containers.internal`; firewalld is
the LAN boundary. `bc250-verify` warns about unexpected listener shapes or an
inactive/incorrect firewall, and `bc250-verify-lan` checks exposure from a
second LAN machine.

## Confidential documents and knowledge bases

For confidential RAG use, require authentication, keep knowledge bases private
or restricted to the necessary users/groups, disable public/open sharing, and
leave cloud model/API connections and web search disabled unless an operator
explicitly approves them. `/var/lib/open-webui/webui.db`, `uploads/` and
`vector_db/` contain or derive from confidential material; protect their backups
accordingly. Keep the authoritative `/srv/bc250-documents` tree `root:root` mode `0750`; the importer creates private knowledge bases owned by the Open WebUI API-key account and does not publish them. Configure group access explicitly after sync. See [`RAG.md`](RAG.md).

## Add HTTPS or stop services

Follow [`HTTPS.md`](HTTPS.md) for encrypted access. Do not expose Open WebUI's
first-registration page before creating the administrator account.

To retain data while stopping the stack:

```bash
sudo systemctl disable --now open-webui.service tika.service nginx.service
sudo systemctl disable --now ollama.service
sudo systemctl disable --now ollama-task.service ollama-agent.service
```

Re-enable only the services required by the next test.
