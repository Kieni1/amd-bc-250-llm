# Development memory (Git-only)

`development/` contains maintainer guidance, historical evidence and engineering decisions. It is deliberately absent from the installed RPM payload and is **not** an independent source of runtime/release truth.

## Current authorities

Use:

- `release-contract.json` + the RPM spec for release/build identity and authority;
- `config/runtime.env` + `packaging/upstreams.toml` for pinned runtime/upstream identity;
- `WORKBENCH-STATE.json` for the current release evidence state and next gate;
- `TESTING-STRATEGY.md` and `VALIDATION-MATRIX.md` for current test/evidence expectations;
- `DEVELOPMENT-SCOPE.json` + `scope.py` for development ownership/freeze hints;
- `DECISIONS.md` for durable engineering decisions;
- `OWNERSHIP.md` for the concise repository ownership map.

## Handovers and history

`handovers/`, `model-runs/`, `patchnotes/`, `references/` and `SOURCE-REFRESH-*` preserve useful engineering history. They may explain why a decision was made, but they do not need to be rewritten for every RPM release and cannot override the current authorities above.

The handover bundle remains intentionally readable in-tree because it records development reasoning that has repeatedly been useful. Sidechat prompt generation is not part of the repository contract; chat handoff prompts are handled outside the package source.

Do not turn historical evidence into a release prerequisite without a current product reason.

## Pre-v1 cleanup rule

Prefer deleting obsolete implementation, wrappers and duplicated state before adding abstraction. Greenfield software interfaces aggressively, while preserving valuable user state, release provenance and rollback/security boundaries. If a behavior is deliberately removed, remove its tests/docs/package references in the same change and add an absence regression where recurrence would be risky.
