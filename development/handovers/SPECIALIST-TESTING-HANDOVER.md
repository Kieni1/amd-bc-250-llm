# Specialist testing coordination — clean-core reconstruction

## 1. Purpose

Sidechats/specialist passes should answer narrow questions without redefining main scope.

Current specialist lane is clean-core reconstruction and selective donor review, not GFX qualification.

## 2. Typical assignments

Useful sidechat tasks include:

- inventory GFX-owned surfaces in one subsystem;
- review whether a helper is generic or GFX-coupled;
- compare one 1.9 component with its 2.2 donor equivalent;
- test package/install removal behavior;
- audit docs for stale current GFX instructions;
- inspect model/benchmark semantics;
- verify no-mutation/return-code behavior;
- review a focused source diff for unintended coupling.

## 3. Required identity

Every return should state:

- source baseline/commit/archive;
- exact files or commands tested;
- whether the result is source-level or device-level;
- any assumptions.

## 4. Finding format

For each material item:

```text
Observed
Interpretation
Classification: KEEP / DROP / REWORK / DEFECT / EVIDENCE GAP
Required action
Evidence
```

End with one recommended main-chat action.

## 5. No scope expansion

A specialist must not reintroduce GFX into the core, bump runtimes, redesign product UX or change release identity unless that is the explicit assignment.

## 6. Safety

Do not manufacture dangerous boot/system states for a core-removal review. Prefer deterministic fixtures for negative paths.

## 7. Handback rule

The main chat reconciles every accepted specialist finding into code/tests/docs/ledger. Sidechat output is evidence, not automatic authority over the canonical tree.
