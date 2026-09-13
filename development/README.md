# Development memory (Git-only)

This tree preserves engineering context that is valuable for future development but is
not part of the installed appliance interface. It is intentionally **not installed by
the binary RPM**. Source archives/source RPMs may still contain it because it belongs to
the reviewed repository state.

Keep current operator truth in `README.md`, `MODELS.md` and `docs/`. Keep detailed
negative results, experiment bookkeeping and the reasons behind easy-to-reverse
decisions here. Do not force operators to read development archaeology to use the
appliance.

- `DECISIONS.md` — durable decisions whose rationale must survive documentation
  cleanup; append or mark entries superseded rather than deleting them.
- `model-runs/` — compact records for consequential model experiments and comparisons.

Every consequential record should separate **observed facts**, **interpretation** and
**decision**. Include exact package release, exact model ID, settings, tests actually
run, evidence filename/SHA-256 when available, and an explicit **Retest only if** field.
That last field is the guardrail against repeating an experiment simply because a later
chat or shorter operator document no longer contains the original caveat.

## Review implementation discipline

When a review has already established the defects and scope, implement it rather than
re-arguing the audit in the release response. The final implementation report should
state only what changed, which recommendations were deliberately deferred, validation
actually run/not run, and any residual risk.

Prefer regression tests that exercise observable behavior over tests that merely assert
that a particular source-code string exists. Keep documentation tests small and tied to
durable package contracts; add a new documentation assertion only when a demonstrated
drift class justifies maintaining it.

