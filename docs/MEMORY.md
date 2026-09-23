# BC-250 memory profile

The BC-250 shares 16 GiB of GDDR6 between CPU and GPU, so model residency depends
on the kernel's TTM limits as well as on real free host memory and swap. The
reviewed fresh-machine profile is now intentionally small:

```text
ttm.pages_limit=4194304
ttm.page_pool_size=4194304
```

Apply/review:

```bash
bc250-memory-profile status
sudo bc250-memory-profile ensure      # idempotent; used by bc250-install
bc250-memory-profile recommend
sudo bc250-memory-profile apply-full  # confirmed interactive equivalent
sudo reboot
```

`ensure` owns the desired-state check: it removes `amdgpu.gttsize=...` and
`amdgpu.ppfeaturemask=...` overrides before applying the two TTM limits only when
needed. `bc250-install` delegates this decision to the helper instead of carrying a
second kernel-argument state machine. `apply-full` adds an operator confirmation to
the same reconciliation path.

## 2026-08-31 Fedora 44 revalidation

The previous package profile also forced `amdgpu.gttsize=14750` and
`amdgpu.ppfeaturemask=0xffffffff`. A reboot-by-reboot comparison on kernel
`7.1.10-200.fc44.x86_64`, Mesa 26.1.8, the modified 40-CU AMDGPU module and
Ollama 0.33.2 found:

- removing `amdgpu.gttsize` did not reduce the exposed GTT aperture or measurable
  Gemma E2B/LFM2.5 context performance;
- removing the explicit full `ppfeaturemask` likewise did not change the tested
  Vulkan/Ollama stability or throughput under the normal busy-flag governor;
- the driver reported `amdgpu.gttsize=-1` and selected its normal power-feature
  mask while the two 4,194,304-page TTM limits remained active;
- no tested configuration used swap or produced the known Vulkan device-loss,
  command-submission OOM or compute-ring failure signatures.

Current upstream Linux [AMDGPU module-parameter documentation](https://docs.kernel.org/gpu/amdgpu/module-parameters.html)
marks `amdgpu.gttsize` deprecated and says its default is the TTM-specified value.
The package therefore lets AMDGPU/TTM derive the aperture from TTM instead of
preserving an obsolete duplicate override. The explicit full power-feature mask is no longer a
fresh-install requirement; operator overclock/experimental power-control work
remains outside the appliance baseline.

### Kernel policy

The appliance follows the current Fedora-supported kernel rather than maintaining historical
release-number warning ranges. Hardware-sensitive checks remain state-based: the installer uses the
exact running kernel dynamically when preparing optional 40-CU module support, and verification checks
the running AMDGPU/module/build-tree relationship rather than comparing the kernel release to a stale list.
No newer BC-250 evidence justifies changing TTM sizing, `ppfeaturemask`, the governor or Mesa defaults.

The two TTM values describe a 16-GiB ceiling at 4-KiB pages. They do **not**
reserve 16 GiB at boot and do not mean a 16-GiB GGUF will fit: the OS, Ollama,
KV/cache and other services share the same physical memory.

IOMMU is not required by the qualified appliance baseline. Do not force `amd_iommu=on` on an unqualified BIOS configuration; BIOS-enabled SVM/IOMMU operation is a separate device-qualification choice. `nomodeset` is only for installation recovery and must not remain on the normal LLM boot. The package does not automatically add `mitigations=off`.

The separate `bc250-swap-profile` remains a pressure safety net; it is not a way
to make an oversized model GPU-resident. Watch `MemAvailable`, swap growth and
`ollama ps` during long-context tests.

## External BC-250 setup references

Community guidance remains useful, but kernel-specific recipes age quickly. The
package was cross-checked against the ElektricM kernel/quick-reference material
and current Linux AMDGPU parameter documentation. The package values above are
based on BC-250 device evidence rather than copying kernel-version-specific recipes
verbatim.
