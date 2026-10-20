# BC-250 handover bundle — current release line 0.14.1-1.2

## Purpose

This bundle is the current engineering handover for the stock-first BC-250 LLM appliance.

Current source/release identity:

```text
package:  bc250-llm-server
version:  0.14.1
release:  1.3
NEVRA:    bc250-llm-server-0.14.1-1.3.fc44.x86_64
```

Use normal RPM identity from here forward. Engineering iteration labels belong in commits, issues and handovers, not in Version/Release.

## Current position

The reconstruction era is closed. The active work is simpler:

1. produce and select the authoritative Fedora 44 GitHub build for `0.14.1-1.3`;
2. run a deliberately small exact-RPM core-functionality check;
3. freeze that result as the known-good stock-core baseline if it passes;
4. shift directly to office RAG/document quality, German–French translation UX and polished local-assistant workflows; perform bounded simplification only opportunistically where it removes concrete obsolete ownership/risk;
5. keep supported product behavior stable while reducing implementation surface.

The selected device candidate must be identified by exact RPM SHA-256. Source tests or an earlier package do not substitute for exact-artifact evidence.

## Product direction

The product is a boring, stock-first appliance. The main package should rely on normal Fedora/kernel/userspace behavior wherever practical. Experimental kernel/Mesa/GFX work is historical engineering evidence, not current architecture.

Greenfield means implementation freedom, not data loss or contract amnesia: preserve supported user behavior, package data, public CLI semantics and recovery guarantees; delete obsolete internal structure freely.

## Current validation snapshot

```text
full source suite:       653/653 PASS across 24 modules
release preflight:       22/22 PASS
RPM package-critical:    127/127 PASS across 8 modules (verified unprivileged)
device acceptance:       pending exact selected 0.14.1-1.3 RPM
```

These counts describe the current cleaned-source snapshot; they are evidence, not permanent architecture.

## Current test philosophy

The repository retains the existing broad pre-v1.0 source test suite. Do not delete tests merely to make fast-moving development quieter. The release path keeps the broad behavioral suite advisory, but Ruff/ShellCheck, current guidance/scope, the bounded package-critical set and configured rpmlint are blocking release-candidate gates so predictable failures are caught before handoff.

Current policy:

- keep all existing behavior coverage unless the protected behavior itself is deliberately removed;
- add targeted regressions for newly discovered failure classes;
- run package-critical contracts in RPM `%check`;
- require Ruff/ShellCheck and configured rpmlint to pass; run the complete source suite as additional advisory quality evidence;
- simplify brittle test harness mechanics rather than weakening the behavior contract.

## Read order

Read these first:

1. `01_CURRENT_STATE_AND_NEXT_WORK.md`
2. `02_MAIN_CHAT_WORKING_RULES.md`
3. `03_CORE_FUNCTIONALITY_CHECK.md`
4. `04_RELEASE_BUILD_AND_VALIDATION.md`
5. `05_TESTING_STRATEGY.md`
6. `06_RUNTIME_AND_MODELS.md`
7. `07_OPERATIONS_AND_PACKAGE_BOUNDARY.md`
8. `08_GREENFIELD_SIMPLIFICATION_PLAN.md`
9. `09_RELEASE_QUALITY_GATE.md`
10. `10_WORKING_METHOD_AND_EVIDENCE.md`
11. `11_LONG_TERM_ENGINEERING_GUIDELINES.md`
12. `12_ENGINEERING_AND_TEST_HARNESS_RULES.md`
13. `13_RESILIENCE_RECOVERY_AND_SECURITY_PLAYBOOK.md`
14. `14_EVALUATOR_AND_RESULT_SEMANTICS.md`
15. `15_SPECIALIST_WORK_AND_RETURN_CONTRACT.md`
16. `16_PRODUCT_GOAL_AND_ROADMAP.md`
17. `17_RELEASE_CANDIDATE_EXECUTION_GATE.md`

The final specialist/evidence files preserve high-value engineering discipline while the product-goal and release-gate files define the current roadmap and acceptance method.

`archive/` is rationale/history only and cannot override current files.
