# BC-250 0.12.1-0.5 RAG lifecycle testing handover

## Purpose

This is the focused retest handover for the `bc250-rag` preparation/lifecycle repair after exact-installed 0.12.1-0.4 exposed native-reasoning contamination in generated `working/*.md` files.

Do not reopen embedding/answer-model selection. Production Documents/RAG remains Gemma E4B with Jina v5 small retrieval on :11437. The human `working/ -> active/` approval boundary remains mandatory.

## Candidate

```text
VERSION       0.12.1
RPM Release   0.5
NVR target    bc250-llm-server-0.12.1-0.5
```

The exact-installed 0.12.1-0.4 appliance was otherwise healthy: Ollama 0.34.2, normal topology, authenticated verifier 54/0, package revalidation quality/restoration and the first RAG filesystem/security gate all passed. Do not replay those unrelated gates unless this repair affects them.

## Defect being repaired

0.4 used Ollama `/api/generate` and consumed the complete `response` field from the native-reasoning Ornith agent. Device output contained English self-analysis and a literal `</think>` before the intended Markdown. Critical-token coverage could also be falsely satisfied by source tokens quoted only inside leaked reasoning.

0.5 changes the contract to:

```text
POST /api/chat
think: true
stream: false
message.thinking  -> ignored for document/fidelity purposes
message.content   -> sole candidate normalized Markdown
```

Preparation must fail closed when:

```text
done != true
done_reason == length/max_tokens
message.content empty
final content contains <think>, </think>, <|think|> or equivalent handled delimiter
final content is wrapped in an outer Markdown fence
```

Do not accept a repair that merely strips text before `</think>`.

## Required preparation retest

Use synthetic, non-sensitive fixtures first. Prepare at least:

1. selectable-text German PDF with unique identifiers, dates and legal/numeric references;
2. matching French PDF with unique identifiers;
3. bilingual PDF with separate DE/FR identifiers;
4. image-only/scanned PDF;
5. oversized text-native PDF above the configured single-pass limit.

Use identifiers that are not production-special-cased, for example random forms such as:

```text
DE-REF-A7-9182
FR-CODE-B4-7315
BI-DE-X9-4421
BI-FR-Q2-6630
```

Run:

```bash
sudo bc250-rag prepare-batch public rag-test-public --dry-run
sudo bc250-rag prepare-batch public rag-test-public
```

Acceptance requires:

```text
four expected working drafts from the bounded DE/FR/bilingual inputs
zero literal reasoning contamination
source-fidelity checks based only on final message.content
all unique source identifiers preserved in the appropriate final body
no invented commentary/summary/process prose
scan input -> DEFERRED — OCR required
oversized input -> DEFERRED — source split required
real processing failure -> ERROR — processing failed
zero active files after preparation
normal topology restored
```

The batch summary must distinguish at least:

```text
prepared
deferred/manual
failed
```

Do not classify expected safe deferral as generic failure.

## Fidelity evaluator checks

Explicitly prove:

1. native reasoning contains a source marker but clean final content omits it -> fidelity reports REVIEW/missing;
2. final content contains the marker -> coverage can PASS;
3. literal reasoning marker in final content -> draft rejected;
4. `done_reason=length` -> rejected;
5. empty final content -> rejected;
6. outer Markdown fence -> rejected;
7. unique codes/identifiers survive normalization or produce a fidelity REVIEW rather than disappearing silently.

For bilingual documents, manual/visual language-specific fidelity remains required where whole-source automated coverage cannot distinguish the two language halves safely.

## Validation gate

Run:

```bash
sudo bc250-rag validate public rag-test-public --include-working
```

`working/` or `active/` Markdown containing obvious native reasoning delimiters must fail validation even if metadata says the file is reviewed.

Do not add heuristic prose detection that could reject legitimate English source text.

## UX acceptance

Confirm the following operator-facing distinctions:

- idempotent `init` says `RAG collection ready` and distinguishes created vs already present/converged;
- status uses `working awaiting review`;
- requested missing collection reports `RAG collection not found: SCOPE/COLLECTION`;
- invalid collection identifier diagnostics include the rejected value and allowed syntax;
- review numbering is based only on drafts actually being reviewed, so a pending review set starts at `[1/N]`;
- when no drafts need review, the command says so explicitly;
- effective-date prompt states that edition/version may satisfy the identity requirement;
- edition/version prompt states that it is required when effective date is blank.

Presence of these strings is a mechanical check, not automatically a human `UX PASS`. Record operator UX separately.

## Lifecycle behavior that must not change

Keep all of the following:

```text
prepare-batch writes only to working/
human review required before activation
only review_required=false may activate
only active/*.md is ingestible
source SHA/provenance enforcement
symlink/path defenses
loopback-only agent URL
shared bilingual source retention
activation/supersession semantics
scan deferral instead of guessed OCR
oversize deferral instead of automatic LLM chunk/reassembly
normal topology restoration
```

After preparation passes, continue the existing review/activation/supersession/Open WebUI ingestion acceptance. Do not continue those later stages if preparation fidelity fails.

## Acceptance-harness policy

The test harness is an evidence collector, not a fail-fast product assertion runner.

A mismatch such as NEVRA/count/wording/state must be recorded and independent evidence collection should continue. Use fields equivalent to:

```text
execution      EXECUTED | SKIPPED_SAFETY | SKIPPED_PREREQ | HARNESS_ERROR
observation    MATCH | MISMATCH | EXPECTED_REFUSAL | ERROR | REVIEW
classification PRODUCT_DEFECT | SAFETY_DEFECT | UX_DEFECT | ENVIRONMENT |
               EXPECTED_BEHAVIOR | EVIDENCE_GAP | HARNESS_DEFECT | CLEAN
```

Only the individual destructive/resource-sensitive subtest may be skipped when its own safety prerequisite is not met. Package the evidence regardless. Reserve a nonzero overall harness exit for a genuinely unsafe final appliance state or a mechanical harness failure that invalidates the evidence run.

## Final handoff

Return:

```text
RAG 0.12.1-0.5 -> MAIN INTEGRATION
installed NEVRA:
preparation result:
reasoning separation result:
fidelity result:
unique identifier result:
deferral taxonomy result:
validation result:
review UX result:
activation/supersession result:
OWUI ingestion result:
privacy/path result:
topology/restoration result:
verifier result:
observed defects:
evidence archive + SHA-256:
```
