# Repackaging and source refresh

The RPM uses four external inputs: the pinned governor source, its offline Cargo
vendor tree, the 40-CU helper source and the CU live-manager source. The
authoritative commits, URLs and archive names are in
`packaging/upstreams.toml`. Normal builds do not maintain a second set of
per-download checksums.

## Normal build

```bash
make sources          # fetch only missing inputs
make sources-check    # offline cache check
make rpm
```

`sources/` is reusable. `make clean` removes `build/`, `dist/` and `rpmbuild/`
but keeps the cache. Use `make clean-sources` only when the inputs must be
fetched again; `make distclean` removes both build output and cached sources.

The resulting source RPM contains the exact external archives used for that
build. `dist/SHA256SUMS` covers finished source and binary RPM artifacts. This
is simpler for local pre-1.0 builds, but it does not independently authenticate
a cached upstream archive. Build releases from a controlled cache and review
the source RPM contents. A future release service can add a Fedora lookaside or
equivalent verified source store without putting that bookkeeping back into the
local build command.

Do not fetch third-party code from RPM scriptlets or `%build`.

## Change a pinned revision

1. Review the upstream code, license and history.
2. Update its full commit in `packaging/upstreams.toml`.
3. Update the corresponding macro in `packaging/bc250-llm-server.spec` so the
   `Source` filename stays aligned.
4. If the governor changed, its vendor archive is recreated automatically from
   `Cargo.lock` by `cargo vendor --locked`.
5. Update `licenses/THIRD_PARTY_NOTICES.md` and relevant documentation when
   upstream ownership or licensing changed.
6. Refresh and build:

   ```bash
   make clean-sources
   make sources
   make rpm
   ```

7. Install and test `dist/RPMS/*.x86_64.rpm`. Keep
   `dist/SRPMS/*.src.rpm` only as rebuild input.
8. Test clean installation, upgrade, removal and recovery on Fedora 44.

## Release checklist

- Bump `VERSION` and spec `Version` together and add a matching top
  `Version-Release` changelog entry.
- Review pinned commits, the cached source inputs and third-party licenses.
- Confirm the RPM owns the governor, 40-CU and live-manager payloads.
- Confirm no RPM scriptlet changes CU routing, a kernel module, memory/swap
  policy or governor clocks.
- Test the three Ollama instances and model installation/cleanup paths.
- Test Open WebUI on empty and upgraded persistent state.
- Test backup/restore with SELinux enforcing.
- Run `rpmlint` on the source and binary RPMs in Fedora and review every error.

`make rpm` runs `make validate` before rpmbuild. Repository validation is kept
fast and deterministic; actual compilation, payload inspection, unit loading,
upgrade testing and `rpmlint` remain build/test-environment responsibilities.
