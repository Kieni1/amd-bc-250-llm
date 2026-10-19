# Quality lessons retained from older handovers

The older resilience/testing bundle was intentionally larger and contained several useful disciplines. The current bundle does not retain its numbered campaigns, exact old package identities or reference harness scripts, but keeps these lessons:

- separate orchestration, evidence collection, interpretation and reporting;
- preserve raw evidence and classify harness errors distinctly from product defects;
- avoid shell subshell/state and environment-variable traps;
- use fail-closed gates before destructive actions;
- require rollback material and staged validation for recovery operations;
- verify cleanup/restoration;
- use external vantage for external network/security claims;
- preserve operator-added state instead of manufacturing pristine baselines;
- use property/idempotency tests instead of exhaustive state matrices;
- use semantic positive/negative controls for evaluators;
- write long-running evidence incrementally;
- do not let missing coverage or empty result sets become accidental PASS.

These are durable engineering rules. The old heavyweight campaign machinery is not.
