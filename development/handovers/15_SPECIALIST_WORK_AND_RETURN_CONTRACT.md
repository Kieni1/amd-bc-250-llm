# Specialist work and return contract

Use this when a task is split into a focused side investigation or specialist chat. It preserves the useful discipline of the older sidechat model without numbered lanes or permanent campaign structure.

## Before starting

Define:

```text
objective
exact source/RPM identity
supported behavior at risk
in-scope files/commands/device state
out-of-scope areas
stop/safety conditions
expected evidence
```

If the task can be answered by a small direct test, do that instead of building a harness.

## Stay within the assigned ownership area

A discovered issue outside scope should be reported with evidence and routed back to integration. Do not silently expand into unrelated tuning, model replacement or architecture work.

## Evidence-driven classification

Do not promote log noise, theoretical possibilities or harness assumptions into product defects.

Classify findings as one of:

```text
CONFIRMED PRODUCT/PACKAGE DEFECT
CONFIRMED BUILD/RELEASE DEFECT
CONFIRMED TEST/HARNESS DEFECT
CONFIRMED SECURITY/RECOVERY DEFECT
EXPECTED/SUPPORTED STATE
CI/ENVIRONMENT FAILURE
INCOMPLETE EVIDENCE
OBSERVATION / REVIEW
OUTSIDE SCOPE
```

## Exact artifact boundaries

Do not say only “latest” when exact identity is available.

Source validation, built-artifact evidence and installed-device evidence are different. A result transfers only where the identity boundary permits it.

## Safety and cleanup

For stateful/device work:

- record starting state relevant to the task;
- preserve operator-added registrations/data;
- keep secrets out of logs/evidence;
- establish rollback before destructive mutation;
- stop if cleanup/recovery can no longer be guaranteed;
- verify final restoration rather than merely attempting it.

Do not impose old universal hardware assumptions; report observed board/device state.

## Return to main integration

Return a concise handback containing:

```text
1. exact scope/artifact
2. verdict
3. what changed or was tested
4. confirmed defect(s), if any
5. harness/environment issue(s), if any
6. evidence supporting the verdict
7. cleanup/restoration status
8. files/patches produced
9. recommended next action
```

If no change is needed, say so explicitly. A specialist task is allowed to conclude that the current implementation is adequate.

## Do not create permanent machinery by default

One-off investigations should prefer disposable scripts/notes. Promote a harness into the repository only when it protects a recurring supported behavior and is simpler than the manual alternative.
