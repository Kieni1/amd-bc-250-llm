# Experimental 40-CU tools

The main RPM installs the pinned Fedora helper and patch from
`fduraibi/bc250-40cu-unlock`, commit
`6c3969ddee40e894297869e6ca30537f274619cb`. The project declares the source
GPL-2.0; its original notices are retained. Installation does not compile or
replace `amdgpu`, change a modprobe option, run `dracut`, or reboot.

The separately downloadable live manager is pinned to WinnieLV commit
`8eb45f07810af738f3e4945ea0cc29d399e378a6` and a reviewed SHA-256. It is not
redistributed because its repository has no attached license.

## Risks

Harvested compute units may be defective. Possible failures include GPU resets,
wrong results, artifacts, boot failures, excess power and overheating. Keep a
second bootable kernel and local console access.

## Pinned live manager

```bash
sudo bc250-install-cu-manager
sudo bc250-40cu live-status
sudo bc250-40cu live-full
sudo bc250-40cu health-test MODEL_NAME
sudo bc250-40cu live-stock
```

`live-full` changes routing without saving boot persistence. Use the manager's
persistence feature only after testing.

## Replacement-module path

```bash
sudo dnf install "kernel-devel-$(uname -r)"
sudo bc250-40cu build
sudo bc250-40cu status
sudo bc250-40cu enable
```

The enable command requires the explicit `ENABLE-40CU` confirmation and then
delegates to upstream, which may replace the module and reboot. Follow the
upstream output for disable/restore operations after kernel updates.

## Governor policy

The RPM ships a 350-2000 MHz range with a 2000 MHz / 960 mV point. The CU tools
do not impose clock safeguards: choosing and validating clock and voltage values
is entirely the operator's responsibility.

Upstreams:

- <https://github.com/fduraibi/bc250-40cu-unlock>
- <https://github.com/WinnieLV/bc250-cu-live-manager>
