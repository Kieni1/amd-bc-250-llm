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
| `bc250` | Canonical multicall dispatcher for the public command surface |
| `bc250-llm-server.sysusers` | Package-owned users/groups |
| `bc250-llm-server.tmpfiles` | Persistent directory declarations |
| `90-bc250-llm-server.preset` | Default service enablement |

Repository groups are `cmd/` for host command implementations, `config/` for shipped
configuration and unit assets, `models/` for Modelfiles/model workflows, `quality-checks/` for source-only engineering real-device
candidate screens, `examples/` for operator-adapted integrations, and `development/`
for Git-only engineering memory. `development/` is deliberately absent from the
binary install manifest.

The install manifest deliberately remains a small placement table. If it ever needs
logic beyond its existing entry types, move that logic into explicit spec sections
instead of creating a general packaging language.

## RPM version and release naming

Use normal RPM `Version` / `Release` identity. For a new product version, start at `Release: 1`; maintenance/package revisions may use a simple numeric or dotted numeric release according to the active release line. Do not encode development labels, chat milestones or branch names in the installable NEVRA. The current clean-core candidate is `bc250-llm-server-0.14.1-1.9.fc44.x86_64`.

## Validation and build boundary

The primary release build runs through the Fedora 44 GitHub Actions workflow and its
`make release-gate`. Local Fedora execution through `scripts/ci-local.sh` reproduces the
same gate but is backup/debug evidence only; it does not silently become release authority.
`make validate` runs current guidance/scope checks plus the complete repository regression suite and can be run wherever its required tools are present. A successful source edit must not be reported as an RPM build unless the Fedora gate actually ran. GitHub runs Ruff and ShellCheck as blocking pre-build checks and configured `rpmlint` as a blocking post-build package check, so predictable source/package defects do not consume another authoritative RPM iteration. The broad repository suite remains additional advisory quality evidence. `rpmlint` uses `packaging/rpmlint.toml`, which filters only documented appliance policy choices and known false positives.

`release-contract.json` is the machine-readable core release contract. The release gate
first verifies source identity and cheap pipeline contracts, then freezes Source0 plus the
RPM spec and records `RPM-INPUTS.sha256`. The package build consumes those exact frozen bytes as an unprivileged builder. The release path first creates the frozen SRPM with `rpmbuild -bs`, then rebuilds that SRPM once in an isolated temporary topdir. RPM `%check` runs the package-critical module list from `release-contract.json` during that rebuild; the exact rebuilt binary/debug RPMs are copied to `dist/` and become the GitHub artifacts. Payload checks and configured blocking `rpmlint` run on those same binaries before closed manifests/evidence are emitted.

GitHub writes the installable `*.x86_64.rpm`, rebuild-input `*.src.rpm`, separate
`SHA256SUMS.binary` / `SHA256SUMS.source`, frozen-input `SHA256SUMS.inputs`, and
`release-evidence.json` under `dist/`. The evidence record captures the Git commit, GitHub
Actions run ID, workflow name/reference, Source0 SHA-256, spec SHA-256, release-contract
SHA-256, and binary/SRPM NEVRA+SHA-256. Push and pull-request builds are CI evidence;
for BC-250 acceptance, explicitly select the specific GitHub run whose artifacts are being
installed and retain its release-evidence record.

### Runtime dependency footprint

Keep dependency cleanup evidence-driven. The package requires `git-core` rather than Fedora's larger `git` meta-package because the appliance needs the Git CLI but not the documentation/meta dependency closure. The larger Mesa/Vulkan, `umr`, Poppler and Hugging Face closures remain intentional: they back active inference/verification, live CU routing, managed document preparation/retrieval and model downloads. If fresh-install footprint needs a larger reduction, treat that as an architectural/package-splitting project rather than deleting runtime requirements without feature qualification.

## External source cache

`packaging/upstreams.toml` is authoritative for upstream repositories, full commits,
URLs and archive names. `make validate` checks full commit formatting and alignment
with the spec source macros; maintainers still review the actual upstream source and
license before changing a pin.

`scripts/prepare-sources.py` stages the governor, offline Cargo vendor tree and live-manager source from the reusable `sources/` cache. The first prepared
HTTPS fetch records a local `.sha256` sidecar; reuse and `make sources-check` verify
current bytes before they are copied into the RPM build tree. Prepared archives and
checksum sidecars are normalized to mode `0644` so SRPM source permissions are stable. RPM scriptlets never
fetch third-party source.

For the carried live-manager patch, `scripts/check-upstream-patches.py` is part of both
`make sources` and `make sources-check`. It verifies that the notice revision matches
the pinned source, dry-runs and applies the patch against that exact cached archive,
and checks the resulting source semantics. This deliberately tests patch applicability
rather than only searching the patch text for expected strings.

Useful maintainer targets are:

```bash
make validate
make release-gate   # authoritative when executed by the selected GitHub Actions run
./scripts/ci-local.sh  # backup/reproduction of the same Fedora 44 gate
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
5. Refresh `sources/`, run `make sources-check`, and require carried patches to apply
   against the exact pinned input before the GitHub/Fedora build.
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
- The repository bootstrap installs the selected RPM and hands off; `bc250 install`
  owns Fedora update/provisioning policy.
- CU routing uses the pinned live manager; the package no longer builds or installs a replacement AMDGPU module.
- Model weights are downloaded only after operator selection.
- Ordinary RPM removal preserves state; `bc250 reset` is the separately confirmed
  greenfield appliance reset.
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
- Build through GitHub/Fedora and require frozen-input verification, frozen-SRPM creation, the single isolated SRPM rebuild with package-critical `%check`, RPM payload-contract checks and closed checksum manifests to pass. Require Ruff, ShellCheck and configured `rpmlint` to pass; review the broad full-suite advisory report separately. The rebuilt binaries from that one SRPM rebuild are the distributed artifacts.
- Record the selected GitHub Actions run and retain its `release-evidence.json`; a PR build is CI evidence until deliberately selected for device acceptance.
- On the BC-250 test clean install or upgrade as appropriate, guided reboot/resume,
  models, affected runtime features and both removal paths.
- Confirm scriptlets still do not enable CUs, replace AMDGPU, change memory/swap or
  governor policy, alter network policy, or reboot.
