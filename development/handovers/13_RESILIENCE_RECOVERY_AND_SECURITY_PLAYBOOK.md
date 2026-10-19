# Resilience, recovery and security playbook

This is a **conditional playbook**, not the normal release checklist. Use the relevant section when a change touches lifecycle safety, long-running state, recovery/data or external exposure.

## Common evidence contract

For nontrivial device tests retain, as applicable:

```text
exact RPM/commit identity
starting state
commands/requests and return codes
timestamps
relevant logs/state snapshots
result classification
cleanup/restoration result
archive/hash for significant evidence
```

Preserve operator-added model registrations and private data. Keep secrets out of evidence.

## Lifecycle / failure injection

Use when touching install/upgrade, service transitions, maintenance, destructive cleanup, backup/restore or mode changes.

High-value cases are boundaries around irreversible operations:

- failure before mutation;
- failure during staging/preparation;
- failure immediately before commit/replacement;
- failure immediately after commit but before validation;
- interruption/restart during a multi-step transition.

Required properties:

- precondition cannot be established -> fail closed;
- failure before commit leaves live state unchanged where practical;
- post-commit validation failure follows a deterministic recovery path;
- rerunning the supported operation converges rather than compounding damage;
- cleanup/restoration is verified.

Do not inject dozens of arbitrary faults. Choose the few transitions where a wrong outcome would create operator pain or data risk.

## Long-run / state drift

Use when a change could leak resources, accumulate state, degrade after repeated requests or drift across idle/reload cycles.

Prefer a bounded representative soak over a ritual fixed duration. Capture periodic checkpoints rather than only final state.

Useful dimensions when relevant:

- memory/swap/PSI trend;
- service restarts/failures;
- model residency and expected eviction;
- storage growth;
- repeated request latency/error trend;
- registrations/configuration drift;
- unexpected failed units or kernel/runtime faults.

A long run should stream checkpoints to durable evidence so interruption does not erase the result.

## State-machine / idempotency

Use when a feature has modes, desired/live state or repeated convergence operations.

Test **properties**, not every theoretical permutation.

Examples:

- repeated install/repair converges;
- repeated enable/disable leaves the same intended state;
- cancel/no-selection is no-op;
- interrupted operation can be rerun safely;
- operator-added registrations remain intact;
- transitions do not leave two mutually exclusive modes active.

Prefer a few high-risk transition sequences over an exhaustive state matrix.

## Security / external boundary

Same-host testing cannot prove LAN isolation.

When making an external-exposure claim, test from a second host/network namespace or another credible external vantage where possible.

Check the current intended boundary, not a historic port list by habit. Typical questions:

- Is the user-facing web port reachable as intended?
- Are loopback/private backends not externally reachable?
- Do firewall ranges/rich rules/custom services accidentally expose protected ports?
- Are authentication/ACL controls effective at the user-facing boundary?
- Are secret/token files privately owned and absent from logs/evidence/support bundles?

Temporary firewall/auth fixtures must be restored exactly.

A security verifier that cannot inspect an active custom service/rule should report incomplete/unsafe-to-claim-clean rather than declaring isolation PASS.

## Recovery / data integrity

Use disposable/synthetic state or a verified clone for destructive recovery tests whenever possible.

Before replacing live data:

- establish rollback material;
- validate archive/checksum where applicable;
- stage outside live state first;
- reject unsafe archive members/links/devices;
- validate data integrity before commit;
- validate ownership/permissions afterward.

High-value failure cases:

```text
missing/wrong checksum
truncated archive
missing required database/content
integrity check failure
unsafe archive member
staging extraction failure
failure immediately before live commit
failure after commit but before validation
insufficient disk/write failure when safely reproducible
```

Post-restore validation failure should follow a deterministic rollback path where the product claims automated safety.

Existing known data inconsistencies may only be tolerated if the current product contract explicitly allows them; newly introduced inconsistencies fail.

## Bounded combined acceptance

If several resilience fixes are integrated together, do not rerun every deep campaign. Select one representative high-risk check from each changed ownership area plus:

- normal service restart;
- supported reboot;
- final package/health/registration/data cleanup check.

Combined acceptance is for integration confidence, not discovering new tuning or architecture.
