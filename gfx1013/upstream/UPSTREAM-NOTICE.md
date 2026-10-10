# Vendored GFX1013 source identity

This package profile is based on DryhoppedIPA/bc250-gfx1013-fix release
`0.2.0-alpha`, pinned at commit
`d3e6dc062c34d2523db0abe5741d1f5b0dea00d9`.

The package intentionally carries only the compute-queue subset needed by the
BC-250 LLM appliance:

- kernel V33 patch 0001: MMIO PASID route;
- kernel V33 patch 0002: compute/GFXOFF guard;
- kernel V33 patch 0003: scoped PASID type-0 invalidation;
- Mesa/RADV patch 0001: compute queue exposure, GFX10.1 identity and ACE
  dispatch workaround.

Upstream Mesa mesh/task patches 0002/0003 are not part of package profile
v0.2.1-alpha. They are optional in the pinned root commit and current upstream
ships them disabled because they can hang the GPU. The package does not import
40-CU, FSR, mesh/task or overclock changes through this lifecycle.

Kernel-derived patches remain GPL-2.0-only. The Mesa patch and this upstream
project's installer/documentation code are MIT-licensed. See the upstream
repository for complete attribution and history.
