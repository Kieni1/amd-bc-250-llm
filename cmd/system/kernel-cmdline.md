# BC-250 kernel command line

The reviewed fresh-machine LLM profile is:

```text
ttm.pages_limit=4194304 ttm.page_pool_size=4194304
```

Apply it with `sudo bc250-memory-profile apply-full`; the helper uses `grubby`
for every installed kernel and never reboots automatically. The installer applies
this profile on green-field systems and pauses for the required reboot.

The package deliberately no longer adds `amdgpu.gttsize=14750` or
`amdgpu.ppfeaturemask=0xffffffff`. On Fedora 44 kernel 7.1.10, a controlled
revalidation showed the TTM-only profile preserved the intended large GTT
aperture and the tested Ollama/Vulkan performance. `amdgpu.gttsize` is also
deprecated upstream. Applying the package profile removes those older overrides
so upgrades converge on one reviewed state.

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
