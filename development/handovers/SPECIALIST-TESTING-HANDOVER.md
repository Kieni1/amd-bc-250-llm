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
  narrow temporary mitigations. Current source 0.12.2-0.6 is the active narrow release candidate: Ollama 0.34.4, Open WebUI 0.11.4, migration-safe OWUI backup gating, Advanced `think=true` with `max_tokens=6144`, retired Qwen3.6 35B, profile-aligned Qwen3.8 experiments, protected OWUI maintenance authentication, saved-profile/live-layout CU semantics, and fail-closed pre-Deep eviction with `keep_alive=2m`. Use the dedicated 0.12.2 release-testing handover and requalify only the crossed boundaries. Keep the external OpenAI-style adapter outside the advertised product contract rather than
  treating `/api/chat/completions` as a supported external compatibility contract. Do not deliberately
  rerun the device-proven unreliable `sudo systemctl reboot` path or reopen model selection. Pi/S5/WOL,
  live pruning and other destructive support checks remain conditional, not automatic release gates.
  Evaluate operator UX as well as functionality.
- **benchmark operations:** use `cmd/benchmark/README.md` and current benchmark source/tests. Prove
  result completeness, resource telemetry and restoration on a known production control before a
  large campaign.
- **RAG / documents:** production answer role is Gemma E4B via `bc250-office-documents`; model
  selection is closed for the current 16 GiB profile. The focused Tika DOCX list question is also closed:
  genuine LibreOffice bullets serialize as `· item`, while heading/table/list content and retrieved facts
  remain intact, so no package rewrite is indicated. Broader arbitrary-document/OCR lifecycle work is
  optional product qualification rather than a blocker for the current 0.5 delta. Direct RAG work must
  preserve starting residency and use non-empty embedding probes for embedding reload.
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

## Current 0.12.2-0.6 testing priority

Use `development/handovers/RELEASE-TESTING-HANDOVER-0.12.2-0.6.md`. Exact 0.12.2-0.5 narrowed the remaining work to installer completion/CU orientation, the package-default Agent prerequisite/attribution contract, and the DE->FR recommendation-modality/product-finalization path. Test those surfaces directly plus one final revalidation. Preserve the previous clean Deep/RAG/Tika/title-tag/topology evidence as comparison context; do not replay those closed campaigns unless a focused 0.6 result crosses their boundary.

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
