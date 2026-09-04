# Reset and package removal

Before 1.0 this is a greenfield appliance. The package does not keep a historical
record of which Fedora packages, firewall rules or SELinux settings existed before
installation and does not attempt to reconstruct an arbitrary previous host.

## Remove only the RPM

```bash
sudo dnf remove bc250-llm-server.x86_64
```

Ordinary RPM removal removes package-owned files and units while retaining
persistent appliance data, `%config(noreplace)` files and the separately installed
Ollama binary. Use this when replacing/reinstalling the RPM without discarding the
appliance state.

## Reset the dedicated appliance

```bash
sudo bc250-reset-info
sudo bc250-reset
```

`bc250-uninstall` and `bc250-uninstall-info` remain compatibility aliases. Reset
requires `PURGE-BC250-LLM`; `--yes` is for deliberate unattended disposal.

Reset stops the appliance and removes BC-250-owned runtime state: model stores and
source GGUFs, Open WebUI data/containers, caches/backups, the package-managed
memory/swap profiles, 40-CU persistence, the appliance HTTP firewalld rule and
`httpd_can_network_connect`, the separately installed Ollama binary, and the BC-250
RPM. Operator documents under `/srv/bc250-documents` are preserved.

For each modified AMDGPU module with a BC-250 backup, reset restores only a backup
verified not to contain the unlock marker, runs `depmod` and rebuilds that kernel's
initramfs. Missing/unverifiable stock backups are reported and retained rather than
guessed away.

Reset intentionally does **not** roll back Fedora upgrades or filesystem growth and
does not run unbounded dependency removal. Reboot afterward to load stock GPU,
memory and zram state.
