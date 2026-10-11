# Vendored GFX1013 source identity

This package profile is based on DryhoppedIPA/bc250-gfx1013-fix release
`0.2.0-alpha`, pinned at commit
`d3e6dc062c34d2523db0abe5741d1f5b0dea00d9`.

Package profile `v0.2.2-alpha` intentionally carries only the compute-queue
subset needed by the BC-250 LLM appliance:

- kernel V33 patch 0001: MMIO PASID route;
- kernel V33 patch 0002: compute/GFXOFF guard;
- kernel V33 patch 0003: scoped PASID type-0 invalidation;
- private Mesa/RADV patch 0001: expose the repaired GFX1013 compute queue and
  apply the required async-compute threadgroup workaround.

The private RADV baseline is the exact Fedora 44 Mesa source package
`mesa-26.2.4-1.fc44.src.rpm`, whose upstream Source0 is
`mesa-26.2.4.tar.xz` with SHA-256
`bce5f7fbebb934373b86c999a064d52fb5065878dc57f287f95346648ec832e9`.
Mesa 26.2.1 already upstreamed the GFX1013 GFX10.1 IP-version correction, so
profile v0.2.2-alpha deliberately drops that stale patch hunk.  The Fedora
`%prep` tree is the patch/applicability authority for the private RADV build.

Upstream Mesa mesh/task patches are not part of this package profile. They are
optional in the pinned root commit and are excluded because they expand the
qualification boundary and have had GPU-hang risk. The package does not import
40-CU, FSR, mesh/task, fan, undervolt or overclock changes through this
lifecycle.

For the kernel side, the package verifies the exact Fedora kernel SRPM identity
and records a target-equivalence manifest for every AMDGPU file touched by the
BC-250 V33 patches. If Fedora downstream SRPM material touches any target, this
profile fails closed instead of silently treating pristine Source0 as Fedora's
prepared source. The patched initramfs is generated from an isolated kmod tree;
the authoritative stock amdgpu path is never replaced by `prepare`.

Kernel-derived patches remain GPL-2.0-only. The Mesa patch and this upstream
project's installer/documentation code are MIT-licensed. See the upstream
repository for complete attribution and history.
