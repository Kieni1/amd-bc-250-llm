# Experimental GFX1013 compute queues

## Read-only checks

```bash
sudo bc250-verify
vulkaninfo --summary
vulkaninfo | grep -E 'queueFlags|QUEUE_COMPUTE_BIT'
modinfo -n amdgpu
modinfo -F vermagic amdgpu
cat /proc/cmdline
```

[`DryhoppedIPA/bc250-gfx1013-fix`](https://github.com/DryhoppedIPA/bc250-gfx1013-fix)
is an external experimental kernel plus Mesa/RADV patch stack for dedicated ACE
compute queues. This package only detects it; it does not download, install,
activate or remove it. The current external project reports dedicated-queue Vulkan
CTS coverage and substantial gaming gains, but those results still do not establish
an Ollama/llama.cpp inference benefit. The appliance therefore keeps this stack
operator-managed and detection-only.

The kernel and Mesa halves must be used together. Upstream warns that selecting
the patched Mesa on an unpatched kernel can hang the GPU. The detected layout
uses `/opt/bc250-gfx1013`, the `bc250.gfx1013_v33=1` boot marker and an
ABI-matched AMDGPU module in the running kernel's `updates/` path.

`bc250-verify` reports compute-only Vulkan queues and checks that a selected
custom ICD has both the patched boot marker and matching AMDGPU module. This is
a consistency check, not cryptographic provenance or Vulkan-conformance proof.

Rebuild the external kernel module, initramfs and boot entry after every kernel
update before selecting the custom Mesa again. The project can build its own
40-CU variant; do not run it and `bc250-40cu prepare` as two independent module
installers. Choose one workflow or maintain one deliberately merged patch set.
