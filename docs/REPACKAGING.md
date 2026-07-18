# Repackaging and source refresh

The source RPM uses immutable third-party revisions:

```text
filippor/cyan-skillfish-governor
  60ab6e5b354f01f287c73d920990dcd618a674cc

fduraibi/bc250-40cu-unlock
  6c3969ddee40e894297869e6ca30537f274619cb

WinnieLV/bc250-cu-live-manager
  8eb45f07810af738f3e4945ea0cc29d399e378a6
```

Prepare all archives:

```bash
make sources
cat sources/*.sha256
```

The governor script downloads the exact source tree and vendors Cargo
dependencies. The CU scripts download exact commit archives and verify the
expected helper, patch and live-manager files.

Do not fetch third-party source during RPM scriptlets.

## Change a pinned revision

1. Review upstream code, license and history.
2. Update the commit consistently in:
   - `Makefile`
   - `packaging/bc250-llm-server.spec`
   - the matching preparation script
   - `licenses/THIRD_PARTY_NOTICES.md`
   - relevant documentation and validation checks
3. Remove old generated archives:

   ```bash
   make clean
   make sources
   ```

4. Run:

   ```bash
   make validate
   make rpm
   ```

5. Test clean install, upgrade, removal and recovery on the intended Fedora
   kernel.

## Project URL

The spec uses `https://github.com/Kieni1/amd-bc-250-llm`.

## Release checklist

- Verify source checksums and licenses.
- Confirm the main RPM owns `/usr/bin/bc250-40cu`,
  `/usr/bin/bc250-cu-live-manager` and both pinned CU payloads.
- Confirm no RPM scriptlet modifies the kernel or CU routing.
- Test Ollama startup with an existing `/usr/share/ollama` passwd home.
- Test Open WebUI on an empty `/var/lib/open-webui`.
- Test backup and restore with SELinux enforcing.
- Test the coding agent with a limited Gitea token.
- Run `rpmlint` on the SRPM and binary RPMs.
