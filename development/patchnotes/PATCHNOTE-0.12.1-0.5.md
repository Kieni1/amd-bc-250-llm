# BC-250 0.12.1-0.5 development patch note

## Release identity

```text
VERSION      0.12.1
RPM Release  0.5%{?dist}
NVR          bc250-llm-server-0.12.1-0.5
```

## Why 0.5 exists

Exact-installed 0.12.1-0.4 was runtime healthy: package convergence, Ollama 0.34.2, normal topology, authenticated verifier 54/0, packaged revalidation quality/restoration and the first bounded RAG filesystem/security gate all passed. Device testing then found two release-blocking source defects plus several state-presentation issues.

The RAG preparation path consumed native Ornith reasoning from `/api/generate` as if it were normalized document content; leaked reasoning could also satisfy the critical-token fidelity check. Separately, `bc250-revalidate status --raw` discarded its CLI option and returned human output. These are source defects even though the appliance/runtime state remained healthy.

## RAG repair

`bc250-rag` now reuses the proven coding-agent response contract: `/api/chat`, `think:true`, terminal completion, non-empty final `message.content`, and fail-closed rejection of output-limit termination, literal reasoning markers and outer Markdown fences. Native `message.thinking` is never part of the document/fidelity input.

The normalization prompt explicitly preserves unique identifiers/codes/markers unless repeated decorative page furniture is clearly established. Critical-token coverage also recognizes uppercase alphanumeric/hyphen identifiers. Working/active validation rejects obvious `<think>`-family reasoning markers so contaminated content cannot be activated accidentally.

Expected safety deferrals are now distinct from failures: scanned/near-empty PDFs report `DEFERRED — OCR required`, oversized single-pass inputs report `DEFERRED — source split required`, and real processing errors report `ERROR`. The batch summary separates prepared files/drafts, deferred/manual inputs and failures. Review/status/init/missing-collection wording is also made explicit. The human `working/ -> active/` approval boundary is unchanged.

## Revalidation / CU / operator UX

`bc250-revalidate status --raw` now forwards options correctly; harness identity is v4.4, with no change to the already-qualified phase/bundle semantics.

Installer/CU wording now presents live 40/40 routing as the operational authority and the persistent boot module as optional secondary state. The kernel `active_cu_number` counter is labelled non-authoritative for live routing, and the initial setup plan no longer calls the kernel simply `current` before Fedora repository evaluation.

## GPT-OSS factual fallback

The production GPT-OSS Modelfile keeps its qualified sampling/context/residency settings. Only the system instruction changes: factual/list questions should return fewer reliable items and state uncertainty instead of filling requested counts with plausible names or placeholders.

## Open WebUI role/tool policy and testing visibility

The 0.5 candidate also incorporates the browser/OWUI findings from direct Standard, Advanced, Deep and Translation testing. Standard, Advanced and Deep now use model knowledge normally instead of treating the absence of a document store as inability to answer. Autonomous built-in Open WebUI knowledge/chat/search tools are disabled on those general roles; the Documents role remains the dedicated retrieval path and keeps knowledge retrieval enabled. Translation roles keep tool use disabled and explicitly preserve legal/contractual modality so recommendations, permissions and obligations are not strengthened or weakened during DE↔FR translation.

During pre-v1 testing the normal main (`11434`) and task (`11435`) Open WebUI providers are intentionally unrestricted. All models actually installed on those lanes are selectable for direct comparison, while curated `bc250-office-*` roles remain the product contracts. Embedding (`11437`) and exclusive agent (`11436`) stay outside the normal chat selector. Package-owned raw implementation/task overrides are visible and labelled as testing surfaces; direct raw GPT-OSS keeps `keep_alive=0` for the same memory-safety reason as the curated Deep role. Desired-state status now checks the package-owned capabilities/built-in-tool metadata as well as visibility.

## Testing boundary

Do not replay the completed 0.4 broad model qualification unless these narrow fixes touch a runtime boundary unexpectedly. Focused exact-installed acceptance should cover RAG preparation fidelity/reasoning separation, lifecycle UX, `status --raw`, installer/CU wording, one Deep factual-quality smoke, package integrity/verifier and final normal topology.
