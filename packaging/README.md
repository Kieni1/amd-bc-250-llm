# RPM packaging

## Build

```bash
make validate
make rpm
```

Binary and source RPMs plus checksums are written together under `dist/`.
Install the `*.x86_64.rpm`; the `*.src.rpm` is rebuild input.

## Authoritative files

| File | Purpose |
|---|---|
| `bc250-llm-server.spec` | Fedora 44 RPM recipe and scriptlets |
| `install-manifest.tsv` | Payload paths, modes and ownership |
| `upstreams.toml` | Pinned third-party revisions and archive names |
| `bc250` | Multicall dispatcher and stable command aliases |
| `bc250-llm-server.sysusers` | Package-owned `ollama` user/group |
| `bc250-llm-server.tmpfiles` | Persistent directory declarations |
| `90-bc250-llm-server.preset` | Default service enablement |

Repository groups are `cmd/` for host commands and units, `config/` for shipped
configuration, `models/` for Modelfiles and model workflows, and `examples/`
for operator-adapted integrations. Only MTP retains a TOML model catalog.

`scripts/prepare-sources.py` stages the governor, offline Cargo vendor tree,
40-CU source and live-manager source from the reusable `sources/` cache. Each
cached archive has a local `.sha256` sidecar; reuse and `make sources-check`
verify the current bytes before they are copied into the RPM build tree.

## Policy boundaries

- RPM scriptlets are package integration only: no appliance provisioning, model
  downloads, kernel builds, firewall/SELinux policy changes or reboots.
- The repository bootstrap installs the selected RPM and hands off; `bc250-install`
  is the single owner of Fedora update/provisioning policy.
- The guided installer may prepare a default-off module for the running kernel;
  activation remains `sudo bc250-40cu enable`.
- Model weights are downloaded only after operator selection.
- Ordinary RPM removal preserves state; `bc250-reset` is the separately confirmed
  greenfield appliance reset (`bc250-uninstall` remains an alias).
- Pre-1.0 setup keeps no package-baseline/network-before-state database. Reset
  removes only declared appliance-owned state and never uses unbounded autoremove.
- Configuration that operators may change uses `%config(noreplace)` or lives
  outside RPM ownership.

The install manifest deliberately remains a small placement table. If it ever
needs logic beyond its existing entry types, move that logic into explicit spec
sections instead of creating a general packaging language.

See [`../docs/REPACKAGING.md`](../docs/REPACKAGING.md) for source refresh and
release checks.

CI runs the same Fedora 44 build on manual dispatch, push and pull request. Ruff
and ShellCheck are CI/build-environment tools only and are not runtime package
dependencies.
