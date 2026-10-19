# Release-candidate execution gate

## Evidence states

Use these states without conflating them:

```text
SOURCE-CANDIDATE
SOURCE-VALIDATED
BUILD-VALIDATED
DEVICE-VALIDATED
ACCEPTED
```

Source-test success never implies an unbuilt RPM passed Fedora or device acceptance.

## Anti-rerun principle

Optimize for one successful external GitHub/device iteration, not for producing a patch quickly. Before candidate handoff:

1. reconcile every current finding;
2. encode the exact previously failing state as a deterministic regression when behavior changes;
3. run focused tests for changed components;
4. test the next command/stage the operator or CI will run;
5. run blocking static/governance/package checks;
6. freeze Source0/spec;
7. validate the extracted frozen Source0;
8. only then hand off for authoritative GitHub build.

## Blocking source/build policy

Blocking candidate gates include Ruff, ShellCheck, current-guidance/scope consistency, package-critical `%check`, configured rpmlint, payload/source integrity, isolated SRPM topdir rebuild evidence and artifact identity. The broad behavioral suite is additional evidence unless a finding exposes a release-critical defect.

## Release-candidate ledger

Track each requirement with:

```text
requirement
implementation status
deterministic source proof
GitHub/Fedora proof
device proof
classification
```

Do not return a candidate while a required source-side cell is blank. Hardware-only branches stay `implemented; device confirmation pending` until the exact selected artifact executes them.

## Authority

GitHub Actions / Fedora 44 is primary release authority. Only an explicitly selected `workflow_dispatch` run, with `release-evidence.json` and `release-selection.json`, defines the authoritative RPM. Workstation execution is reproduction/debug evidence only.
