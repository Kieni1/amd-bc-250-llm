# BC-250 hardware and platform

This is the canonical hardware/runtime guide. It combines memory policy, sensors, governor behavior and live CU routing. The normal CU workflow is intentionally small: configure with `sudo bc250-cu-live-manager` and verify with `sudo bc250-40cu status`.

## Memory profile

The BC-250 shares 16 GiB of GDDR6 between CPU and GPU, so model residency depends
on the kernel's TTM limits as well as on real free host memory and swap. The
reviewed fresh-machine profile is now intentionally small:

```text
ttm.pages_limit=4194304
ttm.page_pool_size=4194304
```

The profile is package-managed. `sudo bc250 install` reconciles it idempotently and requests a reboot only when the active kernel state requires one. `sudo bc250 status` and `sudo bc250 verify` are the supported operator checks. Internally, the installer removes obsolete `amdgpu.gttsize=...` and full `amdgpu.ppfeaturemask=...` overrides before applying the two TTM limits.


### 2026-08-31 Fedora 44 revalidation

The previous package profile also forced `amdgpu.gttsize=14750` and
`amdgpu.ppfeaturemask=0xffffffff`. A reboot-by-reboot comparison on kernel
`7.1.10-200.fc44.x86_64`, Mesa 26.1.8, the then-used modified 40-CU AMDGPU module and
Ollama 0.33.2 found (historical evidence; the current package no longer ships that module backend):

- removing `amdgpu.gttsize` did not reduce the exposed GTT aperture or measurable
  Gemma E2B/LFM2.5 context performance;
- removing the explicit full `ppfeaturemask` likewise did not change the tested
  Vulkan/Ollama stability or throughput under the normal busy-flag governor;
- the driver reported `amdgpu.gttsize=-1` and selected its normal power-feature
  mask while the two 4,194,304-page TTM limits remained active;
- no tested configuration used swap or produced the known Vulkan device-loss,
  command-submission OOM or compute-ring failure signatures.

