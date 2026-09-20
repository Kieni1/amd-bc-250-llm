# BC-250 specialist testing handover template

Use this for temporary support, RAG, translation, general-quality, agentic, benchmark-operations or
MTP chats. Do not maintain a second full project state here; the newest source and main handover are
authoritative.

## First instruction

> Read the newest supplied source first, then `development/handovers/MAIN-INTEGRATION-HANDOVER.md`,
> `development/TESTING-STRATEGY.md`, `development/VALIDATION-MATRIX.md`,
> `development/DECISIONS.md`, `MODELS.md` and the lane-specific package docs. Work only on the assigned
> lane. Use one bounded BC-250 batch at a time. Preserve verified GGUFs, restore state before changing
> lanes, and never weaken quality/safety/restoration checks to make a run pass. Do not change
> production defaults, release metadata or unrelated package policy without returning evidence to
> main integration.

## Lane contract

Fill in at chat start:

```text
lane:
source release:
installed NEVRA:
question being answered:
starting topology/state:
cheap/read-only gate:
real integration gate:
resource/coexistence gate:
restoration requirement:
stop rule:
retest conditions from existing decisions:
```

## Current lane guidance

- **support / maintenance / power:** read `docs/MAINTENANCE.md`,
  `docs/MAINTENANCE-CONTRACT.md`, `cmd/maintenance/maintenance.sh` and `safe-power.sh`. Current highest
  hardware priority is a narrow exact-2.1 changed-boundary pass: interactive SSH defer and healthy
  40-CU rc=0. Add Pi forced-command/second-SSH and one idle S5→WOL→HTTP readiness cycle only when
  those optional power features are being enabled. No-download model lifecycle and backup restore are
  separate bounded support acceptance, not automatic release gates. Evaluate operator UX as well as
  functionality.
- **benchmark operations:** use `cmd/benchmark/README.md` and current benchmark source/tests. Prove
  result completeness, resource telemetry and restoration on a known production control before a
  large campaign.
- **RAG / documents:** production answer role is Gemma E4B via `bc250-office-documents`; model
  selection is closed for the current 16 GiB profile. The active question is real-office-document
  acceptance: actual PDFs/Tika, messy tables, multilingual/multi-source questions, OCR-derived text,
  update/delete/re-import behavior, long residency and one deliberate unload/reload. Direct RAG work
  must preserve starting residency and use non-empty embedding probes for embedding reload.
- **translation:** production is Translate-Gemma E4B through explicit DE→FR / FR→DE roles. Broad
  discovery is closed; run only integrated requalification or investigate a proven product-level
  failure.
- **general/main:** use existing production contracts. The meaningful bounded comparison is GPT-OSS
  20B versus Qwen3.5 9B for deep-office quality versus memory cost; do not reopen broad 27B/35B
  discovery without a concrete reason.
- **agentic/coding:** use `models/coding-agent/README.md`. Agent mode is exclusive; verify normal-mode
  restoration. File-producing/commit contracts reject outer Markdown fences, truncation/incomplete
  final content and reasoning contamination. Product-path evidence must exercise actual documented
  `bc250-code` modes, not only the canonical benchmark.
- **MTP:** use `models/mtp/README.md`, `models/mtp/models.toml`, `bc250-fetch-mtp`, `bc250-run-mtp` and
  `bc250-compare-mtp`. Broad qualification is closed. Active qualified entries are Qwen3.5 9B,
  Qwen3.6 27B, HauhauCS Qwen3.8 27B and YMQ XS-TI Qwen3.8 27B; 35B-A3B is a retired memory-fit failure.
  Direct runs drain and restore Ollama residency; comparison uses drain-only isolation. Only reopen
  targeted work for an actual depth/default/promotion decision.

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
operator UX result:
restoration result:
observed facts:
interpretation:
decision:
retest only if:
evidence artifacts + SHA-256:
recommended next action:
```

If a candidate loses the promotion case at an earlier gate, stop. Do not spend expensive
coexistence/integration time merely to complete a matrix.
