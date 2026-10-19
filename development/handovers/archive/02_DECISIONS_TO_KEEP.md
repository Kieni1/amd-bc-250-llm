# Historical decisions worth retaining

- Technical success does not require retaining a high-maintenance architecture.
- Source, build and device evidence are different authority levels.
- Exact artifact identity matters at release/device boundaries.
- Never publish modified bytes under an already-used RPM NVR.
- Operator-added model registrations are supported state; exact total registration count is not a package invariant.
- Security exposure claims require the right vantage point.
- Destructive operations fail closed when current state cannot be established safely.
- Raw evidence should survive evaluator/parser mistakes.
- Thinking-only output is not visible-response determinism evidence.
- Model-install cancel/no-selection is no-mutation behavior.
- GitHub/Fedora is primary release-build authority; local build is reproduction/debugging.
- Broad quality checks should not automatically become hard release blockers.
- Periodic greenfield simplification is deliberate maintenance.
