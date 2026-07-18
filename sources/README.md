# Prepared RPM sources

Generated third-party archives are placed here by `make sources` and are
ignored by Git:

- `cyan-skillfish-governor-<commit>.tar.gz`
- `cyan-skillfish-governor-vendor-<commit>.tar.xz`
- `bc250-40cu-unlock-<commit>.tar.gz`
- `bc250-cu-live-manager-<commit>.tar.gz`
- matching `.sha256` manifests

The governor source and Cargo vendor archive are prepared by
`scripts/prepare-governor-sources.sh`.

The CU archives are downloaded from exact fduraibi and WinnieLV commits by
`scripts/prepare-40cu-source.sh` and `scripts/prepare-live-manager-source.sh`.
RPM builds never consume a moving branch and never fetch sources from scriptlets.
