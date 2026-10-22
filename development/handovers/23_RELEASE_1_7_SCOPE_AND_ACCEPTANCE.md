# Release 0.14.1-1.7 — scope and acceptance

## Scope

Release `0.14.1-1.7` is a managed-RAG correctness, robustness and operator-UX update on the 1.6 runtime-maintenance source baseline.

Included:

- all-or-nothing managed-RAG activation using a validated projected final corpus;
- duplicate same-family/language replacement rejection and filesystem rollback on activation failure;
- German as the sole managed authoritative language for now; French translations reference an exact German revision ID;
- stable logical `document_id` plus source-derived `revision_id` for new drafts, with bounded legacy filename-link compatibility;
- truthful nonzero failure status for incomplete preparation and topology-restoration failure;
- working-draft overwrite protection;
- real date validation, metadata escaping/round-trip safety, inbox/working/source symlink rejection and stronger Open WebUI sync-response validation;
- persisted extraction-fidelity state with explicit acknowledgement before a `review` result can become active;
- clearer `bc250 rag review` provenance/currentness/fidelity display and `bc250 rag status` lifecycle-health summary;
- current documentation/qualification wording aligned with Open WebUI 0.12.3, Tika 4.1.0-full and the proven Advanced 6144 path.

Unchanged:

- Fedora 44 target;
- Ollama `0.40.8`;
- Open WebUI `0.12.3`;
- Tika `4.1.0-full`;
- governor `0.4.14`;
- stock Fedora AMDGPU/Mesa/Vulkan architecture;
- main/task/embedding/exclusive-agent lane topology and runtime tuning;
- production/recommended model identities;
- Open WebUI RAG chunking/retrieval/context/model policy;
- SRPM-first single-authoritative-rebuild release chain.

## Managed document policy

The managed curated corpus is intentionally narrow for this release:

```text
German PDF source -> authoritative reviewed Markdown
French PDF source -> translation reviewed Markdown -> exact German revision_id
```

Managed preparation remains PDF-only. DOCX and other supported office formats may still use the existing Open WebUI/Tika ad-hoc extraction path; adding DOCX to the curated lifecycle is future adapter work, not part of 1.7.

The package-managed active corpus remains authoritative. Open WebUI Knowledge is a synchronized projection and must never become the source of truth for local lifecycle state.

## SOURCE acceptance

Before GitHub authority:

- release identity and current guidance agree on `0.14.1-1.7`;
- focused RAG regression/failure-injection tests pass;
- full source suite is run and deterministic findings are classified;
- release preflight and package-critical source checks pass;
- Ruff and ShellCheck pass when available in the source environment;
- Python compile, shell syntax and JSON parsing checks pass;
- no generated `__pycache__`/`.pyc` or build output is included in the frozen source ZIP.

RPM construction, frozen-SRPM rebuild, payload validation and configured rpmlint remain BUILD evidence and belong to the authoritative Fedora 44 GitHub release gate.

Current 1.7 source evidence:

```text
full source suite:       678/678 PASS across 24 modules
release preflight:       26/26 PASS
package-critical source: 144/144 PASS across 8 modules
```

Ruff and ShellCheck were not available in the source-review environment, so they remain mandatory Fedora 44 authority checks rather than claimed local evidence.

## Exact selected 1.7 RPM acceptance

1. bind the selected workflow-dispatch run, source commit, RPM/SRPM/evidence hashes before device mutation;
2. verify normal status/health/verify, 40/40 persistence and ordinary service/reboot convergence;
3. recheck Ollama 0.40.8 normal lanes, representative Vulkan generation, registration/restart stability and representative `/api/show` renderer/parser/template-source evidence;
4. verify governor 0.4.14 service health, packaged 350–1850 MHz range, temperature reporting and bounded load response without retuning;
5. create a disposable managed-RAG collection and prove one valid German revision plus an exact-linked French translation;
6. prove an invalid replacement and an ambiguous duplicate `--all-ready` set leave the active corpus unchanged;
7. prove a valid replacement supersedes the prior revision while preserving audit evidence;
8. verify review/status UX exposes provenance/currentness/fidelity/lifecycle health coherently;
9. sync the active corpus to Open WebUI, then obtain one grounded answer with expected provenance/citation and one unsupported answer that does not fabricate a document fact;
10. confirm the resulting RAG state and ordinary-user Open WebUI path survive the required reboot boundary.

Prior device evidence is regression baseline only and cannot be transferred to changed 1.7 bytes.
