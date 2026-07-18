# Fedora 44 kernel memory argument

This package recommends one explicit argument for the BC-250 LLM profile:

```text
ttm.pages_limit=4194304
```

Use the packaged helper:

```bash
sudo bc250-memory-profile recommend
sudo bc250-memory-profile apply-full
sudo reboot
sudo bc250-memory-profile status
```

It removes legacy `amdgpu.gttsize`, `ttm.page_pool_size` and
`amdgpu.ppfeaturemask` arguments before applying the TTM limit. The RPM itself
never changes boot entries or reboots the machine.

To return to kernel defaults:

```bash
sudo bc250-memory-profile remove
sudo reboot
```
