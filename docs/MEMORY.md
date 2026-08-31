# BC-250 memory profile

The BC-250 shares 16 GiB of GDDR6 between CPU and GPU, so model residency depends
on the kernel's GTT/TTM limits as well as on free host memory and swap. The package
therefore treats the following as **required fresh-machine setup**, not legacy
compatibility:

```text
amdgpu.gttsize=14750
ttm.pages_limit=4194304
ttm.page_pool_size=4194304
amdgpu.ppfeaturemask=0xffffffff
```

Apply/review:

```bash
sudo bc250-memory-profile recommend
sudo bc250-memory-profile apply-full
sudo reboot
sudo bc250-memory-profile status
```

The community BC-250 documentation recommends `gttsize=14750` with a roughly
14.5-14.75 GiB usable ceiling and uses 3,959,290 TTM pages. Current upstream Linux marks `amdgpu.gttsize` as deprecated, so this setting
must be revisited if a future Fedora kernel stops honoring it; for the current BC-250
runtime it remains an intentional, verified compatibility parameter. This project retains
4,194,304 pages because that 16-GiB cap is the profile already characterized by
its benchmarks; allocations are still constrained by real free memory. The full
`ppfeaturemask` is retained for the governor/power-control stack.

Do not enable `amd_iommu=on` on this board. `nomodeset` is only for installation
recovery and must not remain on the normal LLM boot. The installer/verify tooling
checks both hazards. The package also does not automatically add `mitigations=off`.

The separate `bc250-swap-profile` remains a pressure safety net; it is not a way
to make an oversized model GPU-resident. Watch `MemAvailable`, swap growth and
`ollama ps` during long-context tests.

## External BC-250 setup reference

This profile was cross-checked against the community documentation. The most
relevant references are the [ElektricM BC-250 kernel guide](https://elektricm.github.io/amd-bc250-docs/linux/kernel/)
and [quick reference](https://elektricm.github.io/amd-bc250-docs/reference/quick-reference/).
Those pages are useful hardware guidance but are not package release pins; where
this project intentionally differs, the tested package value is documented above.
