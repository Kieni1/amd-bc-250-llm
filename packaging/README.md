# RPM packaging

- `bc250-llm-server.spec` is the Fedora 44 RPM recipe.
- `bc250-llm-server.tmpfiles` creates persistent data and backup directories
  without deleting them on uninstall.
- `90-bc250-llm-server.preset` enables only the bundled governor and leaves
  optional maintenance and Wake-on-LAN timers disabled.
- `bc250` is the multicall dispatcher behind stable `/usr/bin/bc250-*` aliases.
- `install-manifest.tsv` is the authoritative payload install and ownership map.
- `upstreams.toml` records pinned third-party revisions and checksums.
- Model catalogs, long-name Modelfiles and feature-specific task, agent,
  experiment, MTP and embedding helpers live under `models/`; the installed
  public command names remain stable.
- `scripts/prepare-sources.py` prepares all upstream archives, including the
  governor Cargo vendor archive.
- `sources/` contains generated source archives used by rpmbuild; archives and
  checksums are intentionally ignored by Git.

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
option, run `depmod` or `dracut`, or reboot the host. Those actions remain
explicit operator commands.

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

`make rpm` prepares pinned sources, creates the project source archive, runs
the basic pre-1.0 RPM preflight and invokes rpmbuild. The preflight checks only
syntax, version alignment, required inputs, model metadata and manifest source
paths. Full policy, unit, security and `rpmlint` gates are deferred to the
1.0.0 production-readiness cycle.
