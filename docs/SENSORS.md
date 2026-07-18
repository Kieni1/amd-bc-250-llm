# Sensors and optional fan control

The main RPM loads `nct6683` for conservative sensor visibility. It does not
install an experimental PWM fan-control driver.

Some community setups use an `nct6687` or `nct6687d` out-of-tree module to gain
PWM control. That driver is optional, kernel-specific and may need rebuilding
after every kernel update.

Never load `nct6683` and `nct6687` at the same time. They target the same
Super-I/O hardware and can conflict. Check with:

```bash
lsmod | grep -E '^nct6683|^nct6687'
sensors
sudo bc250-verify
```

Before replacing the default driver:

1. Keep a working fan curve in hardware or an independent fan controller.
2. Record current temperatures and fan behavior.
3. Disable the default `nct6683` module configuration.
4. Build the optional module for the exact running kernel.
5. Confirm fan control and temperature reporting before sustained loads.

This RPM intentionally leaves that process outside automatic installation.

## Reference

- https://elektricm.github.io/amd-bc250-docs/system/sensors/
