# Uninstall

There are two intentionally different removal paths.

## Full appliance purge

Run the packaged purge command when the machine should no longer contain the
BC-250 LLM setup:

```bash
sudo bc250-uninstall
```

The command prints its destructive scope and requires the exact phrase
`PURGE-BC250-LLM`. For unattended disposal, use
`sudo bc250-uninstall --yes`.

The purge:

- stops the main, task and agent Ollama instances, Open WebUI, Tika, governor,
  maintenance, Wake-on-LAN and CU live-manager services;
- removes the Open WebUI and Tika containers, their dedicated Podman network
  and their pinned images when nothing else uses those images;
- removes all GGUF files, rendered Modelfiles, Ollama stores, Hugging Face
  cache, Open WebUI accounts/uploads/settings, maintenance backups and the
  installer transcript;
- removes the disk-swap file and fstab block, zram override and current/legacy
  BC-250 kernel memory arguments;
- removes the CU live-manager boot service and saved table;
- finds every AMDGPU module with a `*.bc250-backup-*` sibling, restores only a
  backup verified not to contain `bc250_cc_write_mode`, then runs `depmod` and
  rebuilds that kernel's initramfs;
- removes the main RPM, setup-owned configuration, generated systemd units,
  official Ollama installed by this setup, and the setup-created `ollama`
  account;
- restores the firewalld HTTP rule and SELinux network boolean to the state
  recorded before guided installation;
- removes RPMs recorded as absent before the guided installer added them.

Normal DNF removal cleans requirements that are no longer needed. The package
record additionally prevents the purge from guessing which direct setup
additions are disposable. On an installation upgraded from a release that did
not write `/var/lib/bc250-llm-server/install/packages-added.txt`, that recorded
step is simply empty. The purge never runs an unbounded `dnf autoremove`.

The purge does not remove unidentified operator files such as arbitrary TLS
private keys or coding output in user home directories. Review those separately
if they were added while operating the appliance.

Reboot after a successful purge. The live kernel and zram device cannot return
to stock state until reboot. Root-filesystem growth and ordinary Fedora system
upgrades are not reversible and are not rolled back.

If the CU helper finds a patched module but cannot verify a stock backup, it
retains the backups, reports a warning and exits nonzero after completing the
remaining bounded cleanup. Restore that kernel from its Fedora package before
rebooting it.

## RPM-only removal

Use ordinary DNF removal when package binaries and units should go away but
models, Open WebUI state, profiles and separately installed Ollama should be
retained:

```bash
sudo dnf remove bc250-llm-server.x86_64
```

This standard RPM path remains intentionally non-destructive. It preserves
`%config(noreplace)` files and persistent application data so the package can
be reinstalled or upgraded without data loss.
