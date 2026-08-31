# BC-250 kernel command line

The reviewed fresh-machine LLM profile is:

```text
amdgpu.gttsize=14750 ttm.pages_limit=4194304 ttm.page_pool_size=4194304 amdgpu.ppfeaturemask=0xffffffff
```

Apply it with `sudo bc250-memory-profile apply-full`; the helper uses `grubby`
for every installed kernel and never reboots automatically. The installer applies
this profile on green-field systems and pauses for the required reboot.

`amdgpu.gttsize=14750` follows the BC-250 community's large-memory guidance. Current upstream Linux marks the `amdgpu.gttsize` module parameter as deprecated,
so it should be revisited when Fedora kernels stop honoring it; it remains explicit
here because the BC-250 profile still depends on it and is tested with it.
This package keeps its measured 4,194,304-page TTM ceiling/pool (16 GiB at 4 KiB
pages) rather than the community guide's slightly smaller 3,959,290-page value.
`amdgpu.ppfeaturemask=0xffffffff` keeps the power/governor controls available.

BC-250 safety checks:

- keep BIOS IOMMU disabled and do **not** add `amd_iommu=on`;
- `nomodeset` is installation-only and must be removed once Mesa/AMDGPU is ready;
- avoid the community-documented kernel regression ranges 6.15.0-6.15.6 and
  6.17.8-6.17.10;
- the community recommends a 512 MiB dynamic UMA framebuffer; this package does
  not rewrite BIOS settings;
- the gaming-oriented `mitigations=off` suggestion is intentionally not applied
  by this office/RAG appliance.

Always verify after reboot with `sudo bc250-memory-profile status`,
`sudo bc250-verify`, and a representative model load.

Community cross-check: [ElektricM BC-250 kernel guide](https://elektricm.github.io/amd-bc250-docs/linux/kernel/)
and [quick reference](https://elektricm.github.io/amd-bc250-docs/reference/quick-reference/).
