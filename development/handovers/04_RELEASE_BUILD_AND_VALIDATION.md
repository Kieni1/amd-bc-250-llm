# Release build and validation

## Build authority

Primary:

```text
GitHub Actions
Fedora 44 container/build environment
explicit `workflow_dispatch` run selected as release authority
```

Secondary:

```text
local Fedora 44 reproduction/debugging
```

Push/PR builds are CI evidence. They are not automatically the selected release artifact.

## Current release-gate shape

The release path is intentionally small:

1. prepare/check pinned upstream sources;
2. release-critical source preflight;
3. freeze tracked-only Source0 + RPM spec + source identity;
4. verify frozen Source0/spec;
5. build only the SRPM from the frozen source/spec snapshot with `rpmbuild -bs`;
6. rebuild that generated SRPM once in an isolated temporary RPM topdir;
7. RPM `%check` runs the package-critical module list declared in `release-contract.json` during that single rebuild;
8. copy the exact rebuilt binary/debug RPMs to `dist/`;
9. validate those binary payloads and run configured blocking `rpmlint`;
10. create closed binary/source checksum manifests and release evidence from those exact artifacts;
11. emit a release-selection record only for the explicitly selected authority run.

The release path intentionally does not run a preceding `rpmbuild -ba`: the distributed binary is the exact binary rebuilt from the published SRPM.

## Measured 1.4 GitHub result and 1.5 observability

The architecture above has now completed successfully in GitHub Actions. Observed timing:

```text
1.3-era successful run:
  total job     8m45s
  release gate  7m31s
  Rust compile  ~2m31s + ~2m33s

1.4 successful run:
  total job     5m58s
  release gate  4m29s
  Rust compile  2m49s once
```

Observed improvement is about 2m47s overall (~32%) and about 3m02s in the release gate (~40%). The point is not the exact percentage; the durable conclusion is that the redundant Rust build was real and has been removed without weakening the evidence chain.

The successful run also confirmed that the rebuilt RPM payload passed validation and configured rpmlint completed with zero errors. The workflow uploads authoritative binary RPM/SRPM/release-selection/evidence artifacts before starting the advisory full quality report, so advisory execution no longer delays access to usable release artifacts.

Release 1.5 keeps that architecture and adds only measurement/reporting: machine-greppable `BC250_TIMING` records cover preflight/static checks, source preparation, Source0 freeze/check, `rpmbuild -bs`, authoritative SRPM rebuild, payload validation, rpmlint and release evidence; RPM `%check` reports its own duration from inside the authoritative rebuild. The rebuild summary also identifies the source SRPM and prints the actual rebuilt binary RPM filenames. These changes add no second build and do not weaken any gate.

Use successful 1.5 authority-run timing before considering Cargo source/cache work, non-authoritative `sccache`, or a prebuilt builder image. For an explicitly selected authority run, preserve the meaning of one clean authoritative Rust compilation unless policy is deliberately changed.

Ruff/ShellCheck are blocking before freeze/build, and configured `rpmlint` is blocking after RPM construction. The broader full-suite quality report remains advisory unless a specific finding is deliberately promoted to a release blocker.

## Current cleaned-source validation snapshot

```text
release preflight:       26/26 PASS
package-critical source: 144/144 PASS across 8 modules; authoritative RPM `%check` pending
full source suite:       678/678 PASS across 24 modules (advisory path)
```

The full-suite count is current evidence only; the release contract, not a historical count, defines future hard-gate membership.

## Hard-blocking invariants

A build must stop if any of these is broken:

- source/release identity inconsistency;
- wrong Git source identity in GitHub authority mode;
- incomplete/mismatched Source0/spec freeze;
- missing pinned dependency source/provenance;
- Ruff/ShellCheck failure;
- current-guidance/development-scope inconsistency;
- RPM build failure;
- configured rpmlint finding not covered by an intentional appliance-policy filter;
- core package contract failure;
- missing/incorrect required payload;
- checksum manifest failure;
- the frozen SRPM cannot rebuild in the isolated release-environment topdir with offline Cargo as designed;
- release-evidence cannot bind the produced artifacts.

Do not add hard blockers merely because a check is useful. A blocker needs an artifact-integrity reason.

## Advisory quality path

`make quality-report` should run and preserve:

- Ruff/ShellCheck;
- current-guidance/development-scope checks;
- complete repository source test suite, module-by-module;
- `rpmlint` output when available.

It aggregates broad-suite findings and remains non-blocking for artifact production; it does not downgrade the blocking lint/rpmlint gates.

## Required release evidence

For the selected build retain:

```text
commit SHA
GitHub repository/ref/workflow/run ID/run attempt
Fedora/container identity
useful build-tool versions
Version/Release/NEVRA
Source0 SHA-256
spec SHA-256
binary RPM SHA-256
SRPM SHA-256
closed checksum manifests
release-evidence.json
release-selection.json
hard-gate result
advisory-quality summary
```

## Custom build root

Supported Make-level override:

```bash
make BUILD_DIR=/path release-gate
```

`BC250_BUILD_DIR` is an internal helper variable and should not be treated as a second public Make interface.

## After build selection

Once one authority run is selected, stop changing those candidate bytes. Device testing must consume exactly the selected RPM hash. Any source change requires a new package build and therefore a new exact artifact identity.
