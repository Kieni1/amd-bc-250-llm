# RPM packaging

- `bc250-llm-server.spec` is the Fedora 44 RPM recipe.
- `bc250-llm-server.tmpfiles` creates persistent data and backup directories
  without deleting them on uninstall.
- `bc250-llm-server.sysusers` makes the RPM provide and create its own `ollama`
  user and group without depending on Fedora's Ollama package.
- `90-bc250-llm-server.preset` enables only the bundled governor and leaves
  optional maintenance and Wake-on-LAN timers disabled.
- `bc250` is the multicall dispatcher behind stable `/usr/bin/bc250-*` aliases.
- `uninstall.sh` is the explicitly confirmed full-purge workflow exposed as
  `/usr/bin/bc250-uninstall`.
- `install-manifest.tsv` is the authoritative payload install and ownership map.
- `upstreams.toml` records pinned third-party revisions, URLs and archive names.
- Model catalogs, long-name Modelfiles and feature-specific task, agent,
  experiment, MTP and embedding helpers live under `models/`; the installed
  public command names remain stable.
- Repository inputs are grouped by purpose: `cmd/` for host commands,
  `config/` for shipped service configuration and `examples/` for
  operator-adapted integrations.
- `scripts/prepare-sources.py` prepares all upstream archives, including the
  governor Cargo vendor archive.
- `sources/` is the reusable local cache of external rpmbuild inputs and is
  intentionally ignored by Git.

The main package is `bc250-llm-server`. It owns the experimental CU tools:

- `/usr/bin/bc250-40cu`
- `/usr/bin/bc250-cu-live-manager`
- `/usr/libexec/bc250-llm-server/40cu/`
- `/usr/share/bc250-llm-server/40cu/`
- `/usr/share/bc250-llm-server/cu-live-manager/`

The manifest intentionally centralizes install paths, modes and generated RPM
ownership in one table. This reduces drift between `%install` and `%files`, at
the cost of a project-specific layer that Fedora packagers must learn. Keep the
format limited to the existing six entry types; if it grows beyond simple file
placement, replace it with explicit spec sections rather than evolving a second
general-purpose packaging language.

No RPM scriptlet may replace or restore `amdgpu.ko`, write the 40-CU modprobe
option, run `depmod` or `dracut`, or reboot the host. The guided installer may
prepare a default-off replacement for the exact running kernel. Writing the
enable option and rebooting remains an explicit operator command.

The ordinary RPM uninstall remains non-destructive and retains application
state. The separate `bc250-uninstall` command is intentionally destructive: it
restores verified stock CU module backups and deletes appliance state only
after a dedicated confirmation. Dependency cleanup is limited to the package
names recorded by the guided installer; never replace it with an unbounded
`dnf autoremove`.

The coding-agent helpers belong to the main package but do not download a model
or create an Ollama model during installation.

The memory and swap helpers are also operator-triggered. RPM scriptlets must not
change the kernel command line, create a swap file, resize zram or reboot. The
balanced Ollama runtime profile is shipped as a normal systemd drop-in; switching
profiles creates an explicit `/etc/systemd/system` override.

Build with:

```bash
make rpm
```

`make rpm` fetches only missing pinned sources, creates the project source
archive, runs the repository preflight and invokes rpmbuild. `make clean`
removes disposable build output without throwing away downloaded inputs;
`make sources-check`, `make clean-sources` and `make distclean` expose the other
cache operations directly. The preflight covers syntax, version/changelog
alignment, required inputs, paths, command routing, strict model metadata, the
install manifest and focused unit tests. Fedora policy and `rpmlint` remain
build-environment checks.

Installable packages are written to `dist/RPMS/`; source packages are written
to `dist/SRPMS/`. The build also verifies that the binary payload contains
`/usr/bin/bc250-install-ollama`. A source RPM is build input and must not be
used as the appliance runtime package.
