# Main-chat working rules

## Authority order

Use this order when evidence conflicts:

```text
explicit current user instruction
> current source tree / exact Git commit
> selected GitHub build evidence for those exact bytes
> exact installed-device evidence for that exact RPM
> current handovers
> historical evidence
```

Do not infer current behavior from an older package or archived handover.

## Keep iterations small

For each iteration:

1. state one objective;
2. identify the supported behavior that must remain;
3. change only the required ownership surfaces;
4. run the smallest direct tests that can falsify the change;
5. run the release-critical gate when package bytes are affected;
6. collect broader quality findings together instead of chasing them serially;
7. freeze exact artifact identity only at meaningful boundaries.

## Prefer deletion and direct ownership

When two implementations provide the same supported behavior, prefer the smaller one.

Delete dead compatibility layers, redundant wrappers, duplicate state files, duplicate validators and historical workarounds that no longer protect a supported path.

Do not replace a messy script with a framework unless the framework measurably removes concepts and failure modes.

## Evidence classes stay separate

Always distinguish:

```text
SOURCE    what the tree/tests prove
BUILD     what the selected GitHub/Fedora build produced
DEVICE    what the exact installed RPM did
```

A source PASS does not prove an RPM. A build PASS does not prove device behavior. Device acceptance applies only to the exact RPM hash tested.

## Failure classification before fixing

Classify first:

```text
PRODUCT/PACKAGE DEFECT
BUILD/RELEASE DEFECT
TEST/HARNESS DEFECT
CI/ENVIRONMENT FAILURE
EXPECTED/SUPPORTED STATE
INCOMPLETE EVIDENCE
ADVISORY QUALITY ISSUE
```

Fix the correct layer. Do not weaken product behavior to satisfy a bad harness, and do not delete a real safety contract merely because a test is inconvenient.

## Hard gate vs advisory quality

A hard release failure means artifact identity, buildability, payload integrity, self-contained rebuild or another release-critical invariant is broken. Predictable static/package defects are also hard candidate failures: Ruff/ShellCheck run before freeze/build, and configured rpmlint runs after RPM construction.

The broad behavioral suite remains advisory and should be reviewed as a set. Noncritical long-running product-test findings are not automatically permission to block RPM evidence, but known deterministic release defects must be fixed before artifact selection.

## Preserve raw evidence

For device, recovery, security or benchmark work, save the raw command/request/response and return code before interpretation. A broken parser should not erase the evidence required to reinterpret the result.

## Public contract

Preserve unless deliberately changed:

- public command names and meaningful return codes;
- structured JSON fields intended as machine contract;
- supported persistent data and migration/recovery guarantees;
- model-install cancel/no-mutation behavior;
- clear human next action;
- normal stock/Fedora operation.

Operator-added model registrations are supported state. Tests must not delete them or require an exact total registration count merely to create a tidy baseline.

## Documentation truth

Current docs describe current behavior. Historical detail belongs in repository history or `archive/`, not in active operating instructions.
