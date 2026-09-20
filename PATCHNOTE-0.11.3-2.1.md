# 0.11.3-2.1

Expected NVR: `bc250-llm-server-0.11.3-2.1`

RAG qualification integration and secondary-source cleanup on top of the 1.8 support/power fixes.

## RAG integration

- Keep `bc250-office-documents` / `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` as the production document/RAG role for the current 16 GiB profile.
- Expose `language_measurable` separately from `language_ok` in direct RAG evidence while retaining the existing three-state language status and compatibility field.
- Document the existing deterministic numeric/unit contract instead of adding another schema: `numeric_values` accepts numeric equivalence; `required` / `required_any_groups` express mandatory units or qualifiers.
- Clarify that chronological session MemAvailable start/min/end delta may include initial model load and is not workload-only resident-memory drift.
- Record the supplied Qwen3.8 27B IQ3_XXS 16K follow-up: the first five RAG cases were correct with citations, but MemAvailable fell to about 0.28 GiB before the 512 MiB campaign safety abort; unloading recovered about 13.8 GiB. Keep the same verified model identity at the safer 8K experimental default.

## Secondary cleanup

- Make the operator Modelfile template teach canonical category `experiments`; historical singular `experimental` metadata remains readable.
- Make the durable model-manager CLI contract versionless rather than carrying a stale release target.
- Apply the existing private Open WebUI credential-file boundary to benchmark `--token-file` inputs; no new credential subsystem is introduced.

## Deliberately not added

- No dedicated long-residency benchmark/subrun framework.
- No second telemetry/watchdog/residency implementation.
- No new unit-policy schema.
- No global 512 MiB failure rule; existing whole-appliance and campaign-specific thresholds stay distinct.
- No production model, topology, power-policy, governor/CU, GGUF or MTP-default change beyond the already-carried 1.8 IQ3_XXS 8K definition.

## Evidence boundary

The RAG campaign results recorded here are historical/operator-supplied BC-250 evidence and are not relabelled as `0.11.3-2.1` qualification. Exact installed `0.11.3-1.7` remains the newest full whole-appliance hardware baseline in the supplied source.

## Source validation

- Repository/source preflight: PASS.
- Existing deterministic source suite: **432/432 PASS**.
- Python compileall: PASS.
- `bash -n`: **64/64** shell/bootstrap entrypoints PASS.
- Ruff and ShellCheck were unavailable in this environment.
- RPM/SRPM builds were intentionally not run; package-build evidence remains the external gate.
- Exact installed `0.11.3-2.1` BC-250 hardware qualification is still required before making current-release device claims.
