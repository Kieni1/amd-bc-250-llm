# BC-250 0.11.3-1.1 patch note — work in progress

## Release identity

VERSION: `0.11.3`  
RPM Release: `1.1`  
Expected NVR: `bc250-llm-server-0.11.3-1.1`

This release line carries forward the unpublished 0.11.3-0.5 installer/maintenance and
revalidation-diagnostic refinements and adds a bounded RAG evaluator/integration tranche.
It is still **pre-release source work**: final deterministic/package/archive closure,
GitHub RPM/SRPM build and exact-source BC-250 qualification remain pending.

## RAG evaluator changes

- Replace naïve acceptance substrings with normalized boundary-aware matching so a
  forbidden value such as `9 November` cannot match inside the correct `19 November`.
  The same contract protects short numeric values, hyphenated IDs, currency values and
  dates from larger-token collisions.
- Add deterministic fixture support for multiple explicit semantic alternative groups
  (`required_any_groups`) and case-scoped numeric equivalence (`numeric_values`). This
  keeps grading strict and reviewable without fuzzy/LLM-based judging.
- Add deterministic RAG language evidence with `match`, `other` and `not-measurable`.
  Language-neutral values/IDs do not fail merely because no reliable language evidence
  exists, and `not-measurable` is recorded separately from a positive language match.
- Record target retrieval, all-required-source retrieval, fact/abstention, language,
  citation and overall acceptance independently. Existing `answer_ok` / `source_cited`
  compatibility fields remain in CSV evidence for now.
- Add structural completeness checking for `rag-quality` canonical results. Missing,
  duplicate or unexpected case IDs make `Structure: FAIL` while semantic quality and
  infrastructure remain separate dimensions.
- Harden `owui-rag` model selection against the real Open WebUI product contract. Exact
  active preset IDs are accepted directly; a raw Ollama base model is mapped only when
  exactly one active preset exposes it. Ambiguous/unknown selections fail before temporary
  knowledge/upload state is created, and evidence stores only the sanitized active
  `preset_id -> base_model` map used for resolution.
- Require HTTP readiness before `owui-rag` begins, with a bounded five-minute allowance for
  the observed slow Open WebUI startup case.
- Harden `bc250-compare-mtp` cleanup so negative-PID signaling is used only after both SID
  and PGID are proven equal to the launched llama-server PID. Otherwise cleanup signals
  only the direct child and reports the fallback.

## Carried-forward 0.5 work

- one default-No gate before optional maintenance/Pi setup;
- separate local maintenance and Raspberry Pi integration choices;
- targeted post-maintenance verification;
- concise post-install command/document/path guidance;
- non-failing diagnostics for <512 MiB tight MemAvailable headroom and accepted
  output-budget exhaustion, with the existing 128 MiB hard floor unchanged.

## Deliberate non-changes

- no production model, role, Modelfile or runtime-topology changes;
- no long-residency RAG benchmark framework yet;
- no new memory/swap failure thresholds;
- no MTP model/catalog/runtime-setting/tuning changes; only process-cleanup safety is hardened;
- no weakening of quality, restoration, device-error, provenance/SHA or secret-handling
  checks.

## Validation status

Focused touched-path source evidence currently includes **114 benchmark/packaging tests PASS**,
Python compilation for the touched benchmark/test files, and Bash syntax for
`compare-mtp.sh`. Broader deterministic/package/archive closure is deliberately deferred for
this iteration by maintainer direction. Real RAG/MTP hardware results are **not** embedded into
this source yet; those remain external evidence until handed back to main integration and
reviewed.

The newest complete whole-appliance hardware evidence remains exact installed
`bc250-llm-server-0.11.3-0.4.fc44.x86_64`. It must not be relabelled as 1.1 qualification.
