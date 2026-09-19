# BC-250 specialist testing handover template

Use this template for temporary RAG, translation, general-quality, agentic, benchmark-
operations or MTP chats. Do not maintain a permanently duplicated full project state in
each specialist file.

## First instruction

> Read the newest supplied source as authority, then read
> `development/TESTING-STRATEGY.md`, `development/VALIDATION-MATRIX.md`,
> `development/DECISIONS.md`, the relevant package docs and `MODELS.md`. Work only on the
> assigned lane. Use one bounded BC-250 batch at a time. Do not change production defaults,
> version metadata or unrelated package policy without returning evidence to main
> integration first. Never weaken evaluators/restoration to make a candidate pass.

## Lane contract

Fill in at chat start:

```text
lane:
current production baseline:
question being answered:
cheap/direct gate:
real integration gate:
resource/coexistence gate:
repeatability requirement:
stop rule:
retest conditions from existing decisions:
```

Suggested lane references:

- benchmark operations: `cmd/benchmark/README.md`, benchmark source/tests;
- RAG: `docs/RAG.md`, `config/openwebui/desired-state.json`; direct `rag-quality` must preserve starting Ollama residency set, use a non-empty embed probe for embedding-only reloads, and report resident-session MemAvailable/swap state;
- translation: `docs/QUALITY-CHECKS.md`, `MODELS.md`, translation quality scripts;
- general/main: `MODELS.md`, generation/usecase benchmarks;
- agentic: `models/coding-agent/README.md`, exclusive agent-mode tooling;
- MTP: `models/mtp/README.md`, `models/mtp/models.toml`, `bc250-fetch-mtp`, `bc250-run-mtp`, `bc250-compare-mtp`; broad BC-250 qualification is now complete enough for package use. Qwen3.5 9B, Qwen3.6 27B, HauhauCS Qwen3.8 27B and YMQ XS-TI Qwen3.8 27B have passing same-target baseline/MTP evidence under the reviewed llama.cpp Vulkan runtime. The 35B-A3B stock 8K/full-GPU configuration is a retired fit failure. Corrected draft-depth testing keeps depth 2 for Qwen3.6/HauhauCS; Qwen3.5 depth 2 is the strongest exploratory candidate but packaged depth 3 remains until optional confirmation-grade evidence justifies a default change. YMQ passes at depth 2; further optimization is optional only if it is being promoted. Generic installer selection and combined `apply all` / `refresh all` never select MTP; preparation remains explicit. Do not reopen broad MTP campaigns without a concrete product question.

## Required specialist handoff

```text
<LANE> -> MAIN INTEGRATION
source / installed NEVRA:
exact baseline and candidate(s):
settings:
commands actually run:
quality/measurement result:
resource result:
real integration result:
restoration result:
observed facts:
interpretation:
decision:
retest only if:
evidence artifacts + SHA-256:
recommended next action:
```

If a candidate loses the promotion case at an earlier gate, stop. Do not spend expensive
coexistence/integration time merely to finish a matrix.
