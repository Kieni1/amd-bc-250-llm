# Fedora memory argument

```bash
sudo bc250-memory-profile recommend
sudo bc250-memory-profile apply-full
sudo reboot
sudo bc250-memory-profile status
```

The reviewed BC-250 LLM profile applies only:

```text
ttm.pages_limit=4194304
```

It removes legacy `amdgpu.gttsize`, `ttm.page_pool_size` and
`amdgpu.ppfeaturemask` arguments. The RPM itself never changes boot entries or
reboots.

Return to kernel defaults with:

```bash
sudo bc250-memory-profile remove
sudo reboot
```
