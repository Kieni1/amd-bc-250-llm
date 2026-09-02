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
350–1850 MHz range. The 2000 MHz / 960 mV point remains in the curve only for
deliberate operator testing. `%config(noreplace)` preserves local tuning on
upgrades.

The packaged usage policy is:

```text
fix-freq = false
method = "busy-flag"
```

Use `fix-freq = true` only when an eight-core configuration misreports
`current_gfxclk_frequency`. The `kernel` method requires a separately patched
compatible kernel; the 40-CU module alone does not provide it.

## 2026-08-31 governor revalidation

The appliance comparison found that normal `busy-flag` control stayed very close
to a fixed 1850-MHz run while still returning to low clocks between work. Fixed
1750 MHz reduced prefill by roughly five percent in the tested Gemma E2B/LFM2.5
workloads, so 1850 remains the normal package maximum rather than adopting 1750
as the default.

One important upstream-helper behavior was exposed: on the pinned v0.4.12 stack,
`cyan-skillfish-performance-mode --on` selected the 2000-MHz safe point even
though `[frequency-range].max` was 1850. It produced a measurable prefill gain but
also higher power/temperature. Therefore **do not interpret `--on` as "use the
package maximum"**. For a deliberate fixed normal-maximum comparison use:

```bash
sudo cyan-skillfish-performance-mode --fixed-frequency 1850
# return to normal dynamic policy afterwards
sudo cyan-skillfish-performance-mode --off
```

For an optional efficiency comparison, 1750 MHz can be tested explicitly with
`sudo cyan-skillfish-performance-mode --fixed-frequency 1750`; the reviewed run
showed lower power/temperature but about a five-percent prefill cost, so it is not
the package default.

Use 2000 MHz only as an explicit operator experiment and validate the individual
board. `bc250-verify` warns if the observed active clock is above the configured
normal maximum, which helps catch a forgotten D-Bus/performance override.

Frequency and voltage remain the operator's responsibility. Validate every
change with representative inference, temperature monitoring, output checks and
GPU-reset logs. CU tools do not alter governor policy.
