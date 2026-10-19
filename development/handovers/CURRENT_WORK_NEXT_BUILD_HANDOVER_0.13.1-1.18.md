# BC-250 0.13.1-1.18 — current corrective release handover

## Authority

This document is the current source-side handover for the 1.18 corrective build. The
1.17 clean Fedora 44 release gate and exact-device stock-install results remain valid
historical evidence for 1.17 only. They do not qualify 1.18.

## Why 1.18 exists

The first 1.17 exact-device GFX1013 `prepare` safely completed Fedora kernel `%prep`,
patched amdgpu compilation, Mesa preparation and private RADV compilation/staging, then
failed at `module-vermagic-and-abi-validation` because the produced module did not carry
a `srcversion`. Boot state, runtime services and stock authority were unchanged.

That exposed a release/device gate asymmetry: the clean 1.17 full release gate accepted
the exact-kernel amdgpu build/ABI layer, while device `prepare` imposed an additional
mandatory `srcversion` requirement.

## 1.18 corrective contract

- RPM release is `1.18`; runtime Ollama remains `0.40.4`.
- GFX1013 remains experimental, opt-in and default-off; profile remains `v0.2.5-alpha`.
- Patch/profile reference kernel is `7.2.9-200.fc44.x86_64`.
- Package release qualification kernel is explicitly `7.2.10-200.fc44.x86_64`.
- Device-local preparation always targets the currently running exact kernel.
- Release and device prepare now call the same module-identity validator.
- Exact vermagic, module SHA-256 and ABI evidence remain mandatory.
- `srcversion` is supplemental: if present it is recorded and later must match; absence
  alone is not a failure and is never synthesized or spoofed.
- Patched runtime attestation binds lifecycle state to exact staged BLS and initramfs
  SHA-256 values in addition to the prepared exact-kernel/module/ABI/provenance identity.
- Prepare failure evidence retains built/stock module SHA-256, `modinfo`, `readelf -n`
  and the running kernel `CONFIG_MODULE_SRCVERSION_ALL` state when available.
- Stock-module discovery queries `modinfo -k <exact-kernel> -n amdgpu` first.
- Preflight distinguishes genuine `BLOCKED` from `NOT CHECKED`; every counted blocker
  has exactly one remediation entry and the reported count is asserted internally.
- Clean successful `./build-local.sh --full` prints `Qualification: full release gate PASS`.
- Installer completion orders normal appliance status/verification and model management
  before optional workflows, with GFX1013 last and only the read-only `prepare --check`
  plus help advertised.
- RPM transaction authority remains one next action: `sudo bc250 install`.

## Optional build dependencies

Do not make the experimental GFX kernel/Mesa build toolchain hard runtime dependencies
of the normal appliance RPM. A future helper/meta-package for the complete tested GFX
build dependency set remains optional backlog, not a 1.18 acceptance requirement.

## Release boundary

The authoritative 1.18 RPM does not exist until a clean Fedora 44
`./build-local.sh --full` succeeds from clean source and produces the exact main RPM.
A Debian/static validation run is useful source evidence only and must not be described
as an RPM release gate PASS.

After a clean Fedora build:

1. preserve `result.json`, full log, Source0/spec hashes and RPM/SRPM SHA-256;
2. install that exact 1.18 RPM on the BC-250;
3. verify normal appliance health and Ollama 0.40.4;
4. run `sudo bc250 gfx1013 status --brief` and `sudo bc250 gfx1013 prepare --check`;
5. verify package qualification kernel `7.2.10-200.fc44.x86_64` is reported separately
   from patch/profile reference `7.2.9-200.fc44.x86_64`;
6. verify dependency/provider output and blocker accounting are truthful/read-only;
7. run `prepare` and confirm module identity accepts absent `srcversion` only under the
   supplemental policy while exact vermagic/SHA/ABI evidence remains mandatory;
8. preserve A1, then `stage-boot -> reboot patched -> status -> enable -> B ->
   disable/reset -> reboot stock -> A2`, preserving state/evidence at each boundary.

No GFX1013 promotion is valid until fresh 1.18 A1/B/A2 evidence completes.
