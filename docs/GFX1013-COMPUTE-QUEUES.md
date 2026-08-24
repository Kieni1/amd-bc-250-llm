# Experimental GFX1013 compute queues

[`DryhoppedIPA/bc250-gfx1013-fix`](https://github.com/DryhoppedIPA/bc250-gfx1013-fix)
is an external experimental kernel plus Mesa/RADV patch stack for exposing the
BC-250's dedicated ACE compute queues. This RPM does not download, build,
install, activate or remove it. The reported gaming gains do not establish an
LLM-inference benefit.

The two halves are inseparable: the patched Mesa must never be selected on an
unpatched kernel because upstream warns that this combination can hang the GPU.
The external installer places Mesa below `/opt/bc250-gfx1013`, uses
`bc250.gfx1013_v33=1` as its patched-boot marker and installs its ABI-matched
AMDGPU module in the running kernel's `updates/` module path.

`sudo bc250-verify` reports whether Vulkan exposes a compute-only queue family.
When the optional tree exists, it distinguishes files that are merely installed
from a custom ICD actually selected by the verifier or Ollama. A selected custom
ICD without both the patched boot marker and a matching `updates/amdgpu.ko` is a
verification failure.

This is a layout and runtime-consistency check, not cryptographic proof of patch
provenance or Vulkan conformance. The external project's documented test target
is not this package's Fedora 44 appliance, so detection must not be read as a
compatibility endorsement.

Every kernel update requires the external AMDGPU module to be rebuilt and its
initramfs/boot entry regenerated before the custom Mesa ICD is selected again.
Boot stock and leave the custom ICD unselected until that matching rebuild is
complete.

The external project can build its own 40-CU variant. Do not run its installer
and this package's `bc250-40cu prepare`/`enable` as two independent module
replacement workflows: the later operation can replace the earlier module.
Choose one workflow or manually maintain one reviewed, merged patch set. The
existing stability and correctness warnings in [`CU-UNLOCK.md`](CU-UNLOCK.md)
still apply.

Useful read-only checks:

```bash
sudo bc250-verify
vulkaninfo --summary
vulkaninfo | grep -E 'queueFlags|QUEUE_COMPUTE_BIT'
modinfo -n amdgpu
modinfo -F vermagic amdgpu
cat /proc/cmdline
```
