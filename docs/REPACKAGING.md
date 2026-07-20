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
   `packaging/bc250-llm-server.spec`; validation requires it to match the lock.
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
   make validate
   make rpm
   ```

7. Test clean install, upgrade, removal and recovery on the intended Fedora
   kernel.

## Project URL

The spec uses `https://github.com/Kieni1/amd-bc-250-llm`.

## Release checklist

- Bump `VERSION`, the spec `Version`, and the top changelog entry together so
  DNF treats the package as an upgrade and runs the upgrade scriptlets normally.
- Verify source checksums and licenses.
- Confirm the main RPM owns `/usr/bin/bc250-40cu`,
  `/usr/bin/bc250-cu-live-manager` and both pinned CU payloads.
- Confirm no RPM scriptlet modifies the kernel or CU routing.
- Test Ollama startup with an existing `/usr/share/ollama` passwd home.
- Test Open WebUI on an empty `/var/lib/open-webui`.
- Test backup and restore with SELinux enforcing.
- Test the coding agent with a limited Gitea token.
- Run `rpmlint` on the SRPM and binary RPMs.
