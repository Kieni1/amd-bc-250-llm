# Uninstall

Persistent model, Open WebUI and backup data are intentionally retained.

Get the files for comparison after uninstall first, repeat after uninstall for 
possible leftovers

```bash
sudo find /usr/local/bin /etc/systemd/system /etc/systemd/zram-generator.conf.d /etc/modprobe.d /var/llm /var/swap /var/lib/open-webui /var/backups/bc250-llm-server \( -type f -o -type l \) -print0 | while IFS= read -r -d '' file; do rpm -qf "$file" >/dev/null 2>&1 || printf '%s\n' "$file"; done
```

## Restore 40-CU changes first

When the 40-CU helper has been used, restore the stock state before removing the
RPM:

```bash
sudo bc250-40cu disable
# After the reboot:
sudo bc250-40cu restore
sudo reboot
sudo bc250-40cu status
```

If the live manager's boot service was enabled, remove its copied service state
before removing the RPM:

```bash
sudo bc250-cu-live-manager uninstall-service
```


## Remove optional host profiles

These settings live outside RPM ownership and are retained deliberately. Remove
them before uninstalling when you want to return to Fedora defaults:

```bash
sudo bc250-ollama-profile reset
sudo bc250-swap-profile remove
sudo bc250-memory-profile remove
sudo reboot
```

Task and agent setup also creates local systemd units outside RPM ownership.
Remove them when those isolated instances are no longer wanted:

```bash
sudo systemctl disable --now ollama-task.service ollama-agent.service
sudo rm -f /etc/systemd/system/ollama-task.service
sudo rm -f /etc/systemd/system/ollama-agent.service
sudo systemctl daemon-reload
```

The memory and swap commands require explicit confirmation. Skip a command when
you intentionally want to retain that host configuration.

## Remove the main package

```bash
sudo dnf remove bc250-llm-server
```

The package does not remove Ollama installed by `bc250-install-ollama`.

To reverse the global network policy applied by the testing RPM:

```bash
sudo firewall-cmd --permanent --remove-service=http
sudo firewall-cmd --reload
sudo setsebool -P httpd_can_network_connect 0
```

## Review retained state

```text
/etc/bc250-llm-server/
/etc/cyan-skillfish-governor-smu/
/etc/systemd/system/ollama.service.d/
/etc/systemd/system/ollama-task.service
/etc/systemd/system/ollama-agent.service
/etc/systemd/zram-generator.conf.d/
/var/swap/bc250-llm.swap
/var/llm/
/var/llm/ollama-task/
/var/llm/ollama-agent/
/var/lib/ollama/
/var/lib/open-webui/
/var/backups/bc250-llm-server/
```

Also review:

- operator-added HTTPS configuration and certificates;
- firewalld changes;
- the global SELinux boolean `httpd_can_network_connect`;
- Wake-on-LAN configuration;
- `.rpmsave` and `.rpmnew` files;
- local coding-agent Gitea credentials under user home directories.

Remove retained data only after backups have been verified. Example:

```bash
sudo rm -rf /var/llm /var/lib/open-webui
sudo rm -rf /var/backups/bc250-llm-server
```

Those commands are destructive and are not run by RPM.
For good measures reinstall the OS to avoid leftovers.
