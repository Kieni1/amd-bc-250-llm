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

- **support / maintenance / power / Open WebUI operations:** read `docs/MAINTENANCE.md`,
  `docs/MAINTENANCE-CONTRACT.md`, `docs/openwebui-settings.md`, `cmd/maintenance/maintenance.sh` and
  `safe-power.sh`. Exact installed 2.4 is the latest broad operations baseline: package integrity,
  topology/recovery, maintenance/backup/restore, storage hygiene, runtime soak, live 40/40 and a real
  supported reboot reconstruction all passed. The final exact-2.4 OWUI investigation then proved
  ordinary-user model ACL and Deep Reasoning residency defects plus the two-view verifier defect, with
  narrow temporary mitigations. Current source 0.12.1-0.6 preserves the established runtime configuration and focuses on effective ordinary-user model visibility, translation integrity, centralized Qwen request policy and operator/evidence observability. Exact 0.4 already provides broad runtime/model evidence; do not replay it unless the repair crosses that boundary. Keep the pinned-v0.11.3 adapter limitations documented rather than
  treating `/api/chat/completions` as a supported external compatibility contract. Do not deliberately
  rerun the device-proven unreliable `sudo systemctl reboot` path or reopen model selection. Pi/S5/WOL,
  live pruning and other destructive support checks remain conditional, not automatic release gates.
  Evaluate operator UX as well as functionality.
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
  `bc250-compare-mtp`. Broad qualification is closed. Active policy is Qwen3.5 9B 16K/d2 as primary
  fast, YMQ Qwen3.8 27B 8K/d1 as primary general 27B, and HauhauCS Qwen3.8 27B 8K/d2 as specialist
  alternative. Qwen3.6 27B is retired as superseded; 35B-A3B is retired for memory fit. Direct runs
  drain/restore Ollama residency and comparison uses drain-only isolation. Reopen only for a materially
  new runtime/model/hardware or product question.

## Current 0.12.1-0.6 testing priority

Keep this round impact-based and use `development/handovers/RELEASE-TESTING-HANDOVER-0.12.1-0.6.md`. Do not replay broad closed campaigns. Prove the effective ordinary-user model selector against actual 11434/11435 inventory, embedding/agent exclusion, additive/non-destructive model reconciliation, DE↔FR modality/literal integrity behavior, Advanced effective nested request params, status residency/reboot wording, revalidation v4.5 identity/raw output, support-bundle timeout/self-verification, package integrity/verifier and final normal topology.

The already-repaired RAG lifecycle semantics from 0.5 remain in force; reopen them only if a 0.6 change demonstrably crosses that boundary. Qwen template replacement, generic memory admission and the model-only deployment profile are not part of this release.

## Acceptance-harness evidence policy

Acceptance harnesses must record device truth rather than aborting the whole evidence run on an ordinary product mismatch. Keep execution/observation/classification separate; a failed assertion is evidence and independent checks continue. A destructive or resource-sensitive subtest may skip only itself when its safety prerequisite is not met. Reserve a nonzero overall harness exit for an unsafe final appliance state or a mechanical harness error that invalidates the evidence run. Also distinguish mechanical field/string presence from human UX judgment; do not call string presence alone `UX PASS`.

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
