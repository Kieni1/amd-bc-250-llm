# Repackaging and source refresh

The source RPM uses immutable third-party revisions. The authoritative URLs,
commits, checksums and required archive members are in
`packaging/upstreams.toml`; the RPM spec retains only the macros needed to name
its `Source` entries.

Prepare all archives:

```bash
make sources
cat sources/*.sha256
```

The source preparer downloads exact source trees, validates required archive
members and vendors the governor's Cargo dependencies.

Do not fetch third-party source during RPM scriptlets.

## Change a pinned revision

1. Review upstream code, license and history.
2. Update the commit and checksum in `packaging/upstreams.toml`.
3. Update the corresponding RPM macro in
   `packaging/bc250-llm-server.spec` so its source name remains aligned with
   the lock.
4. Update source/license notices when the reviewed upstream changes:
   - `licenses/THIRD_PARTY_NOTICES.md`
   - relevant documentation
5. Remove old generated archives:

   ```bash
   make clean
   make sources
   ```

6. Run:

   ```bash
   make rpm
   ```

7. Test clean install, upgrade, removal and recovery on the intended Fedora
   kernel.

## Project URL

The spec uses `https://github.com/Kieni1/amd-bc-250-llm`.

## Release checklist

- Bump `VERSION` and the spec `Version` together so DNF treats the package as
  an upgrade and runs the upgrade scriptlets normally. Add a matching changelog
  entry for the release history; it is not a preflight build gate.
- Verify source checksums and licenses.
- Confirm the main RPM owns `/usr/bin/bc250-40cu`,
  `/usr/bin/bc250-cu-live-manager` and both pinned CU payloads.
- Confirm no RPM scriptlet modifies the kernel or CU routing.
- Test Ollama startup with an existing `/usr/share/ollama` passwd home.
- Test Open WebUI on an empty `/var/lib/open-webui`.
- Test backup and restore with SELinux enforcing.
- Test the coding agent with a limited Gitea token.
- Reintroduce full policy, unit, security and `rpmlint` gates for the 1.0.0
  production-readiness cycle.

## Pre-1.0 build validation

`make rpm` runs `make validate` automatically before rpmbuild. The current
preflight is deliberately limited to build-blocking checks: shell and Python
syntax, `VERSION`/spec alignment, required build inputs, strict model catalog
and Modelfile consistency, and install-manifest source paths. The RPM build
then validates source preparation, compilation, installation and file
packaging in Fedora's normal build environment.

Unit, repository-policy, security-scan and `rpmlint` gates are deferred until
the 1.0.0 production-readiness cycle. They must not be mixed into this
pre-production build gate piecemeal.
