# Engineering and test-harness rules

This file preserves the strongest practical lessons from earlier qualification work. These are **engineering rules**, not a requirement to rebuild the old qualification framework.

## Separate operation from interpretation

Do not combine mutation, evidence capture, parsing and final PASS/FAIL in one fragile pipeline.

Preferred order:

1. establish preconditions;
2. perform operation;
3. save raw evidence and return codes;
4. inspect resulting state;
5. parse/interpret saved evidence;
6. summarize/classify;
7. restore and verify cleanup.

If the parser is wrong, raw evidence should still be usable.

## Shell state must be explicit

Do not rely on assignments surviving a pipeline/subshell. If a value is needed later, assign it outside the piped block or write/read it explicitly.

Do not repurpose standard environment variables such as `TMPDIR`, `HOME`, `PATH`, `USER`, `SHELL` or `PWD` as private test state. Use names such as `WORK_DIR`, `EVIDENCE_DIR` and `RUN_STATE`.

For multi-phase state prefer JSON, TSV, explicit key/value parsing or one field per file. Avoid blindly sourcing generated shell state.

## Critical paths use known commands

For destructive or machine-state operations, use the intended command and verify its outcome. Do not assume aliases/functions or an interactive shell environment.

Examples where exact semantics matter include systemd operations, reboot/power commands, package operations, journal capture and network probes.

## Explicit error handling over clever shell behavior

Do not make complex acceptance/recovery logic depend primarily on `set -e`.

Capture return codes deliberately. For pipelines through `tee`, preserve the left command's status with `PIPESTATUS` rather than assuming `$?` refers to it.

Unexpected exceptions/errors should retain context and fail the harness clearly; expected injected errors should be classified separately.

## Safety gates before destructive action

Before reboot, restore, prune/delete, package replacement, database mutation or service-topology transition, establish the prerequisites required to recover safely.

Depending on the operation this may include:

```text
exact package/artifact identified
starting state captured
backup/rollback material verified
sufficient disk/memory headroom
expected service state established
no unrelated failed units
required endpoint/data ready
```

If the harness cannot establish whether the mutation is safe, abort rather than assuming safety.

## Failure is not the same as incomplete coverage

Use explicit result states. Do not let `all([])` or a missing fixture become accidental PASS.

A test may be `INCOMPLETE` because:

- safe memory/disk headroom was unavailable;
- an external vantage was unavailable;
- a fixture/model was not installed by design;
- a test timeout prevented conclusion;
- required raw evidence was lost/corrupt.

That is not automatically a product defect.

## Assertions should match contracts

Prefer properties/invariants over incidental ordering and exact internal text.

Good examples:

- required default model identity exists;
- an operator-added registration remains preserved;
- a protected endpoint is not externally reachable;
- a rollback restores valid live state;
- a selected release record matches the artifact hashes.

Avoid exact total model counts, exact dictionary ordering, shell implementation details or private helper call sequences unless they are themselves the contract.

## Native path and adapter path are different evidence

When behavior passes through an adapter (Web UI, proxy, wrapper CLI), distinguish:

- backend/native behavior;
- adapter behavior;
- policy/configuration behavior.

A failure in one layer should not automatically be attributed to another.

## Readiness means real readiness

After restart/reboot do not equate `systemctl start` success with application readiness. Check the relevant service endpoint/state and make the check bounded.

Likewise, a listening socket alone may not prove application readiness.

## Cleanup must be verified

A `finally`/trap that runs cleanup is not proof cleanup succeeded.

Verify the important ending invariants: service mode, temporary files, firewall rules, data path, model registrations, package state, and any test-created state.

If exact restoration cannot be proven, report it.

## Preserve error context in HTTP/API helpers

Record enough of the request target, HTTP status and bounded response body/error to diagnose failure. Do not discard the response and return only a generic boolean.

Do not log secrets/tokens.

## Timeouts should match operations

Use bounded timeouts, but classify them correctly. A timeout on model generation may mean runtime slowness, test budget mismatch or actual hang; preserve the evidence needed to tell which.

Long-running tests should write progress/evidence incrementally so interruption does not erase the run.

## Reuse semantic authorities

Do not copy version constants, model defaults, prompt text, semantic parsers or policy tables into multiple harnesses. Read/import the authoritative source where practical.

Duplicated semantic logic is particularly dangerous because a product change can leave the test validating yesterday's rule.

## Injection points stay narrow

Failure injection must be explicit, reversible and recorded. Do not monkeypatch/shim so broadly that the test no longer exercises the production path.

An injected failure is expected test stimulus; the product fails only if its response violates the intended fail-closed/recovery contract.
