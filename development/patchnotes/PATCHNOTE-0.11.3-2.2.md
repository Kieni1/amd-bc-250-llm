# 0.11.3-2.2

Expected NVR: `bc250-llm-server-0.11.3-2.2`

Final model-policy integration and faster developer-side package regeneration on top of 2.1.

## MTP package policy

- Keep MTP standalone, explicit opt-in, disabled/download-only and excluded from normal installer/Open WebUI/Ollama convergence.
- Use the existing MTP catalog as the single source for runtime context/draft plus thin operator policy metadata (`role`, `recommendation`).
- Promote package defaults to `qwen3.5-9b-mtp` 16K/draft 2 as primary fast, `qwen3.8-27b-ymq-xs-ti-mtp` 8K/draft 1 as primary general 27B, and HauhauCS Qwen3.8 27B 8K/draft 2 as the specialist alternative.
- Retire Qwen3.6 27B from active discovery as superseded while preserving its exact positive historical definition in source-only `graveyard.toml`; keep the 35B-A3B stock-envelope fit failure retired.
- Remove ambiguous 27B convenience aliases rather than silently retarget them; exact 27B IDs are required.
- Do not add automatic promotion/retirement, benchmark-result ingestion or another recommendation database.

## RAG conclusion

- Keep `bc250-office-documents` / Gemma E4B as the production RAG default. Corrected direct scoring is 94/96 overall for Gemma versus 93/96 for Qwen 9B, with both retaining strong short-path product evidence.
- Keep the Qwen3.8 IQ3_XXS 16K 5/5 result explicitly partial-before-resource-abort; 16K remains rejected and the same 8K identity remains experimental only.
- Future RAG work is real-document acceptance/retrieval realism, not another answer-model tournament.

## Package regeneration

- Preserve the existing verified `sources/` cache with normal `make clean`; `clean-sources` remains explicit.
- Default `scripts/ci-local.sh` to Podman `--pull=missing` instead of pulling Fedora every invocation.
- Allow `BC250_BUILD_IMAGE` / `BC250_BUILD_PULL_POLICY` overrides and skip dependency installation when a prebuilt Fedora builder already contains the required packages.
- Do not add an `rpm-fast` path that bypasses validation.

## Evidence boundary

The RAG and MTP decisions are based on historical/operator-supplied BC-250 qualification evidence, including installed 1.7 MTP optimization. They are package policy inputs, not exact installed 2.2 hardware qualification. Exact installed 1.7 remains the newest full whole-appliance baseline; the inherited 1.8 safe-power and 40-CU fixes still need their first exact-current-release device confirmation.

## Source validation

- Repository/source preflight: PASS.
- Existing deterministic source suite: **433/433 PASS**.
- Python compileall: PASS.
- `bash -n`: **64/64** shell/bootstrap entrypoints PASS.
- Ruff and ShellCheck: unavailable in this environment; external developer/build gate.
- RPM/SRPM build: intentionally not run here; external build gate.
- Exact installed `0.11.3-2.2` BC-250 hardware qualification: pending.
