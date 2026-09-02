# Experimental CU tools

## Commands

```bash
# Inspect kernel enumeration and live routing
sudo bc250-cu-status
sudo bc250-40cu status
sudo bc250-40cu verify

# Activate the prepared replacement module and reboot
sudo bc250-40cu enable

# Disable additional CUs but keep the prepared module
sudo bc250-40cu disable

# Restore a verified Fedora module backup
sudo bc250-40cu restore

# Interactive live routing for boards with fewer than 40 stable CUs
sudo bc250-cu-live-manager menu
sudo bc250-cu-live-manager status

# Direct live-routing helpers
sudo bc250-40cu live-status
sudo bc250-40cu live-full
sudo bc250-40cu live-stock
sudo bc250-40cu mask WGP_ID [WGP_ID ...]
sudo bc250-40cu unmask WGP_ID [WGP_ID ...]
sudo bc250-40cu health-test [OLLAMA_MODEL]

# After booting a new Fedora kernel
sudo bc250-40cu prepare
sudo bc250-40cu enable
```

The guided installer compiles and verifies the replacement AMDGPU module for
the running kernel, embeds it in that kernel's initramfs and stops with the
unlock disabled. After installation run `sudo bc250-40cu` for the guided
workflow. `bc250-cu-status` reports when preparation belongs to an older kernel.
`bc250-40cu enable` is the normal activation step; it requires `ENABLE-40CU`
and reboots.

## Choose the stable CU count

BC-250 boards contain harvested GPU hardware, so not every board has 40 usable
CUs. The operator must determine the stable amount. Start by checking 40 CUs,
then use the interactive live manager to disable unstable WGP pairs. One WGP is
two CUs, so masking one pair gives 38 CUs and two pairs give 36 CUs. Use the
WGP IDs reported on the actual board, not IDs copied from another system.

Test representative inference output, Vulkan initialization, temperature and
kernel logs—not only reported CU count or speed. Use the live manager's save
and service-install workflow only after the routing table is stable, then
confirm it after reboot with `bc250-cu-live-manager status`.

The replacement module and live WGP routing solve different parts of the
workflow. A live 40/40 table alone does not prove that the patched module is
loaded or that all CUs produce correct results.

## Kernel updates

AMDGPU modules are tied to the exact kernel ABI. After every Fedora kernel
update, boot the new kernel, prepare it again, reapply the intended CU mode and
verify the running module:

```bash
sudo bc250-40cu prepare
sudo bc250-40cu enable
sudo bc250-40cu verify
sudo bc250-verify
```

`status` distinguishes the module installed on disk, the copy in the initramfs
and the module currently loaded. A patched file on disk is not proof that it is
running. Preparation is also blocked when enforced module-signature policy
cannot load the unsigned replacement.

## Risks and recovery

Unstable harvested CUs can cause wrong output, GPU resets, hangs, boot failure
or excess heat. Keep local console access and another bootable kernel while
testing. The CU tools do not alter governor frequency or voltage policy.

Use `bc250-40cu disable` to return to disabled CU mode while retaining the
prepared module. Use `bc250-40cu restore` to restore a verified stock Fedora
module backup. Do not combine two independent module installers.

## External projects

The package pins and integrates:

- [fduraibi/bc250-40cu-unlock](https://github.com/fduraibi/bc250-40cu-unlock),
  based on [duggasco/bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock),
  for the replacement-module workflow; and
- [WinnieLV/bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager)
  for live WGP routing.

The 2026-08-31 upstream review confirms that `fduraibi/bc250-40cu-unlock` is a
fork of the active duggasco research tree and that both trees expose Fedora-oriented
helpers. The current duggasco tree also publishes LLM-prefill evidence for the
40-CU path. This RPM still keeps its reviewed fduraibi commit because the package
does not simply run either upstream helper: `bc250-40cu` wraps the pinned patch in
its own running-kernel build, verified-stock-backup, restore and qualification
workflow. Change the source pin only after a source-level delta audit shows that a
newer tree preserves those assumptions; recency alone is not a migration reason.

The external [GFX1013 compute-queue stack](GFX1013-COMPUTE-QUEUES.md) also
replaces AMDGPU. Choose one reviewed module workflow or maintain a deliberately
merged patch set; do not layer the two installers independently.
