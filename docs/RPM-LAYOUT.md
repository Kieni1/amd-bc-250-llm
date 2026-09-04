# RPM layout

The main package is `bc250-llm-server`. Inspect the exact installed payload
instead of relying on a static list:

```bash
rpm -qlv bc250-llm-server.x86_64
rpm -qc bc250-llm-server.x86_64
rpm -qd bc250-llm-server.x86_64
rpm -V bc250-llm-server.x86_64
bc250 --help
```

## Payload groups

| Prefix | Contents |
|---|---|
| `/usr/bin/bc250` and `/usr/bin/bc250-*` | Dispatcher and stable aliases |
| `/usr/libexec/bc250-llm-server/` | Host-side implementations |
| `/usr/share/bc250-llm-server/` | Models, examples, profiles and pinned CU inputs |
| `/usr/share/doc/bc250-llm-server/` | Operator and packaging documentation |
| `/etc/bc250-llm-server/` | Operator model drop-ins and MTP/maintenance policy |
| `/usr/lib/systemd/system/` | Services and timers |
| `/usr/share/containers/systemd/` | Open WebUI and Tika Quadlets |
| `/usr/share/bc250-llm-server/openwebui/` | Versioned additive Open WebUI model presets |

`packaging/install-manifest.tsv` is the authoritative source-to-payload map.
It drives installation and RPM ownership. Keep it limited to simple file,
configuration, directory, alias, generated-text and ghost entries.

## State outside RPM ownership

```text
/var/lib/bc250-llm-server/
/var/cache/bc250-llm-server/
/var/lib/ollama/
/var/lib/open-webui/
/var/backups/bc250-llm-server/
```

Services, tmpfiles and operator commands create content below these paths.
`bc250-revalidate` keeps final result tarballs below
`/var/lib/bc250-llm-server/revalidation/results/` and removes its transient worker
state after finalization. Ordinary RPM removal intentionally preserves persistent
state.

## Packaging boundaries

- CU helpers and pinned inputs belong to the main package, but RPM scriptlets
  never replace AMDGPU, change CU routing, rebuild initramfs or reboot.
- RPM `%post` does not provision the appliance. Memory, swap, Ollama, firewall,
  SELinux, Fedora update policy and service setup remain explicit `bc250-install`/operator actions.
- Model weights are never part of the RPM.
- The source RPM is rebuild input and provides no runtime commands.

See [`FILESTRUCTURE.md`](FILESTRUCTURE.md) for the operator-facing path map and
[`../packaging/README.md`](../packaging/README.md) for maintainer policy.

The RPM statically owns all four lane units (`ollama.service`, `ollama-task.service`, `ollama-embedding.service`, `ollama-agent.service`) under `/usr/lib/systemd/system/`. The pinned upstream Ollama installer supplies `/usr/local/bin/ollama`; `bc250-install-ollama` removes only the recognizable upstream-generated base unit and re-enables the RPM-owned main service. Task/embedding become required normal lanes after the primary reboot; agent remains static and exclusive.


Open WebUI uses a two-part Quadlet enablement contract. The RPM-owned base
`open-webui.container` has no `[Install]` section, so merely installing the RPM
cannot start the UI at the primary reboot. After normal Ollama topology and the
baseline task/Jina registrations are ready, `bc250-install` copies the packaged
`open-webui-enable.conf` to
`/etc/containers/systemd/open-webui.container.d/90-enable.conf`, reloads
systemd, and starts the service. Full package removal deletes that installer-owned
enablement drop-in.
