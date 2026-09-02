# Uninstall

## Keep persistent data

```bash
sudo dnf remove bc250-llm-server.x86_64
```

Ordinary RPM removal removes package files and units but retains models, Open
WebUI state, profiles, `%config(noreplace)` files and separately installed
Ollama. Use this path when reinstalling or upgrading later.

## Purge the complete appliance

```bash
sudo bc250-uninstall-info
sudo bc250-uninstall
```

The purge prints its exact scope and requires `PURGE-BC250-LLM`. `--yes` is
available only for deliberate unattended disposal.

It stops services and removes:

- main, task, embedding and agent Ollama stores and source GGUFs;
- Open WebUI accounts, chats, uploads, vector state and containers;
- Hugging Face caches, maintenance backups and installer records;
- memory, zram, disk-swap, swappiness and CU persistence created by the setup;
- official Ollama installed by the setup;
- the main RPM and packages recorded as newly added by the guided installer.

For every AMDGPU module with a matching BC-250 backup, the purge restores only
a backup verified not to contain the unlock marker, runs `depmod` and rebuilds
that kernel's initramfs. If no verified stock backup exists, it retains the
files, reports the problem and exits nonzero after the other bounded cleanup.

The purge also restores recorded firewalld HTTP and SELinux states. It never
runs unbounded `dnf autoremove` and does not delete unrelated operator TLS keys,
home-directory work or unidentified files.

Reboot after a full purge. Root-filesystem growth and Fedora system updates are
not reversible.
