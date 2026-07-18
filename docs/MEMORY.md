# Unified memory profile

The reviewed Fedora 44 profile raises TTM's allocation limit to the board's
full 16 GiB physical memory:

```text
ttm.pages_limit=4194304
```

At the normal 4 KiB page size, 4,194,304 pages equal 16 GiB. This is an
allocation ceiling, not a reservation made at boot. Host processes and GPU
allocations still compete for the same physical memory, so disk-backed swap is
recommended for recovery margin.

The older `amdgpu.gttsize`, `ttm.page_pool_size` and
`amdgpu.ppfeaturemask=0xffffffff` arguments are deliberately removed. The
feature mask produced no measurable improvement in testing, and the separate
GTT/page-pool limits only made the effective cap harder to understand.

## Apply or inspect

```bash
sudo bc250-memory-profile recommend
sudo bc250-memory-profile apply-full
sudo reboot
sudo bc250-memory-profile status
sudo bc250-verify
```

The apply command first removes current and legacy arguments from every kernel
entry, then adds only `ttm.pages_limit=4194304`. It never reboots automatically.

Equivalent manual commands:

```bash
sudo grubby --update-kernel=ALL \
  --remove-args="amdgpu.gttsize ttm.pages_limit ttm.page_pool_size amdgpu.ppfeaturemask"
sudo grubby --update-kernel=ALL --args="ttm.pages_limit=4194304"
sudo reboot
```

## Roll back

```bash
sudo bc250-memory-profile remove
sudo reboot
```

After reboot, check `/proc/cmdline`, free memory, swap activity and a
representative model workload. A successful boot alone does not prove workload
stability.
