# BC-250 kernel command line

The reviewed fresh-machine LLM profile is:

```text
ttm.pages_limit=4194304 ttm.page_pool_size=4194304
```

Apply it with `sudo bc250-memory-profile apply-full`; the helper uses `grubby`
for every installed kernel and never reboots automatically. The installer applies
this profile on green-field systems and pauses for the required reboot.

The package deliberately no longer adds `amdgpu.gttsize=14750` or
`amdgpu.ppfeaturemask=0xffffffff`. Controlled BC-250 evidence showed the TTM-only
profile preserved the intended large GTT aperture and tested Ollama/Vulkan behavior.
`amdgpu.gttsize` is also deprecated upstream. Applying the package profile removes
those older overrides so upgrades converge on one reviewed state.

BC-250 safety checks:

- IOMMU is not required by the qualified LLM baseline. Do not force `amd_iommu=on` on an unqualified BIOS configuration; a BIOS-enabled SVM/IOMMU setup must be qualified separately;
- `nomodeset` is installation-only and must be removed once Mesa/AMDGPU is ready;
- follow the current supported Fedora kernel; the package no longer carries historical kernel-version warning ranges;
- the community recommends a 512 MiB dynamic UMA framebuffer; this package does
  not rewrite BIOS settings;
- the gaming-oriented `mitigations=off` suggestion is intentionally not applied
  by this office/RAG appliance.

Always verify after reboot with `bc250-memory-profile status`,
`sudo bc250-verify`, and a representative model load.

Community cross-check: [ElektricM BC-250 kernel guide](https://elektricm.github.io/amd-bc250-docs/linux/kernel/)
and [quick reference](https://elektricm.github.io/amd-bc250-docs/reference/quick-reference/).
