# Unified memory and swap

## Commands

```bash
sudo bc250-memory-profile recommend
sudo bc250-memory-profile apply-full
sudo reboot
sudo bc250-memory-profile status
sudo bc250-swap-profile status
sudo bc250-status
sudo bc250-verify
```

The reviewed profile applies:

```text
ttm.pages_limit=4194304
```

At a 4 KiB page size, this is a 16 GiB allocation ceiling. It is not a boot-time
reservation: CPU processes and GPU allocations still share the board's physical
memory. The helper removes legacy `amdgpu.gttsize`, `ttm.page_pool_size` and
`amdgpu.ppfeaturemask` arguments before applying the reviewed limit. It never
reboots automatically.

Return to kernel defaults with:

```bash
sudo bc250-memory-profile remove
sudo reboot
```

## Swap

The reviewed swap profile uses 2 GiB zram plus a 16 GiB disk swap safety margin:

```bash
sudo bc250-swap-profile apply
sudo bc250-swap-profile status
```

Override sizes with `ZRAM_MIB` and `SWAP_GIB`. `SWAPPINESS` is optional:

```bash
sudo SWAPPINESS=100 bc250-swap-profile apply
```

If unset, Fedora's current swappiness is preserved. Profile removal restores
the value recorded before the first explicit override:

```bash
sudo bc250-swap-profile remove
```

`bc250-status` reports RAM, memory PSI, zram, disk swap and current swappiness
together. After any change, also check GPU residency and a representative long
model run. A successful boot alone is not a stability test.
