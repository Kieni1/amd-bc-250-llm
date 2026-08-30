# Repackaging and source refresh

## Build commands

```bash
make validate
make sources
make sources-check
make rpm
```

Binary and source RPMs plus `SHA256SUMS` are written to `dist/`. `sources/`
is the reusable cache for four external inputs: governor source, its Cargo
vendor tree, 40-CU source and live-manager source.

```bash
make clean          # remove build output; retain source cache
make clean-sources  # remove cached external archives
make distclean      # remove both
```

Authoritative upstream repositories, commits, URLs and archive names are in
`packaging/upstreams.toml`. `make validate` checks full commit formatting and
that each pinned commit is referenced by the RPM spec; maintainers still review
the upstream repository itself before changing a pin. The first HTTPS fetch of a
pinned commit records a local `sources/ARCHIVE.sha256`; cached upstream and Cargo
vendor archives are reused only after that sidecar verifies. RPM scriptlets never
fetch third-party code.

## Update a pinned source

1. Review upstream code, history and license.
2. Change the full commit in `packaging/upstreams.toml`.
3. Align the source macro in `packaging/bc250-llm-server.spec`.
4. Update third-party notices and affected documentation.
5. Refresh and build:

   ```bash
   make clean-sources
   make sources
   make rpm
   ```

6. Install the `dist/*.x86_64.rpm` on Fedora 44 and test the affected feature.

The governor vendor archive is generated from its `Cargo.lock` with
`cargo vendor --locked` and receives the same local checksum sidecar. The
sidecars protect a prepared build cache against later corruption/replacement;
they do not claim that GitHub's generated tarball bytes are a permanent global
release checksum. Inspect the source RPM for release builds.

## Release checklist

- For a feature version bump, update `VERSION` and spec `Version`; for every
  build bump spec `Release`. Keep the top spec changelog entry aligned with the
  resulting Version-Release.
- Review pinned revisions, licenses and source-RPM contents.
- Run `make validate` and build on Fedora 44.
- Inspect the binary payload and run `rpmlint`.
- Test clean installation, guided reboot/resume, models, upgrade and both
  removal paths.
- Confirm RPM scriptlets still do not enable CUs, replace AMDGPU, change memory
  or swap policy, alter governor tuning or reboot.
