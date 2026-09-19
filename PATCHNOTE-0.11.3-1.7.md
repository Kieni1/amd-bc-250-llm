# Patch note — bc250-llm-server 0.11.3-1.7

Expected NVR: `bc250-llm-server-0.11.3-1.7`

## Scope

This is a focused operator-boundary and UX hardening release on top of 0.11.3-1.6. It does **not**
change production model roles, MTP defaults, Ollama lane topology, Open WebUI desired state, GPU/CU
policy, hard memory thresholds or the maintenance safe-power decision policy. Broad MTP work remains
closed; support/maintenance hardware qualification remains the next active device lane.

## Fixes

- `bc250-status` no longer derives appliance mode from agent-unit inactivity alone. It reuses the
  existing `bc250-agent-mode status` classifier and reports `normal`, `degraded`, `stopped` or
  exclusive `agent` state. This removes a false-normal summary when normal Ollama lanes are down.
- Explicit credential files now fail closed consistently. `bc250-rag-import --token-file` and
  `bc250-model ... --token-file` require a regular, non-empty file with no group/world permission
  bits (normally `0600`). Environment variables remain valid ephemeral credential inputs.
- Raw/structured `bc250-code` contracts reject an outer Markdown code fence for `generate`,
  `refactor`, `test` and `commit`. The wrapper reports a contract failure rather than stripping the
  fence or atomically replacing a valid file with fenced source. `review`/`document` keep Markdown.
- Installer completion now reports Open WebUI baseline state separately as `APPLIED + VERIFIED`,
  `SKIPPED` or `RETRY REQUIRED`. Core install/verification success remains available-first and a
  recoverable Open WebUI configuration problem remains nonfatal, but is no longer hidden by an
  unconditional whole-install success sentence.
- `safe-power.sh` keeps its conservative existing rule that either endpoint of an established
  connection can match protected ports; the log/docs now say **protected TCP activity** rather than
  incorrectly implying only inbound SSH/UI/Ollama sessions.
- Upload pruning no longer assumes a 50-item Open WebUI page size. Listing continues until zero
  records, an advertised total is reached, or no new file IDs are discovered; uncertain metadata is
  still preserved rather than selected for deletion.
- Repository bootstrap `./install --help` is available without root.
- Correct the repeated `tags-en` false negative narrowly: the existing OCR semantic group now accepts
  `text recognition` / `optical character recognition`; the two-group relevance threshold, task prompt
  and production task model are unchanged.
- Installer Stage 7 now shows standalone MTP operational state as a read-only, non-indexed inventory.
  MTP remains excluded from normal selection/convergence and is never fetched implicitly.
- `bc250-run-mtp` now snapshots and drains resident models from every reachable Ollama lane before
  standalone llama.cpp launch. Direct operator runs restore the exact pre-run residency set on exit;
  `bc250-compare-mtp` records/uses `drain-only` isolation and intentionally leaves Ollama cold.

## Documentation / operator UX

- Slim the README `Daily commands` block to actual day-to-day appliance operations and route
  experiments, benchmarks, destructive lifecycle actions and reset to the detailed command/model docs.
- Mark older model decision tables as historical/superseded where later current sections changed the
  lifecycle decision.
- Explain that full read-only `status agentic MODEL` may report registration unavailable/UNKNOWN in
  normal mode because the exclusive agent API is intentionally stopped; status does not switch modes.
- Align RAG, model-manager, coding-agent and maintenance docs with the new enforced boundaries.

## New exact-device evidence carried into this source

Exact installed `0.11.3-1.6.fc44` completed guided install/core verification at 54/0/0 and full v4.2
revalidation with infrastructure/restoration PASS and FULL coverage. RAG passed 4/4 and Jina
residency restoration succeeded. The only scored quality miss was the `tags-en` evaluator vocabulary
gap above. GPT-OSS/Jina passed policy at 79.293 tok/s with 156.266 MiB minimum MemAvailable, 17.066
MiB swap peak delta and 72 C maximum temperature; 8662 -> 8320 prompt truncation remained a
non-severe diagnostic. This is exact-1.6 evidence, not exact-1.7 hardware qualification.

## Source validation

Focused affected-surface regression passed **196/196**. Final deterministic `make validate` passed
**413/413**. Changed/source Python compilation and packaged/source shell syntax are checked again at
artifact closure. RPM/SRPM build, Ruff, ShellCheck and exact installed BC-250 qualification remain
external unless explicitly reported otherwise.

## Next device gate

After installing exact 0.11.3-1.7, first confirm normal/degraded/stopped status semantics and the
existing 1.5 Jina residency-restoration fix through revalidation. Then proceed with the dedicated
support/maintenance campaign: read-only state, real S5 WOL, busy shutdown defer, idle shutdown allow,
recovery/restoration, local backup/restore, and optional Pi/backup-export only after the local path is
proven.
