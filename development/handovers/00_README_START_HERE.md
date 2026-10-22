# BC-250 handover bundle — current release line 0.14.1-1.7

## Purpose

This bundle is the current engineering handover for the stock-first BC-250 LLM appliance.

Current source/release identity:

```text
package:  bc250-llm-server
version:  0.14.1
release:  1.7
NEVRA:    bc250-llm-server-0.14.1-1.7.fc44.x86_64
```

Use normal RPM identity from here forward. Engineering iteration labels belong in commits, issues and handovers, not in Version/Release.

## Current position

The reconstruction era is closed. Release 1.7 is a RAG correctness/robustness increment on the 1.6 runtime-maintenance source baseline. Runtime/model/retrieval tuning remains unchanged.

1. preserve the successful 1.4 Fedora 44 SRPM-first build evidence and exact-RPM Blocks 1-3 device evidence as **baseline/history**, not transferable PASS status;
2. build/select the exact `0.14.1-1.7` GitHub Fedora 44 artifact and bind all further acceptance to its hashes;
3. recheck the carried 1.6 runtime surfaces: Ollama 0.40.8 Vulkan/lane/registration behavior and `/api/show` renderer/parser/template-source metadata plus governor 0.4.14 service/thermal/power behavior;
4. prove the changed 1.7 managed-RAG surfaces: all-or-nothing activation/rollback, duplicate-target rejection, DE-authority/FR-translation revision provenance, source/fidelity validation, truthful failure exits, review/status UX and Open WebUI synchronization;
5. complete reboot-persistence / ordinary-user Open WebUI grounding/abstention on the exact new bytes while keeping the stock-core architecture and SRPM-first release authority unchanged.

The selected 1.7 device candidate must be identified by exact RPM SHA-256. Prior source/device evidence does not substitute for acceptance of changed 1.7 package/RAG bytes.

## Product direction

The product is a boring, stock-first appliance. The main package should rely on normal Fedora/kernel/userspace behavior wherever practical. Experimental kernel/Mesa/GFX work is historical engineering evidence, not current architecture.

Greenfield means implementation freedom, not data loss or contract amnesia: preserve supported user behavior, package data, public CLI semantics and recovery guarantees; delete obsolete internal structure freely.

## Current validation snapshot

```text
full source suite:       678/678 PASS across 24 modules
release preflight:       26/26 PASS
package-critical source: 144/144 PASS across 8 modules; authoritative unprivileged RPM `%check` pending
device acceptance:       PENDING exact selected 1.7 RPM; prior exact-device results are regression baseline only
```

These counts describe the current cleaned-source snapshot; they are evidence, not permanent architecture.

## Inherited 1.4 GitHub build evidence; 1.7 build pending

The SRPM-first architecture was exercised successfully by the 1.4 GitHub authority run and remains authoritative for 1.7. The 1.7 selected GitHub build is still pending. The observed authority-path timing was:

```text
total job:    5m58s
release gate: 4m29s
Rust compile: 2m49s once
```

The comparable 1.3-era successful run was 8m45s total with a 7m31s release gate and two governor/Rust compilations of roughly 2m31s and 2m33s. The 1.4 change therefore removed the duplicate authoritative compilation and reduced the observed total job by about 32% and the release gate by about 40%, while retaining frozen Source0/spec verification, `%check`, isolated SRPM rebuild, payload validation, blocking rpmlint, hashes and release evidence.

The successful build reported payload validation PASS and rpmlint with zero errors. The exact selected GitHub run ID and artifact hashes are not embedded in this standalone handover bundle; the testing sidechat must record them before device mutation.

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
18. `18_TESTING_SIDECHAT_HANDOVER.md`
19. `19_BUILD_TIME_OPTIMIZATION_AND_TIMING.md`
20. `20_DEVICE_QUALIFICATION_1_4.md`
21. `21_RELEASE_1_5_SCOPE_AND_ACCEPTANCE.md`
22. `22_RELEASE_1_6_SCOPE_AND_ACCEPTANCE.md`
23. `23_RELEASE_1_7_SCOPE_AND_ACCEPTANCE.md`

The final specialist/evidence files preserve high-value engineering discipline while the product-goal and release-gate files define the current roadmap and acceptance method.

`archive/` is rationale/history only and cannot override current files.
