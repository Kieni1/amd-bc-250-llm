# BC-250 current work / next-build handover — 0.13.1-1.0

## Identity

```text
VERSION       0.13.1
RPM Release   1.0
NVR target    bc250-llm-server-0.13.1-1.0
```

## Qualified predecessor

Exact-device `bc250-llm-server-0.12.2-0.8.fc44.x86_64` is the functional baseline.
It passed upgrade/convergence, `bc250 verify` 53/0/0/0, 40/40 live CU with exact saved-profile boot restore,
Open WebUI desired state, revalidation infrastructure/restoration, direct and OWUI RAG, ordinary-user ACL/product
journeys, multi-turn/task and Advanced/Deep qualification. Agent remained correctly optional/PARTIAL.

The only package-layout REVIEW was runtime Python bytecode written under package-owned `/usr`.
The pre-release investigation then reproduced and attributed that behavior, qualified optional-model state transitions,
and proved that retired native Qwen3.6 residue was hidden from ordinary users but incorrectly affected Open WebUI
desired-state accounting.

## 0.13.1-1.0 implementation delta

This release intentionally keeps architecture and runtime/model pins unchanged.

Implemented changes:

1. Canonical `bc250` exports `PYTHONDONTWRITEBYTECODE=1` before dispatching helpers.
2. Guided install/upgrade convergence removes stale `__pycache__`, `*.pyc` and `*.pyo` only below the package-owned
   `/usr/libexec/bc250-llm-server` and `/usr/share/bc250-llm-server` trees.
3. Intentionally unselected optional models report `OPTIONAL — not installed` or
   `OPTIONAL — source cached, not registered` instead of `MISSING`/false `DRIFT`.
4. Optional unselected models receive no `apply`/`refresh` recommendation.
5. A selected optional model with a runtime Modelfile but missing/inconsistent registration remains genuine `DRIFT`.
6. Retired/non-user-visible testing policies are excluded from active Open WebUI base-override desired state.
   Native retired residue remains lifecycle evidence and is cleaned with `sudo bc250 model purge-retired --yes`.

## Closed decisions preserved

Do not reopen without a new dependency:

- model selection;
- RAG model tournament;
- structured-output discovery;
- Agent installation/qualification as a baseline requirement;
- MTP/OCR campaigns;
- CU architecture or replacement-AMDGPU backend;
- broad dependency debloat.

Dependencies remain evidence-backed. In particular `umr`, Mesa/Vulkan, `vulkan-tools`, Poppler,
`python3-huggingface-hub` and `git-core` stay in the base package for the current product/verification contract.

## Required exact-package delta qualification

After building the exact `0.13.1-1.0` RPM:

1. Start from exact 0.12.2-0.8 with deliberately created known package-tree Python bytecode.
2. DNF upgrade to exact 0.13.1-1.0.
3. Run `sudo bc250 install` convergence.
4. Prove stale bytecode is removed.
5. Exercise `bc250 rag --help`, `bc250 benchmark translation --help`, model status, Open WebUI setup/status,
   `bc250 verify` and `llm-run-diagnose --no-load`.
6. Require `rpm -V` clean, zero unowned files below package-owned `/usr`, and no new `*.pyc`/`__pycache__`.
7. Verify optional absent/cached/applied/broken states have the new semantics.
8. Create a zero-copy retired Qwen3.6 native registration and prove Open WebUI desired-state status remains clean,
   ordinary-user visibility remains false, and `purge-retired` removes the residue.
9. Run `bc250 verify`; require the established 53/0/0/0 baseline unless a platform-only diagnostic changed.
10. Restore exact normal topology/state.

A full 0.8 release campaign is not required unless this bounded delta exposes a regression.
