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
sudo bc250-memory-profile recommend
sudo bc250-memory-profile apply-full
sudo reboot
sudo bc250-memory-profile status
```

`apply-full` removes older package-managed `amdgpu.gttsize=...` and
`amdgpu.ppfeaturemask=...` overrides before applying the two TTM limits. The
helper still knows those legacy argument names so uninstall/migration cleanup is
complete.

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

### Fedora 44 kernel 7.1.12 note

Fedora 44 now ships `7.1.12-200.fc44`. Keep the measurements above attributed to
`7.1.10-200.fc44`: they have not been rerun on 7.1.12 yet. The relevant 7.1.11
AMDGPU stable fixes are in the devcoredump path (per-ring dump-buffer allocation
and safer reservation locking after a hung job), while 7.1.12 itself fixes a
network fragment/GSO panic path. None of those changes is evidence for altering
TTM sizing, `ppfeaturemask`, the governor or Mesa. The installer continues to use
the exact running kernel dynamically when preparing optional 40-CU support.

The two TTM values describe a 16-GiB ceiling at 4-KiB pages. They do **not**
reserve 16 GiB at boot and do not mean a 16-GiB GGUF will fit: the OS, Ollama,
KV/cache and other services share the same physical memory.

Do not enable `amd_iommu=on` on this board. `nomodeset` is only for installation
recovery and must not remain on the normal LLM boot. The installer/verify tooling
checks both hazards. The package also does not automatically add
`mitigations=off`.

The separate `bc250-swap-profile` remains a pressure safety net; it is not a way
to make an oversized model GPU-resident. Watch `MemAvailable`, swap growth and
`ollama ps` during long-context tests.

## External BC-250 setup references

Community guidance remains useful, but kernel-specific recipes age quickly. The
package was cross-checked against the ElektricM kernel/quick-reference material
and current Linux AMDGPU parameter documentation. The package values above are
based on the Fedora 44 revalidation rather than copying an older kernel command
line verbatim.
