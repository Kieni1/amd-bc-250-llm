# Release quality gate

## Source-ready

A source tree is ready for an authoritative build when:

- Version/Release and release contract agree;
- source/provenance inputs are complete;
- release-critical preflight passes;
- frozen Source0/spec can be reproduced and checked;
- no known defect makes the package unsafe or knowingly unbuildable;
- Ruff/ShellCheck and current guidance/scope pass;
- remaining broad-suite advisory findings have been reviewed and classified rather than ignored.

## Build-selected

After GitHub builds, require:

- expected main binary RPM and SRPM;
- configured rpmlint PASS with no unfiltered findings;
- payload contract PASS;
- closed checksum manifests PASS;
- isolated SRPM-topdir rebuild PASS;
- release-evidence record;
- explicit release-selection record for the chosen workflow-dispatch run;
- exact RPM/SRPM hashes.

Only then call the build selected for device acceptance.

## Device-smoke-ready

For `0.14.1-1.2`, use the small core functionality check. Broad historical qualification is not a prerequisite.

## Advisory finding classification

```text
FIX-NOW   evidence indicates current product/release risk
DEFER     valid issue outside this iteration
REMOVE    obsolete check or no longer-supported invariant
INFO      useful observation with no required change
```

A WARN quality report is not itself a release failure. Its contents still need conscious review.

## Safety escalation

Promote an advisory finding to a blocker when it demonstrates one of:

- data-loss/recovery risk;
- security exposure or secret leakage;
- package identity/payload corruption;
- non-reproducible release artifact or isolated SRPM-topdir rebuild failure;
- core public command unusable in normal supported operation;
- install/upgrade/reboot cannot converge safely.

## Confidence language

Use precise labels:

```text
source-ready
authoritative build selected
package checks passed
device smoke passed
known-good baseline
```

Do not say “fully qualified” when only the small smoke was performed.
