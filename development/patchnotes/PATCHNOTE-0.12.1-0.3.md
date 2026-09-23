# BC-250 0.12.1-0.3 development patch note

## Scope

This release keeps the 0.12.1 model/runtime policy unchanged and focuses on operator UX,
readiness clarity, and trustworthy diagnostic evidence. It does not reopen the accepted RAG,
translation, MTP, topology, Tika, CU, Deep-Reasoning residency, or Open WebUI ACL decisions.

## Changes

- The guided installer no longer prints the full optional Ollama catalogue on a converged run.
  Required role models are reconciled first, then the operator chooses whether to review/install
  additional models. Explicit noninteractive `BC250_MODEL_SELECTION` still applies directly.
- `bc250-status` obtains the Ollama server version from the active lane's `/api/version` endpoint
  and reports Open WebUI HTTP readiness separately from systemd activity.
- `bc250-verify` keeps the same pass/fail/skip semantics but states when successful completion
  includes skipped optional/authenticated coverage.
- `bc250-revalidate` is harness v4.3. Result bundles include `manifest.json` and
  `SHA256SUMS.txt`, expected inactive-agent raw systemd RCs are annotated, accepted context
  truncation is described as policy-aware diagnostic behavior, and PASS/status output includes
  the count of diagnostics when present.
- New `bc250-support-bundle` creates a root-only, mode-0600 redacted evidence archive by reusing
  existing status/verifier/topology/CU/maintenance authorities. It intentionally excludes tokens,
  prompts/chats, uploaded document contents, Open WebUI database rows, identity SQL and backups.

## Intentionally deferred

- ordinary-user multi-model/compare policy changes until the dedicated hardware safety round;
- backup-contract expansion/verify-only until completeness is reviewed against current product data;
- generalized memory admission/backpressure;
- RAG lifecycle/index repair tooling;
- broad security-hardening changes without a demonstrated exposure gap.

## Testing handoff

The testing specialist should focus on changed boundaries rather than replaying closed campaigns:

1. converged and explicit-selection installer UX;
2. `bc250-status` Ollama version and Open WebUI active-vs-ready reporting;
3. verifier skipped-check completion wording;
4. revalidation v4.3 bundle manifest/checksum validity, diagnostic headline, and expected agent RC annotation;
5. support-bundle redaction/integrity and evidence usefulness;
6. ordinary-user multi-model/compare safety as a separate policy-discovery round (no package policy change yet).

GitHub/Fedora remains authoritative for complete validation and RPM/SRPM construction; BC-250
owns exact installed runtime/product qualification.
