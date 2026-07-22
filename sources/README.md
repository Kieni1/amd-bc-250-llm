# Prepared RPM sources

Generated third-party archives are placed here by `make sources` and are
ignored by Git:

- `cyan-skillfish-governor-<commit>.tar.gz`
- `cyan-skillfish-governor-vendor-<commit>.tar.xz`
- `bc250-40cu-unlock-<commit>.tar.gz`
- `bc250-cu-live-manager-<commit>.tar.gz`

`scripts/prepare-sources.py` reads `packaging/upstreams.toml`, reuses non-empty
cached archives, downloads missing pinned revisions, and creates the offline
governor Cargo vendor archive. `make clean` keeps these inputs;
`make clean-sources` removes them explicitly. RPM builds never consume a moving
branch and never fetch sources from scriptlets.
