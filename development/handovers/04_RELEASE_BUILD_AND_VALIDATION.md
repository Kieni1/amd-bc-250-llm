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
5. build RPM/SRPM from the frozen source tree;
6. RPM `%check` runs the package-critical module list declared in `release-contract.json`;
7. validate binary payload and package metadata;
8. create closed binary/source checksum manifests;
9. run the isolated SRPM-topdir rebuild in the release environment;
10. emit release evidence;
11. emit a release-selection record only for the explicitly selected authority run.

Ruff/ShellCheck are blocking before freeze/build, and configured `rpmlint` is blocking after RPM construction. The broader full-suite quality report remains advisory unless a specific finding is deliberately promoted to a release blocker.

## Current cleaned-source validation snapshot

```text
release preflight:       22/22 PASS
package-critical %check: 126/126 PASS across 8 modules
full source suite:       651/651 PASS across 24 modules (advisory path)
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
- SRPM cannot rebuild self-contained/offline as designed;
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
