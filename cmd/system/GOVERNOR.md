# Cyan Skillfish SMU governor

The RPM builds and installs `filippor/cyan-skillfish-governor` from release
v0.4.12, commit `be9537fc36f24b17570088cafa8c79365f80fee8`.

The packaged configuration uses a 350-1850 MHz range. The higher tested
2000 MHz / 960 mV point remains available in the curve for operators who
deliberately raise the maximum. The configuration is installed as
`%config(noreplace)`, so upgrades do not overwrite local tuning; the 1850 MHz
default therefore applies automatically only to fresh installations.

The packaged `[gpu-usage]` policy keeps the established `method = "busy-flag"`
and now declares `fix-freq = false` explicitly. Set `fix-freq = true` only on a
system where enabling all eight CPU cores causes incorrect
`current_gfxclk_frequency` reporting. The optional `method = "kernel"` requires
a separately patched compatible kernel; the presence of the 40-CU replacement
module alone is not a reason to select it.

```bash
systemctl status cyan-skillfish-governor-smu.service
sudoedit /etc/cyan-skillfish-governor-smu/config.toml
sudo systemctl restart cyan-skillfish-governor-smu.service
journalctl -u cyan-skillfish-governor-smu.service -b
sudo bc250-verify
```

Frequency and voltage policy is entirely the operator's responsibility. The
40-CU tools do not inspect, cap or modify governor settings. Stability varies by
board; validate local changes with representative inference, temperature and
GPU-reset monitoring.
