# RPM packaging and release maintenance

This is maintainer documentation. **GitHub is the authoritative RPM/package build
path for this project.** Do not ask the appliance operator to build RPMs locally.
Developer environments may run the checks they actually provide; hardware/runtime
qualification belongs on the real BC-250.

## Authoritative files

| File | Purpose |
|---|---|
| `bc250-llm-server.spec` | Fedora 44 RPM recipe and scriptlets |
| `install-manifest.tsv` | Binary-payload paths, modes and ownership |
| `upstreams.toml` | Pinned third-party revisions and archive names |
| `bc250` | Multicall dispatcher and stable command aliases |
| `bc250-llm-server.sysusers` | Package-owned users/groups |
| `bc250-llm-server.tmpfiles` | Persistent directory declarations |
| `90-bc250-llm-server.preset` | Default service enablement |

Repository groups are `cmd/` for host commands and units, `config/` for shipped
configuration, `models/` for Modelfiles/workflows, `quality-checks/` for real-device
candidate screens, `examples/` for operator-adapted integrations, and `development/`
for Git-only engineering memory. `development/` is deliberately absent from the
binary install manifest.

The install manifest deliberately remains a small placement table. If it ever needs
logic beyond its existing entry types, move that logic into explicit spec sections
instead of creating a general packaging language.

## Validation and build boundary

The normal release build runs through GitHub. `make validate` is the deterministic
repository check and can be run wherever its required tools are present. The `make rpm`
target describes the Fedora/GitHub build step; a successful source edit must not be
reported as an RPM build unless that build actually ran. CI/build environments may
also provide Ruff, ShellCheck and rpmlint; none are runtime dependencies.

GitHub writes binary/source RPMs and checksums under `dist/`; the `*.x86_64.rpm` is
the installable package and the `*.src.rpm` is rebuild input.

## External source cache

`packaging/upstreams.toml` is authoritative for upstream repositories, full commits,
URLs and archive names. `make validate` checks full commit formatting and alignment
with the spec source macros; maintainers still review the actual upstream source and
license before changing a pin.

`scripts/prepare-sources.py` stages the governor, offline Cargo vendor tree, 40-CU
source and live-manager source from the reusable `sources/` cache. The first prepared
HTTPS fetch records a local `.sha256` sidecar; reuse and `make sources-check` verify
current bytes before they are copied into the RPM build tree. RPM scriptlets never
fetch third-party source.

Useful maintainer targets are:

```bash
make validate
make sources
make sources-check
make clean          # remove build output; retain source cache
make clean-sources  # remove cached external archives
make distclean      # remove both
```

## Update a pinned source

1. Review upstream code, history and license.
2. Change the full commit in `upstreams.toml`.
3. Align the source macro in `bc250-llm-server.spec`.
4. Update third-party notices and affected documentation.
5. Refresh `sources/` and let the GitHub/Fedora build validate the package.
6. Install the resulting binary RPM on the BC-250 and test the affected feature.

The governor vendor archive is generated from its `Cargo.lock` with
`cargo vendor --locked` and receives the same local checksum sidecar. Sidecars protect
a prepared build cache from later corruption/replacement; they do not claim GitHub's
generated archive bytes are a permanent global release checksum. Inspect the source
RPM for release builds so pinned inputs and notices can be reviewed from the shipped
rebuild artifact.

## Packaging policy boundaries

- RPM scriptlets are integration only: no appliance provisioning, model downloads,
  kernel builds, firewall/SELinux changes or reboots.
- The repository bootstrap installs the selected RPM and hands off; `bc250-install`
  owns Fedora update/provisioning policy.
- The guided installer may prepare a default-off module for the running kernel;
  activation remains `sudo bc250-40cu enable`.
- Model weights are downloaded only after operator selection.
- Ordinary RPM removal preserves state; `bc250-reset` is the separately confirmed
  greenfield appliance reset (`bc250-uninstall` remains an alias).
- Pre-1.0 setup keeps no package-baseline/network-before-state database. Reset removes
  only declared appliance-owned state and never uses unbounded autoremove.
- Operator-editable configuration uses `%config(noreplace)` or lives outside RPM
  ownership.

## Release checklist

- For an ordinary package revision keep `VERSION`/spec `Version` stable and increment
  spec `Release`; change `VERSION` only for a real package-version reason.
- Keep the top spec changelog entry aligned with the resulting Version-Release.
- Review pinned revisions, licenses, source-RPM contents and the binary payload.
- Run only checks available in the editing environment and report them exactly.
- Build through GitHub/Fedora, then inspect build/lint results and run `rpmlint` when available in that build environment.
- On the BC-250 test clean install or upgrade as appropriate, guided reboot/resume,
  models, affected runtime features and both removal paths.
- Confirm scriptlets still do not enable CUs, replace AMDGPU, change memory/swap or
  governor policy, alter network policy, or reboot.
