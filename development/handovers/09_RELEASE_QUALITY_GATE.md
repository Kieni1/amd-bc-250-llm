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
- authoritative frozen-SRPM rebuild/publish PASS;
- release-evidence record;
- explicit release-selection record for the chosen workflow-dispatch run;
- exact RPM/SRPM hashes.

Only then call the build selected for device acceptance.

## Current 1.5 build status

The 1.5 source candidate retains the proven 1.4 SRPM-first authority chain and adds stage-timing/log instrumentation without changing build authority. A selected 1.5 GitHub `workflow_dispatch` build is still required before BUILD-VALIDATED status.

Prior 1.4 authority evidence remains useful: payload validation passed, configured rpmlint reported zero errors, and the job completed in 5m58s with a 4m29s release gate and one 2m49s Rust/governor compilation. Do not transfer those artifact hashes or BUILD PASS status to 1.5.

