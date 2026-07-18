# HTTPS is an operator responsibility

The testing RPM intentionally installs **HTTP only**. It does not request,
generate, trust or renew certificates and it does not claim that the resulting
HTTP deployment is suitable for production.

Until HTTPS is configured, credentials, prompts and uploaded documents are
unencrypted on the network. Keep the service on a trusted LAN.

## Recommended approach

1. Assign a stable IP address or DHCP reservation.
2. Use a DNS name controlled by your organisation when possible.
3. Obtain a certificate from your organisation's CA or another trusted issuer.
   For direct-IP HTTPS, the certificate must contain the exact IP address as an
   IP subject alternative name.
4. Copy the packaged `https-example.conf` from the documentation directory to
   `/etc/nginx/conf.d/`, replace every placeholder, and remove or rename
   `/etc/nginx/default.d/bc250-llm-server.conf` if you want forced HTTPS.
5. Open `https` in firewalld, test from another client, and only then consider
   redirecting port 80 to 443.

```bash
sudo nginx -t
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
sudo systemctl reload nginx
```

Certificate issuance, client trust, DNS, renewal and private-key protection are
outside this RPM's scope.
