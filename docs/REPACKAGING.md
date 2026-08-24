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
the upstream repository itself before changing a pin. RPM scriptlets must never
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
`cargo vendor --locked`. Cached source archives are not independently
authenticated by a second local lock file, so release builders should use a
controlled cache and inspect the source RPM.

## Release checklist

- Bump `VERSION`, spec `Version`, spec `Release` and the top spec changelog
  entry together.
- Review pinned revisions, licenses and source-RPM contents.
- Run `make validate` and build on Fedora 44.
- Inspect the binary payload and run `rpmlint`.
- Test clean installation, guided reboot/resume, models, upgrade and both
  removal paths.
- Confirm RPM scriptlets still do not enable CUs, replace AMDGPU, change memory
  or swap policy, alter governor tuning or reboot.
