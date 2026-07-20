# Move beyond the trusted-LAN testing profile

The packaged defaults favor a quick trusted-LAN test. Before the host is placed
on a shared, guest, routed or otherwise untrusted network, choose the controls
that match the deployment.

## Close all LAN web access

Remove the HTTP service from the active firewalld zone:

```bash
sudo firewall-cmd --get-active-zones
sudo firewall-cmd --permanent --remove-service=http
sudo firewall-cmd --reload
```

Open WebUI remains available locally through `http://127.0.0.1:3000`. Restore
LAN access later with `--add-service=http` only when that is intentional.

## Limit HTTP to one trusted subnet

Replace the example zone and subnet with the active values:

```bash
ZONE=public
TRUSTED_CIDR=192.168.1.0/24
sudo firewall-cmd --zone="$ZONE" --permanent --remove-service=http
sudo firewall-cmd --zone="$ZONE" --permanent \
  --add-rich-rule="rule family=ipv4 source address=$TRUSTED_CIDR service name=http accept"
sudo firewall-cmd --reload
```

List the result with `sudo firewall-cmd --zone="$ZONE" --list-all`.

## Add encrypted access

Follow `HTTPS.md`, verify certificate renewal, then remove unrestricted HTTP or
retain it only as an HTTPS redirect. Do not expose the first-registration page
before the administrator account has been created.

## Protect Ollama

The primary Ollama listens on `0.0.0.0:11434` so the rootful Open WebUI
container can reach it. Optional task and agent services similarly use `11435`
and `11436`. The RPM does not open these ports in firewalld. If firewalld is
stopped or disabled, every enabled unauthenticated Ollama API is exposed on host
interfaces.

```bash
sudo systemctl is-active firewalld
sudo firewall-cmd --list-all
bc250-verify-lan SERVER_IP
```

Keep firewalld active or redesign the deployment so Ollama and Open WebUI share
a private container network.

## Stop the application stack

```bash
sudo systemctl disable --now open-webui.service tika.service nginx.service
sudo systemctl disable --now ollama.service
sudo systemctl disable --now ollama-task.service ollama-agent.service
```

This retains models, accounts and documents. Re-enable only the services needed
for the next test.
