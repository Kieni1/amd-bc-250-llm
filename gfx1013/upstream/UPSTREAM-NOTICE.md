# Vendored GFX1013 source identity

This package profile is based on DryhoppedIPA/bc250-gfx1013-fix release
`0.2.0-alpha`, pinned at commit
`d3e6dc062c34d2523db0abe5741d1f5b0dea00d9`.

Package profile `v0.2.4-alpha` intentionally carries only the compute-queue
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
this profile deliberately drops that stale patch hunk. The exact Fedora
`%prep` tree is the patch/applicability and private-RADV source authority.

The private Mesa build is deliberately headless and compute-only. It builds
only the AMD Vulkan driver with no Gallium, X11, Wayland, EGL, GBM, OpenGL,
OpenGL ES, Mesa Vulkan layers, Mesa tools, LLVM or video-codec frontends. Meson
subproject downloads are disabled. The deployed private prefix is reduced to
`lib64/libvulkan_radeon.so` plus its architecture-specific Vulkan ICD JSON, and
the RADV ELF is rejected if it directly links X11/Wayland/related WSI client
libraries or carries RPATH/RUNPATH. The private ICD is activated only for the
package Ollama service after exact-device verification; system Mesa remains the
stock/default path.

Upstream Mesa mesh/task patches are not part of this package profile. They are
optional in the pinned root commit and are excluded because they expand the
qualification boundary and have had GPU-hang risk. The package does not import
40-CU, FSR, mesh/task, fan, undervolt or overclock changes through this
lifecycle.

For the kernel side, the package verifies the exact Fedora kernel SRPM identity,
runs that SRPM's `%prep`, locates exactly one prepared source tree containing
every AMDGPU file touched by the BC-250 V33 patches, fingerprints those target
files, then adapts only recognized in-tree AMD trace include paths, applies and
builds the package patches from that same prepared tree. Any unresolved relative
AMD `TRACE_INCLUDE_PATH` fails closed. The Fedora release gate performs this same
external-module build against an installed Fedora `kernel-devel` tree and verifies
vermagic plus ABI compatibility before RPM publication. The patched initramfs is
generated from an isolated kmod tree; the authoritative stock amdgpu path is never
replaced by `prepare`.

Kernel-derived patches remain GPL-2.0-only. The Mesa patch and this upstream
project's installer/documentation code are MIT-licensed. See the upstream
repository for complete attribution and history.
