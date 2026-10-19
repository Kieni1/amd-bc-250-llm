# BC-250 0.13.1-2.0 — current corrective release handover

## Authority

1.18 is accepted build and partial exact-device evidence. The clean Fedora 44 full gate passed on
`7.2.10-200.fc44.x86_64`; stock install/verify passed; `gfx1013 prepare --check` and `prepare` passed,
including the revised shared module-attestation contract with `srcversion=none`. No patched boot occurred.

2.0 exists because the first 1.18 `stage-boot` reached dracut and failed deterministically: the private
module tree was staged as `kmod/<kernel>/`, while current dracut requires the kernel module directory
to have a literal `lib/modules/` ancestor. Stock boot/runtime were unchanged and prepared artifacts were retained.

## 2.0 corrective contract

- RPM release is `2.0`; Ollama remains `0.40.4`; GFX1013 profile remains `v0.2.5-alpha`.
- Build the isolated stage-boot module tree as `kmod/lib/modules/<exact-running-kernel>/`.
- Keep `dracut --kmoddir` validation enabled; do not bypass it with `DRACUT_KMODDIR_OVERRIDE=1`.
- Never replace the authoritative stock amdgpu or stock initramfs while creating the patched one-shot boot.
- Preserve stage failure cleanup: prepared build retained, partial BLS/initramfs removed, boot selection restored, runtime/services unchanged.
- Keep the 1.18 attestation contract: exact vermagic, module SHA-256 and ABI evidence mandatory; `srcversion` supplemental.
- Keep package qualification kernel, patch/profile reference kernel and running/prepare target as distinct identities.
- RPM upgrade transaction has one authoritative next action after completion: `sudo bc250 install`; package-upgrade GFX rollback must not advertise unrelated GFX next actions.
- `sudo bc250 health` is the user-facing read-only health command; `bc250 doctor` remains a compatibility alias.
- Experimental GFX lifecycle faults are reported explicitly without pretending the normal core appliance is itself broken; status must surface action-required GFX state rather than printing unconditional HEALTHY.
- `sudo bc250 model install` is the normal combined-catalog interactive model workflow; advanced `apply` remains supported.
- Installer completion keeps the fuller orientation block for technical installers, with status/health/verify and model management before optional/experimental workflows.
- Documentation start point is `/usr/share/doc/bc250-llm-server/docs/OPERATIONS.md`.

## Development/testing policy

This is pre-1.0 greenfield development. GFX1013/kernel integration is the active lane. Unrelated appliance
areas are frozen or boundary-active. Routine main-chat validation is changed-area depth plus small crossed-boundary
checks, not the entire suite every iteration. A full deterministic suite is a milestone/escalation gate; the clean
Fedora `./build-local.sh --full` is still mandatory for every RPM candidate sent to the device.

## Device boundary

After a clean 2.0 Fedora full build and normal stock acceptance:

1. run `sudo bc250 gfx1013 status --brief`;
2. run `sudo bc250 gfx1013 prepare --check`;
3. prepare exact-device artifacts again if package identity requires it;
4. run `sudo bc250 gfx1013 stage-boot`;
5. if staging passes, preserve state/evidence before rebooting patched;
6. continue patched status -> enable -> B -> disable/reset -> stock reboot -> A2.

Do not promote GFX1013 until the complete fresh 2.0 staged-boot/B/A2 lifecycle is accepted.
