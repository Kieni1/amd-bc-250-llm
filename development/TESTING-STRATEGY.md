# BC-250 testing strategy

## Current objective

This is durable test policy; exact current NVR/evidence lives in `VALIDATION-MATRIX.md` and
`WORKBENCH-STATE.json`, so an ordinary RPM release does not require rewriting this document.

Testing has three jobs:

1. keep source and packaging regressions visible while pre-v1.0 development moves quickly;
2. prevent release-critical artifact defects from reaching an RPM candidate;
3. validate the exact selected RPM on a BC-250 with a deliberately small core-functionality check.

Do not revive the old reconstruction milestone ladder or historical GFX qualification campaign.

## Test layers

### Release-critical preflight

Hard blockers should remain small, deterministic and host-safe. They protect:

- current release identity and release contract;
- tracked-source / frozen Source0 rules;
- GitHub-primary release authority;
- source/provenance requirements;
- clean-core absence;
- release-pipeline contracts.

Run:

```bash
scripts/validate.sh --preflight
```

### RPM `%check`

`release-contract.json` owns the package-critical module list. The current hard set covers:

- core CLI/config contracts;
- packaging/payload/source invariants;
- pinned source/provenance handling;
- upstream patch validation;
- runtime configuration contracts.

Run:

```bash
scripts/validate.sh --package
```

These tests must run as an unprivileged RPM builder. Fixtures must not depend on writable `/run`, `/var`, root-owned state or inherited Make helper variables unless that boundary is explicitly under test.

### Full repository suite

Keep every existing `tests/test_*.py` module unless the protected behavior itself is deliberately removed. Do not delete tests merely to make fast-moving development quieter. Run modules in isolation so mocks/environment changes do not leak between modules and one slow module is identifiable.

```bash
scripts/validate.sh
```

The full suite is advisory in the GitHub RPM workflow: failures are evidence to classify and fix, but they do not prevent production of RPM/SRPM evidence unless they expose a release-critical defect.

When a test becomes brittle during greenfield cleanup:

1. determine whether the protected behavior is still supported;
2. if yes, fix the fixture/isolation or rewrite the test around observable behavior;
3. if no, remove the behavior and test together in the same deliberate change;
4. do not delete a test solely because implementation is changing quickly.

## Lint and static quality

`make lint` checks source-owned files only. Generated build trees, downloaded/vendored sources, caches and historical quality recipes are outside the lint surface.

Ruff/ShellCheck are blocking release-candidate checks and run before Source0 freeze/build. Configured rpmlint is blocking after RPM construction. The broad behavioral suite remains advisory in GitHub unless a finding is promoted to a release-critical defect.

## Device ownership

Source tests do not substitute for exact-RPM device evidence.

For a structural cleanup release, compare against the most recent accepted RPM and keep the
device regression deliberately bounded:

- exact RPM install/upgrade and `rpm -V`;
- `bc250 install` convergence plus `version`, `status`, `health`, and `verify`;
- 40-CU routing/persistence and governor health;
- normal Ollama topology and one representative generation;
- Open WebUI login;
- managed-document lifecycle smoke plus one grounded query;
- German/French translation smoke;
- one representative Advanced/Deep query;
- reboot, persistence checks, and final status/health/verify;
- absence of intentionally removed public command aliases.

The question is whether structural simplification changed supported observable behavior. Deeper
product campaigns belong to releases that actually change those product surfaces.

## Deeper tests are risk-driven

Use the resilience/recovery/security playbook when a change touches lifecycle, destructive operations, recovery, credentials, network exposure or persistence. Use benchmark/evaluator-specific checks when model/quality behavior changes. Do not run broad campaigns by default merely because they existed historically.

## Evidence discipline

For meaningful device or release work record:

```text
source commit
selected GitHub run
RPM/SRPM filenames and SHA-256
installed NEVRA
kernel/device identity when relevant
exact commands
observed result
classification (PASS / FAIL / INCOMPLETE / HARNESS_ERROR / REVIEW)
cleanup/restoration result for stateful tests
```

A wrapper timeout, missing optional fixture, root-permission mismatch or stale expectation is a harness/environment problem until product failure is demonstrated.
