# GitHub build-time optimization and timing — 1.6 source state

## Scope

This file records the current GitHub build-time result and the constraints for future optimization work. It is not a request to redesign the release pipeline again.

Current package/build line:

```text
bc250-llm-server 0.14.1-1.6 source candidate
Fedora 44
GitHub Actions = primary release/build authority
workstation/local CI = secondary reproduction/debugging
```

## Problem that 1.4 solved

Before 1.4, the authoritative GitHub release path compiled the Rust governor twice:

```text
frozen Source0/spec
→ rpmbuild -ba
   → binary RPM
   → SRPM
   → Rust governor compile #1

→ rpmlint

→ isolated SRPM rebuild
   → rpmbuild --rebuild generated SRPM
   → Rust governor compile #2
   → rebuilt binary discarded
```

A successful 1.3-era trace showed:

```text
total job:    8m45s
release gate: 7m31s
Rust build 1: ~2m31s
Rust build 2: ~2m33s
```

The two Rust compilations alone consumed roughly five minutes. This was real duplicate work, not hypothetical optimization potential.

## 1.4 authority chain

1.4 intentionally changed the authoritative path to:

```text
freeze exact Source0 + spec
        ↓
rpmbuild -bs
        ↓
generated frozen SRPM
        ↓
rpmbuild --rebuild in isolated temporary topdir
        ↓
ONE Rust/governor compilation
        ↓
RPM %check during that rebuild
        ↓
copy those rebuilt binary/debug RPMs to dist/
        ↓
payload validation on those exact RPMs
        ↓
blocking rpmlint on those exact artifacts
        ↓
closed manifests / release evidence / release selection
        ↓
those exact rebuilt binaries become the GitHub release artifacts
```

This is a cleaner provenance statement than the old arrangement: the distributed binary is exactly the binary produced by rebuilding the published SRPM. There is no second proof-only binary whose output is discarded.

The workflow authority boundary did not change. One unprivileged `make release-gate` remains the artifact-producing path, and explicit `workflow_dispatch` selection remains the release-authority control.

## Successful 1.4 result

Observed successful GitHub run:

```text
total job:    5m58s
release gate: 4m29s
Rust compile: 2m49s once
```

Compared with the successful pre-1.4 trace:

```text
2m47s faster overall
~32% total-job reduction
~3m02s faster release gate
~40% release-gate reduction
```

The exact numbers may vary with GitHub runner load, but the durable result is established: eliminating the duplicate authoritative compilation materially reduced wall-clock time.

The optimization did not remove or downgrade:

```text
frozen Source0/spec verification
package %check
isolated SRPM rebuild
payload validation
blocking rpmlint
artifact hashes
closed checksum manifests
release evidence
release selection semantics
explicit workflow_dispatch release authority
```

The rebuilt RPM payload passed validation, and rpmlint completed with zero errors in the successful run.

## Artifact-availability workflow improvement

The GitHub workflow now uploads the authoritative artifacts immediately after the release gate:

```text
binary RPM
source RPM
release-selection / release-evidence artifacts
```

Only after those usable release artifacts are uploaded does it run the advisory full quality report.

The advisory report remains part of CI. It simply no longer delays artifact availability.

The advisory report took roughly 29–31 seconds in the observed run. Reordering therefore improves operator UX by roughly half a minute without weakening validation or increasing compute usage.

Do not split the advisory report into a separate parallel job merely for speed unless new evidence justifies the additional Fedora-container startup, dependency installation and GitHub-minute cost.

## 1.5 log wording cleanup — implemented

The 1.4 rebuild output could read approximately:

```text
Authoritative SRPM rebuild published 3 binary RPM(s):
bc250-llm-server-0.14.1-1.4.fc44.src.rpm
```

The count is correct, but the displayed filename is the source RPM. This is a wording/reporting issue, not an artifact or provenance defect.

Release 1.5 implements this cleanup. The summary now identifies the source SRPM and prints the actual rebuilt binary RPM filenames, equivalent to:

```text
Authoritative SRPM rebuild published 3 binary RPM(s) from SRPM:
bc250-llm-server-0.14.1-1.4.fc44.src.rpm
```

or print the actual rebuilt binary RPM filenames.

This was folded into 1.5 alongside substantive package changes; it was not released alone.

## Remaining visible costs

After the large duplicate-work fix, the remaining observed costs are roughly:

```text
Rust compile:        2m49s
DNF/bootstrap:       ~40s
advisory suite:      ~31s, no longer on artifact critical path
other release work:  ~1m40s
```

These figures are approximate observations from the current successful run, not permanent performance budgets.

The DNF/bootstrap stage is no longer an attractive first target. A prebuilt Fedora builder image might save part of ~40 seconds, but it would add image maintenance, provenance, update and trust work for a comparatively small gain.

## 1.5 timing instrumentation — implemented

Release 1.5 adds lightweight, machine-greppable timing without restructuring the authority chain. Successful release runs now emit `BC250_TIMING` records for:

```text
preflight-static
preflight
prepare-sources
source-check
freeze-source0
check-frozen-inputs
rpmbuild-bs
authoritative-srpm-rebuild
rpm-check              (from inside the authoritative rebuild)
payload-check
rpmlint
release-evidence
```

The wrapper records elapsed seconds and return code. `%check` measures itself inside the same authoritative SRPM rebuild, so instrumentation does not add another compilation or package build.

The next optimization decision must use timing from successful 1.5 authority runs. The source change provides observability; it does not claim a new speedup before those measurements exist.

## Cargo cache / sccache policy

There was no `sccache` use in the measured run. Caching could potentially help because the governor changes relatively infrequently, but it should not be the next automatic change.

Recommended order:

1. keep the SRPM-first architecture;
2. use the 1.5 stage timing now present;
3. measure successful clean authority runs;
4. identify whether Rust compilation remains the dominant actionable cost;
5. only then evaluate caching.

For ordinary push/PR builds, aggressive `sccache` use may be reasonable because those runs provide CI feedback rather than final artifact authority.

For an explicitly selected `release_authority=true` / workflow-dispatch authority run, be cautious. Cached compilation changes the meaning of “one clean authoritative Rust compilation.” Do not adopt it there without deliberately updating the evidence policy and deciding that cached compiler outputs are acceptable release provenance.

## Prebuilt builder-image policy

A custom Fedora builder image is not currently recommended.

Potential advantage:

```text
reduce some or all of the ~40s DNF/bootstrap cost
```

Costs introduced:

```text
builder-image maintenance
base-image update cadence
additional provenance chain
image publication/retention
potential divergence from normal Fedora package availability
additional security/update ownership
```

Do not accept that ownership unless timing data shows bootstrap has become significant enough to justify it.

## Local CI relationship

The workstation/local reproducer should continue to mirror GitHub by installing the same relevant package set and invoking the same `make release-gate` behavior. Local CI remains secondary reproduction/debugging evidence; it must not silently replace the GitHub authority chain.

No structural local-CI redesign is required because of the 1.4 optimization or 1.5 timing instrumentation.

## Durable recommendation

```text
KEEP the SRPM-first architecture proven in 1.4 and retained in 1.5.
Do not weaken release evidence.
Do not reintroduce rpmbuild -ba into the authoritative path.
Do not optimize from intuition after the duplicate build is gone.
Use the lightweight stage timing included in 1.5.
Measure successful authority runs.
Then optimize the measured bottleneck.
```

Possible future ideas, not current tasks:

```text
Cargo source/cache optimization
sccache for non-authoritative push/PR builds
prebuilt Fedora builder image
```

They remain ideas until measurements justify them.
