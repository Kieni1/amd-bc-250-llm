# Development memory (Git-only)

This tree preserves engineering context that is valuable for future development but is
not part of the installed appliance interface. It is intentionally **not installed by
the binary RPM**. Source archives/source RPMs may still contain it because it belongs to
the reviewed repository state.

Keep current operator truth in `README.md`, `MODELS.md` and `docs/`. Keep detailed
negative results, experiment bookkeeping, validation state and the reasons behind easy-
to-reverse decisions here. Do not force operators to read development archaeology to
use the appliance.

## Current development references

- `DECISIONS.md` — durable easy-to-reverse engineering decisions; append/supersede
  rather than deleting rationale.
- `model-runs/` — compact records for consequential model experiments/comparisons.
- `VALIDATION-MATRIX.md` — which evidence class exists for each subsystem and what is
  still pending.
- `TESTING-STRATEGY.md` — shared promotion funnel and lane-specific qualification order.
- `handovers/` — durable main/workflow/operations handovers plus the temporary
  specialist-chat template.
- `SOURCE-REFRESH-0.11.1-0.6.md` — source-only coordination refresh note; no RPM metadata
  or installed payload change.

Every consequential model/behavior record should separate **observed facts**,
**interpretation** and **decision**. Include exact package release, exact model ID,
settings, tests actually run, evidence filename/SHA-256 when available, and an explicit
**Retest only if** field. That field prevents repeating an experiment simply because a
later chat or shorter operator document no longer contains the original caveat.

## Review implementation discipline

When a review has already established defects and scope, implement it rather than
re-arguing the audit in the release response. The final implementation report should
state what changed, which recommendations were deliberately deferred, validation
actually run/not run, and residual risk.

Prefer regression tests that exercise observable behavior over tests that merely assert
a particular source-code string exists. Keep documentation tests small and tied to
durable package contracts; add a new documentation assertion only when a demonstrated
drift class justifies maintaining it.

## Handover discipline

Do not maintain many parallel full project handovers. Keep the long main integration
handover because hardware/software constraints and proven negative results are easy to
lose. Keep workflow rules separate and versionless. Keep one current operations handover
for hardware work. Generate temporary specialist chats from current source and
`SPECIALIST-TESTING-HANDOVER.md` when a lane becomes active.
