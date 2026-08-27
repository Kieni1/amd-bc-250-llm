# RPM packaging

## Build

The normal package build is the Fedora 44 GitHub Actions workflow. It runs the
repository checks and publishes the binary RPM and SRPM together. Maintainers
with a matching Fedora build environment can reproduce that path locally with:

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
40-CU source and live-manager source from the reusable `sources/` cache.

## Policy boundaries

- RPM scriptlets must not replace AMDGPU, change CU routing, rebuild initramfs,
  alter memory/swap policy, change governor tuning or reboot.
- The guided installer may prepare a default-off module for the running kernel;
  activation remains `sudo bc250-40cu enable`.
- Model weights are downloaded only after operator selection.
- Ordinary RPM removal preserves state; `bc250-uninstall` is the separately
  confirmed full purge.
- Dependency cleanup is limited to packages recorded as newly added by the
  guided installer; never use unbounded `dnf autoremove`.
- Configuration that operators may change uses `%config(noreplace)` or lives
  outside RPM ownership. Ordinary RPM upgrades therefore remain non-destructive.
- A full guided-installer rerun is an explicit convergence operation: it backs up
  and reapplies the packaged copies of all four `%config(noreplace)` defaults,
  resets Open WebUI ConfigVars once, refreshes generated Ollama instance units and
  reconciles deployed models. Operator secrets/data and `models.d` are excluded.

The install manifest deliberately remains a small placement table. If it ever
needs logic beyond its existing entry types, move that logic into explicit spec
sections instead of creating a general packaging language.

See [`../docs/REPACKAGING.md`](../docs/REPACKAGING.md) for source refresh and
release checks.
