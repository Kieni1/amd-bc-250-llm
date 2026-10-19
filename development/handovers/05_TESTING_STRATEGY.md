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
651/651 source tests PASS using isolated module execution
22/22 release-preflight tests PASS
126/126 package-critical tests PASS across 8 modules, including unprivileged execution
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

Source PASS is not device PASS. The selected `0.14.1-1.2` RPM must be bound by exact filename/SHA-256 and selected GitHub run identity before device testing.

Start with `03_CORE_FUNCTIONALITY_CHECK.md`. Use the resilience/recovery/security playbook only when the changed area or observed defect justifies it.
