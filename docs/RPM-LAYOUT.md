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
Ordinary RPM removal intentionally preserves it.

## Packaging boundaries

- CU helpers and pinned inputs belong to the main package, but RPM scriptlets
  never replace AMDGPU, change CU routing, rebuild initramfs or reboot.
- Memory, swap, Ollama and maintenance profiles remain explicit operator or
  guided-installer actions.
- Model weights are never part of the RPM.
- The source RPM is rebuild input and provides no runtime commands.

See [`FILESTRUCTURE.md`](FILESTRUCTURE.md) for the operator-facing path map and
[`../packaging/README.md`](../packaging/README.md) for maintainer policy.

Dynamic model setup may create `ollama-task.service`, `ollama-embedding.service` and the boot-disabled `ollama-agent.service` under `/etc/systemd/system/`; these are operator/runtime state rather than RPM-owned unit payloads.
