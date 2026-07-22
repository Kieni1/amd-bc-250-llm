# Cyan Skillfish SMU governor

The RPM builds and installs `filippor/cyan-skillfish-governor` from release
v0.4.11, commit `60ab6e5b354f01f287c73d920990dcd618a674cc`.

The packaged configuration uses a 350-2000 MHz range and includes the tested
2000 MHz / 960 mV point. It is installed as `%config(noreplace)`, so upgrades do
not overwrite local tuning.

```bash
systemctl status cyan-skillfish-governor-smu.service
sudoedit /etc/cyan-skillfish-governor-smu/config.toml
sudo systemctl restart cyan-skillfish-governor-smu.service
journalctl -u cyan-skillfish-governor-smu.service -b
```

Frequency and voltage policy is entirely the operator's responsibility. The
40-CU tools do not inspect, cap or modify governor settings. Stability varies by
board; validate local changes with representative inference, temperature and
GPU-reset monitoring.
