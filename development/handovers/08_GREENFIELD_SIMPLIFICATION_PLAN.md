# Bounded simplification alongside the office-intelligence roadmap

## Goal

After the exact `0.14.1-1.7` RPM passes the small core smoke, move directly into the office-intelligence roadmap. Perform cleanup only when it clearly reduces obsolete ownership, release risk or duplicated state without changing the supported appliance contract.

Success means fewer concepts, owners, scripts and states — not a larger abstraction layer. Simplification is a bounded, opportunistic risk-reduction activity, not a transition phase and not the product roadmap. Product work on RAG/document quality, German–French translation UX and polished local-assistant workflows proceeds without waiting for cleanup to finish.

## Establish the behavioral baseline

Before deleting code, write down only the behavior we actually intend to preserve:

- install/upgrade and package identity;
- public CLI behavior;
- normal service topology;
- Web interface availability;
- model catalog/install/no-mutation behavior;
- one normal inference;
- reboot persistence;
- supported recovery/data guarantees.

Everything else must justify itself.

## Inventory executable surfaces

List every public command, internal helper, service, script and state file. Classify:

```text
KEEP      owns supported behavior directly
SIMPLIFY  needed behavior, excess implementation complexity
MERGE     duplicates another owner
DELETE    obsolete, historical, unreachable or unjustified
MOVE      development/experimental concern that should leave product core
```

Also identify callers. A helper with no meaningful caller is a deletion candidate, not a documentation task.

## Recommended domain order

1. release/build scripts;
2. monitoring/status/health/verify;
3. installer/uninstaller/maintenance;
4. model management;
5. qualification/resilience remnants;
6. benchmark tooling;
7. documentation/development helpers.

Work one ownership domain at a time so failures remain attributable.

## Simplification questions

For every script/state/check ask:

- What supported behavior fails if this disappears?
- Is another component already authoritative for the same fact?
- Is this validating a historical workflow rather than current product state?
- Is the same condition checked in multiple layers?
- Can RPM/systemd/Fedora provide the invariant structurally?
- Can a public command call the real owner directly?
- Is a state file recording data that can be obtained reliably from one existing authority?
- Is a shell parser becoming more complex than the behavior it protects?

If the answer points to deletion, delete the code and its implementation-detail tests together.

## Shell simplification

Prefer shallow shell orchestration. Do not build wrapper chains.

When structured parsing/state dominates a shell script, either simplify the behavior or move only that structured portion to Python. Avoid creating internal frameworks with one caller.

Avoid:

- implicit state through sourced shell snippets;
- multiple names for the same build/state directory;
- copied version constants;
- scripts that validate each other recursively;
- large all-in-one scripts that mutate, parse, classify and report in one pipeline.

## Qualification/resilience cleanup

Older resilience machinery may contain useful **rules**, but its harnesses/state machines are not automatically current product requirements.

Retain safety properties such as fail-closed destructive operations, rollback-before-replace and external-vantage security evidence. Delete obsolete campaign orchestration, sidechat numbering, stale acceptance matrices and helpers that no longer serve a supported command.

## Tests simplify with the code

Keep the test suite behavior-oriented. Do not delete existing tests merely to make simplification easier. Rewrite brittle implementation-detail assertions when necessary, and add a focused regression when cleanup exposes a real failure class.

Add targeted coverage for a public contract or high-risk safety invariant when needed; otherwise rely on the core/release contracts and exact-RPM smoke.

## After each meaningful batch

- run direct tests for the changed owner;
- run the release-critical gate if package bytes changed;
- review the advisory report once;
- build an exact RPM only when the batch is worth device comparison;
- repeat only the affected core device checks.

## Exit condition

Stop when further cleanup would introduce more abstraction than it removes.

A good simplification release should be describable as:

> same supported appliance behavior, fewer owners, fewer scripts, fewer states, smaller failure surface.

After that point, further cleanup needs a concrete product/reliability reason; otherwise return engineering effort to the office-intelligence roadmap.
