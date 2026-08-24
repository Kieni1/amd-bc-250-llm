# HTTPS

The testing package intentionally installs HTTP only. Until HTTPS is configured,
credentials, prompts and documents are unencrypted on the network; keep the
endpoint on a trusted LAN.

## Operator checklist

1. Assign a stable IP address or DHCP reservation.
2. Use an organisation-controlled DNS name when possible.
3. Obtain a certificate from a trusted issuer. A direct-IP certificate must
   contain that exact IP address as an IP subject alternative name.
4. Copy the packaged `https-example.conf` from
   `/usr/share/doc/bc250-llm-server/` to `/etc/nginx/conf.d/` and replace every
   placeholder.
5. Remove or rename the default HTTP configuration when forced HTTPS is ready.
6. Validate nginx, open HTTPS in the active firewall zone and test from another
   machine.

```bash
sudo nginx -t
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
sudo systemctl reload nginx
```

Certificate issuance, DNS, client trust, renewal and private-key protection are
operator responsibilities. Do not remove working HTTP access until the HTTPS
path and renewal procedure have been tested.
