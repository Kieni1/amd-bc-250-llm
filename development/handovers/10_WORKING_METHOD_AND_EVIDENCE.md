# Working method and evidence discipline

## Freeze meaningful boundaries

Hash source archives, selected RPMs/SRPMs and important evidence at release boundaries. Do not create hash bureaucracy for every transient file.

## One canonical tree

Avoid parallel partially-fixed candidates. Merge accepted changes into one tree before final validation.

## Raw evidence before interpretation

For device/recovery/security/benchmark operations:

1. perform the operation;
2. save raw stdout/stderr/request/response and return code;
3. capture relevant state/logs;
4. interpret the saved evidence;
5. produce a concise structured summary.

A parser or evaluator failure must not destroy the underlying evidence.

## Preserve first authoritative failure

Save the first meaningful failure before changing code. Later errors are often secondary effects of the first failure or of the attempted fix.

## Starting and ending state matter

Stateful tests should record enough starting state to restore what they touch. After the test, verify cleanup rather than merely attempting cleanup.

Useful dimensions when relevant:

- package identity;
- service state;
- model registrations;
- memory/swap/PSI;
- storage/free space;
- firewall/network exposure;
- data/backup identity;
- boot ID for reboot tests.

Do not collect all of these by habit if they are irrelevant to the test.

## Second-pass review

After implementation, perform one bounded omission/QC pass:

- identity/version surfaces;
- help/completions/docs;
- install/uninstall manifests;
- source/payload boundaries;
- stale historical references;
- privilege/environment assumptions in tests;
- security/data/recovery implications of the change.

The second pass is valuable; it must not become a permanent subsystem.

## Evidence taxonomy

Use clear classifications instead of ambiguous “failed”:

```text
CONFIRMED PRODUCT/PACKAGE DEFECT
CONFIRMED BUILD/RELEASE DEFECT
CONFIRMED TEST/HARNESS DEFECT
CONFIRMED SECURITY/RECOVERY DEFECT
EXPECTED/SUPPORTED STATE
CI/ENVIRONMENT FAILURE
INCOMPLETE EVIDENCE
OBSERVATION / REVIEW
```

## Side work return format

Narrow specialist work should return:

```text
scope / exact artifact
what was tested or changed
result
first authoritative failure if any
raw evidence location/hash when meaningful
classification
cleanup/restoration status
recommended next action
```

## Durable decisions

Current durable decisions:

- stock-first clean core;
- no package-owned GFX/kernel/Mesa experiment architecture;
- GitHub/Fedora is primary build authority;
- local build is reproduction/debugging;
- hard release gate stays small;
- Ruff/ShellCheck and configured rpmlint are blocking candidate gates; broad behavioral quality remains aggregated/advisory by default;
- exact artifacts cross source/build/device boundaries;
- simplification is bounded risk/ownership reduction; the product roadmap prioritizes RAG/document quality, German–French translation UX and polished local-assistant operation.
