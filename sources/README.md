# Prepared RPM sources

Generated third-party archives are placed here by `make sources` and are
ignored by Git:

- `cyan-skillfish-governor-<commit>.tar.gz`
- `cyan-skillfish-governor-vendor-<commit>.tar.xz`
- `bc250-40cu-unlock-<commit>.tar.gz`
- `bc250-cu-live-manager-<commit>.tar.gz`
- matching `.sha256` manifests

`scripts/prepare-sources.py` reads `packaging/upstreams.toml`, downloads and
verifies all three pinned upstreams, and creates the governor Cargo vendor
archive. RPM builds never consume a moving branch and never fetch sources from
scriptlets.
