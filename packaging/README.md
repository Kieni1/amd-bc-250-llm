# RPM packaging

- `bc250-llm-server.spec` is the Fedora 44 RPM recipe.
- `bc250-llm-server.tmpfiles` creates persistent data and backup directories
  without deleting them on uninstall.
- `90-bc250-llm-server.preset` enables only the bundled governor and leaves
  optional maintenance and Wake-on-LAN timers disabled.
- `wrappers/` provides stable `/usr/bin/bc250-*` commands.
- `scripts/prepare-governor-sources.sh` creates the pinned governor source and
  Cargo vendor archives.
- `scripts/prepare-40cu-source.sh` creates the pinned fduraibi source archive.
- `sources/` contains generated source archives used by rpmbuild; archives and
  checksums are intentionally ignored by Git.

The main package is `bc250-llm-server`. The experimental
`bc250-llm-server-40cu` subpackage owns only:

- `/usr/bin/bc250-40cu`
- `/usr/libexec/bc250-llm-server/40cu/`
- `/usr/share/bc250-llm-server/40cu/`

No RPM scriptlet may replace or restore `amdgpu.ko`, write the 40-CU modprobe
option, run `depmod` or `dracut`, or reboot the host. Those actions remain
explicit operator commands.

The coding-agent helpers belong to the main package but do not download a model
or create an Ollama model during installation.

The memory and swap helpers are also operator-triggered. RPM scriptlets must not
change the kernel command line, create a swap file, resize zram or reboot. The
balanced Ollama runtime profile is shipped as a normal systemd drop-in; switching
profiles creates an explicit `/etc/systemd/system` override.

Run before building:

```bash
make sources
make validate
make rpm
```
