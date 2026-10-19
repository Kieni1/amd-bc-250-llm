# Development memory (Git-only)

`development/` contains engineering guidance and evidence that is useful to maintainers but is not part of the installed appliance interface.

## Current authority

Use:

- `TESTING-STRATEGY.md` — current source/package/device test split;
- `VALIDATION-MATRIX.md` — current release evidence state;
- `DEVELOPMENT-SCOPE.json` + `scope.py` — development ownership/freeze hints;
- `DECISIONS.md` — durable engineering decisions;
- `handovers/` — current `0.14.1-1.2` integration, release, testing and product-roadmap guidance.

The active handover entry point is `handovers/00_README_START_HERE.md`.

## Historical material

`model-runs/`, `patchnotes/`, `references/`, `SOURCE-REFRESH-*` and `handovers/archive/` are historical evidence. They may explain why a decision was made, but they cannot override current release/runtime/operator guidance.

Do not turn historical evidence into a release prerequisite without a current product reason.

## Pre-v1.0 cleanup rule

Prefer deleting obsolete implementation, wrappers and duplicated state before adding new abstraction. Preserve supported behavior, public CLI/package contracts, data/recovery safety and useful regression coverage. If a behavior is deliberately removed, remove its tests/docs/owners in the same change.
