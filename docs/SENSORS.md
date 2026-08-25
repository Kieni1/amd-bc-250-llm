# Sensors and fan control

## Check the active hardware interface

```bash
lsmod | grep -E '^nct6683|^nct6687'
sensors
sudo bc250-status
sudo bc250-verify
bc250-check-temp --once
```

For continuous monitoring:

```bash
bc250-check-temp
```

`bc250-check-temp` refreshes the selected temperatures/fans/power every second by
default; `--once` prints one snapshot.

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
