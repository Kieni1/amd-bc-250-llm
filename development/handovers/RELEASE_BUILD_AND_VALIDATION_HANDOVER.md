# Release build and validation handover — clean core

## 1. Authoritative build path

The primary RPM build path is the repository GitHub Actions workflow:

```text
.github/workflows/build-rpm.yml
Fedora 44 container
make release-gate
```

The workflow must publish the binary RPM, source RPM, separate binary/source/input checksum evidence, and `release-evidence.json`. Push and pull-request runs are CI evidence only. An explicit `workflow_dispatch` selection run may additionally emit `release-selection.json`; that selected run becomes the artifact authority used for BC-250 acceptance.

Make-level custom build roots use only:

```bash
make BUILD_DIR=/some/path release-gate
```

`BC250_BUILD_DIR` is an internal helper-script variable and is not a supported independent Make-level override.

Local build is backup/reproduction only. Use:

```bash
scripts/ci-local.sh
```

or run the same `make release-gate` directly in a matching Fedora 44 environment. A local backup build may reproduce/debug CI, but it must not silently replace the GitHub artifact identity chosen for device acceptance.

## 2. Clean-core build expectation

The normal release build must no longer depend on building:

- patched amdgpu;
- Fedora kernel source for GFX;
- private Mesa/RADV;
- GFX benchmark/boot artifacts.

If such work still appears in the core build gate after C2, clean-core reconstruction is incomplete.

## 3. Release-gate layering

`make release-gate` now enforces three source-side/build stages:

1. **preflight-freeze** — prepare/verify pinned sources, lint, clean-core/current-guidance checks, host release-pipeline contracts, source-identity recheck, then freeze Source0 plus the RPM spec. In a Git worktree Source0 is built from the Git tracked-file set only, so ignored/untracked workspace junk is excluded; on GitHub Actions the gate also requires checked-out `HEAD` to equal `GITHUB_SHA`;
2. **frozen-package** — build binary/source RPMs from those exact frozen bytes as an unprivileged Fedora builder; RPM `%check` runs the package-context deterministic suite from Source0;
3. **artifact-evidence** — transformed payload proof, configured rpmlint, clean SRPM rebuild, split binary/source manifests, input hashes, and `release-evidence.json`.

## 4. Build evidence

Preserve:

- exact Git commit SHA;
- selected GitHub Actions run ID, workflow name/reference and repository/ref;
- frozen Source0 SHA-256 and RPM spec SHA-256;
- release-contract SHA-256;
- RPM/SRPM NEVRA and SHA-256;
- `SHA256SUMS.binary`, `SHA256SUMS.source`, `SHA256SUMS.inputs`;
- `release-evidence.json` (producer, CI/release-authority flag, source/artifact hashes and recorded build environment);
- `release-selection.json` from the explicitly selected authoritative workflow-dispatch run;
- build log and rpmlint outcome;
- transformed payload validation outcome;
- clean SRPM rebuild result;
- for the selected authoritative run, record the Fedora container/image reference actually used and key build-tool versions for investigation provenance; this is evidence capture, not a requirement to pin dozens of Fedora RPM versions.

## 5. First-failure semantics

Stop at and preserve the first authoritative gate failure. Classify before modifying source.

Do not patch around a failing Fedora gate without understanding whether it is source, dependency, environment or test-tooling related.

## 6. Handoff identity

The exact RPM installed on the BC-250 must be the same artifact whose hash was recorded after the Fedora build.

Do not rebuild between build validation and device acceptance without creating a new artifact identity.