Current upstream Linux [AMDGPU module-parameter documentation](https://docs.kernel.org/gpu/amdgpu/module-parameters.html)
marks `amdgpu.gttsize` deprecated and says its default is the TTM-specified value.
The package therefore lets AMDGPU/TTM derive the aperture from TTM instead of
preserving an obsolete duplicate override. The explicit full power-feature mask is no longer a
fresh-install requirement; operator overclock/experimental power-control work
remains outside the appliance baseline.

#### Kernel policy

The appliance follows the current Fedora-supported kernel rather than maintaining historical
release-number warning ranges. CU routing now uses the live manager on the stock Fedora AMDGPU path;
verification checks live saved/routed WGP state rather than maintaining a package-built replacement module.
No newer BC-250 evidence justifies changing TTM sizing, `ppfeaturemask`, the governor or Mesa defaults.

The two TTM values describe a 16-GiB ceiling at 4-KiB pages. They do **not**
reserve 16 GiB at boot and do not mean a 16-GiB GGUF will fit: the OS, Ollama,
KV/cache and other services share the same physical memory.

IOMMU is not required by the qualified appliance baseline. Do not force `amd_iommu=on` on an unqualified BIOS configuration; BIOS-enabled SVM/IOMMU operation is a separate device-qualification choice. `nomodeset` is only for installation recovery and must not remain on the normal LLM boot. The package does not automatically add `mitigations=off`.

The package-managed zram/disk-swap profile remains a pressure safety net; it is not a way
to make an oversized model GPU-resident. Watch `MemAvailable`, swap growth and
`ollama ps` during long-context tests.

### External BC-250 setup references

Community guidance remains useful, but kernel-specific recipes age quickly. The
package was cross-checked against the ElektricM kernel/quick-reference material
and current Linux AMDGPU parameter documentation. The package values above are
based on BC-250 device evidence rather than copying kernel-version-specific recipes
verbatim.

## Sensors and fan control

### Check the active hardware interface

```bash
lsmod | grep -E '^nct6683|^nct6687'
sensors
sudo bc250 status
sudo bc250 verify
```

For continuous monitoring use `watch -n 1 sensors`; `bc250 status` provides the concise appliance view.

The RPM loads `nct6683` for conservative sensor visibility. It does not install
an experimental PWM driver. Status reports temperatures, power, fan readings
and exposed PWM controls; verification fails if conflicting driver families
are loaded.

Community setups sometimes use the out-of-tree
[`nct6687d`](https://github.com/Fred78290/nct6687d) driver for PWM control. It
is optional, kernel-specific and may require rebuilding after every kernel
update. Never load `nct6683` and `nct6687` together because they target the same
Super-I/O hardware.

Before replacing the default, keep an independent safe fan curve, record
temperatures, build for the exact running kernel and confirm both cooling and
sensor reporting before sustained inference. This workflow remains outside the
base package until tested on the target board.

Hardware reference: [ElektricM BC-250 sensors](https://elektricm.github.io/amd-bc250-docs/system/sensors/).

## Cyan Skillfish governor

### Commands

```bash
systemctl status cyan-skillfish-governor-smu.service
sudoedit /etc/cyan-skillfish-governor-smu/config.toml
sudo systemctl restart cyan-skillfish-governor-smu.service
journalctl -u cyan-skillfish-governor-smu.service -b
sudo bc250 verify
```

The RPM pins `filippor/cyan-skillfish-governor` v0.4.13 at commit
`aaed42535622aee1a93df8b22860c409539f67f8`. Fresh installations use a
350–1850 MHz range. The 2000 MHz / 960 mV point remains in the curve only for
deliberate operator testing. `%config(noreplace)` preserves local tuning on
upgrades.

The packaged usage policy is:

```text
fix-freq = false
method = "busy-flag"
temp-read = "sysfs"
```

Use `fix-freq = true` only when an eight-core configuration misreports
`current_gfxclk_frequency`. The `kernel` method requires a separately patched
compatible kernel; live CU routing does not provide it.

### 2026-08-31 governor revalidation

The appliance comparison found that normal `busy-flag` control stayed very close
to a fixed 1850-MHz run while still returning to low clocks between work. Fixed
1750 MHz reduced prefill by roughly five percent in the tested Gemma E2B/LFM2.5
workloads, so 1850 remains the normal package maximum rather than adopting 1750
as the default.

One important upstream-helper behavior was exposed on the earlier v0.4.12 stack:
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
board. `bc250 verify` warns if the observed active clock is above the configured
normal maximum, which helps catch a forgotten D-Bus/performance override.

Frequency and voltage remain the operator's responsibility. Validate every
change with representative inference, temperature monitoring, output checks and
GPU-reset logs. CU tools do not alter governor policy.

## Live CU routing

The package uses the pinned `bc250-cu-live-manager` runtime-routing method. It does **not**
ship or build a replacement AMDGPU module.

### Normal workflow

Configure and save the board-specific routing profile:

```bash
sudo bc250-cu-live-manager
```

Use the interactive table to select and save the highest CU-routing profile proven stable on this individual BC-250, then enable boot restore. A 40/40 profile is valid only on boards where it has been qualified; deliberately unselected `--` cells are allowed, while `D!` indicates an inconsistency.
Then verify the saved and live masks:

```bash
sudo bc250-40cu status
```

`bc250-40cu status` is a thin public verification command. Package diagnostics use the
same internal live-routing status helper. Live SPI-routed CUs are the operator-facing CU-capacity value;
the saved/live WGP mask match is the operational authority.

### Boot behavior

The live manager stores its selected row masks in:

```text
/etc/bc250-cu-live-manager.conf
```

and restores them through `bc250-cu-live-manager.service`. No initramfs or AMDGPU module
replacement is required by the package workflow.

### Diagnostics

For normal operation use only the two commands above. Broader appliance evidence remains
available through:

```bash
sudo bc250 verify
sudo bc250 support-bundle
```

The package does not automatically change CU routing during RPM installation or guided
setup.

### Upstream

The packaged runtime manager is pinned from
[WinnieLV/bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager).
