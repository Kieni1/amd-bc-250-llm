# Testing strategy

## Principle

Testing should make wrong releases harder without making the test system the dominant architecture.

The project is pre-v1.0 and moving quickly. Keep the existing regression suite. Do not delete tests merely to make fast-moving development quieter. When implementation is simplified, fix brittle fixtures or rewrite assertions around supported behavior rather than deleting tests merely to reduce noise.

## Current split

```text
release preflight      release-pipeline/source-authority contracts
RPM %check             bounded package-critical module list from release-contract.json
full source quality    every tests/test_*.py module, run in isolation
exact-RPM device       small core-functionality smoke first; deeper playbooks only when risk warrants
```

The hard candidate path covers Ruff/ShellCheck, current guidance/scope, core packaging/source/provenance/upstream-patch/runtime contracts and configured rpmlint. The broad behavioral suite remains advisory in GitHub so a noncritical long-running test cannot prevent RPM/SRPM evidence from being produced.

## Current cleaned-source snapshot

```text
24 source test modules
678/678 source tests PASS using isolated module execution
26/26 release-preflight tests PASS
144/144 package-critical source tests PASS across 8 modules; authoritative unprivileged RPM `%check` remains BUILD evidence
```

Keep these as checkpoint evidence, not as a target test count. Tests may be added as supported behavior grows or new failure classes are discovered.

## Test design rules

- Preserve existing behavior coverage unless the behavior itself is deliberately removed.
- Add focused regressions for newly discovered failure classes.
- Prefer observable behavior over source-string implementation details.
- Use temporary state instead of real `/run`, `/var` or user data unless that state is explicitly under test.
- Do not depend on the developer running as root.
- Isolate inherited environment variables in subprocess fixtures.
- Run modules separately so one mock, timeout or environment mutation cannot contaminate later modules.
- Do not weaken production root/safety checks merely to satisfy a unit test; stub the boundary in the test harness.
- Do not treat an empty/partial coverage set as PASS.

## Advisory failure classification

```text
FIX-NOW        current product/release regression
DEFER          real issue outside current objective
REMOVE-WITH-FEATURE  obsolete behavior and its test are deliberately removed together
HARNESS        fixture/environment/tooling failure
INFO           useful evidence only
```

Do not serially patch product code just to drive advisory output to zero.

## Exact-artifact testing

Source PASS is not device PASS. The selected `0.14.1-1.7` RPM must be bound by exact filename/SHA-256 and selected GitHub run identity before device testing.

Start with `03_CORE_FUNCTIONALITY_CHECK.md` and the dedicated `18_TESTING_SIDECHAT_HANDOVER.md`. Use the resilience/recovery/security playbook only when the changed area or observed defect justifies it.

## Layer model

The current split can also be understood as three evidence layers.

### Layer 1 — hard release-critical tests

These are small, deterministic checks that protect release artifact invariants and predictable package failures.

Examples include:

- expected package/release identity and current release contract;
- required core files and public CLI shape;
- source/provenance correctness;
- frozen Source0/spec consistency;
- the authoritative SRPM-first rebuild/publish chain;
- binary payload contract;
- package-critical `%check` modules;
- blocking Ruff/ShellCheck before freeze/build;
- configured blocking rpmlint after RPM construction.

A check that primarily exercises broad product quality, requires special device state, or exists only to police a transient development convention should not be promoted into this layer without an artifact-integrity reason.

### Layer 2 — advisory source/product quality

The complete module-isolated source suite remains useful evidence for behavioral regressions, stale assumptions and product-quality findings. It is advisory as a release-automation layer, not disposable.

A deterministic finding that exposes a real current release blocker is still a blocker because of what it proves, not because of which job produced it.

Broad quality findings should be reviewed together and classified rather than triggering serial speculative code changes.

### Layer 3 — exact-artifact device tests

Device tests validate the exact selected GitHub RPM, not the source tree in the abstract and not a locally rebuilt approximation.

For `0.14.1-1.7`, use the bounded core smoke plus the carried runtime and changed managed-RAG checks in `18_TESTING_SIDECHAT_HANDOVER.md` and `23_RELEASE_1_7_SCOPE_AND_ACCEPTANCE.md`. Deeper resilience, security or recovery work remains available when a changed area or observed risk justifies it; it is not a mandatory ritual for every package bump.

## Test result taxonomy

A useful harness or sidechat distinguishes:

```text
PASS
FAIL
SKIPPED
INCOMPLETE
HARNESS_ERROR
REVIEW
```

An injected failure, wrapper timeout, unavailable optional fixture or insufficient safe device headroom is not automatically a product FAIL. Preserve enough evidence to classify the responsible layer.

For integration handback, map those raw outcomes into the project evidence classifications where appropriate:

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

## Timeout rule

A wrapper timeout is evidence about the wrapper until proven otherwise.

For deterministic source tests:

1. identify the affected module or bounded group;
2. run it directly or module-isolated;
3. preserve the real assertion/result;
4. do not call the package failed merely because one giant aggregate invocation exceeded an external execution window.

For device/harness work:

1. preserve partial stdout/stderr/request/response and return code;
2. capture relevant device/service state;
3. determine whether the product stopped making progress or the harness stopped waiting;
4. classify product vs harness/environment before changing package code.

## When to add a new test

Add a test when at least one is true:

- a public contract regressed;
- an artifact-integrity invariant needs protection;
- a security/privacy/data-loss boundary needs deterministic proof;
- a subtle semantic rule has previously produced a false PASS/FAIL;
- an upstream runtime migration changed a supported boundary;
- the test will survive the next implementation simplification.

Prefer one strong behavioral invariant over several overlapping source-string assertions.

If a test exists only to police an implementation structure that is deliberately being removed, remove or rewrite the test together with that structure; do not preserve dead architecture through the test suite.
