# Cyan Skillfish governor

## Commands

```bash
systemctl status cyan-skillfish-governor-smu.service
sudoedit /etc/cyan-skillfish-governor-smu/config.toml
sudo systemctl restart cyan-skillfish-governor-smu.service
journalctl -u cyan-skillfish-governor-smu.service -b
sudo bc250-verify
```

The RPM pins `filippor/cyan-skillfish-governor` v0.4.12 at commit
`be9537fc36f24b17570088cafa8c79365f80fee8`. Fresh installations use a
350–1850 MHz range. The 2000 MHz / 960 mV point remains available in the curve
for deliberate operator testing. Ordinary RPM upgrades preserve local tuning via
`%config(noreplace)`. A full guided-installer rerun is the deliberate green-field
convergence path and backs up then restores this file to the current package
default.

The packaged usage policy is:

```text
fix-freq = false
method = "busy-flag"
```

Use `fix-freq = true` only when an eight-core configuration misreports
`current_gfxclk_frequency`. The `kernel` method requires a separately patched
compatible kernel; the 40-CU module alone does not provide it.

Frequency and voltage remain the operator's responsibility. Validate every
change with representative inference, temperature monitoring, output checks and
GPU-reset logs. CU tools do not alter governor policy.
