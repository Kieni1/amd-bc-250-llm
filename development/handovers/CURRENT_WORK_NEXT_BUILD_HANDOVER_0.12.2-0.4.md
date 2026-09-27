# BC-250 current work / next-build handover — 0.12.2-0.4

## Source state

The UX/model and Deep-residency batches are implemented in source. Current identity:

```text
VERSION       0.12.2
RPM Release   0.4
NVR           bc250-llm-server-0.12.2-0.4
Ollama        0.34.4
Open WebUI    0.11.4
Tika          4.0.0-full / TIKA_SERVER_VERSION=4
Governor      0.4.13
Revalidation  v4.6
```

Implemented source boundaries:

1. trustworthy revalidation semantic/budget/root-cause reporting;
2. Advanced `think=true` + exact 4096 ceiling with externally evidenced OWUI-to-Ollama mapping (raw outbound capture not retained in source);
3. Qwen3.6 35B retirement and aligned Qwen3.8 profile policy;
4. transaction-final installer handoff and verifier-derived final setup summary;
5. saved-profile/live-layout CU semantics;
6. protected default OWUI maintenance credential;
7. fail-closed pre-Deep task/embedding eviction plus exact `keep_alive=2m` bounded residency.

## Required exact-device acceptance

Source/static validation is not release acceptance. Exact-installed 0.12.2-0.4 must cover:

- real ordinary-user Open WebUI/browser journey and selector visibility;
- Advanced arithmetic/history/office writing/final-answer behavior under the 4096 ceiling plus latency/UMA;
- no-regression confirmation that stored `max_tokens=4096` yields Ollama `options.num_predict=4096` with no root-level Ollama `max_tokens`;
- Documents/RAG twice -> Deep -> second Deep within 2m -> 2m idle expiry -> later task/background and Documents cold reload;
- embedding/task pre-eviction success, `/api/ps` residency timeline, Deep first/reuse latency, minimum MemAvailable, swap/zram/PSI and kernel/AMDGPU/Vulkan critical events;
- configured CU profile/layout versus live routing, intentional disabled cells, RADV diagnostic-only count;
- migration-safe OWUI upgrade/rollback-snapshot behavior;
- final service topology/restoration and authenticated verifier cleanliness;
- current translation modality/polarity qualification in both directions.

## Evidence-first investigations still open

- Real office-generated DOCX heading/bullets/table through Tika -> OWUI index -> retrieval.
- Intermittent multi-model tag persistence/timing.
- BTF/kernel-build warning interpretation.

Do not turn those observations into source defaults without focused evidence.
