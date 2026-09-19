# BC-250 0.11.3-1.3 patch note — work in progress

## Release identity

VERSION: `0.11.3`  
RPM Release: `1.3`  
Expected NVR: `bc250-llm-server-0.11.3-1.3`

This is the step-3 RAG benchmark-integrity tranche on top of 0.11.3-1.2. It carries forward the
unpublished installer/maintenance work, deterministic RAG/Open WebUI/MTP hardening, and the 1.2
Ruff/executable-mode correction unchanged.

## Changes in 1.3

- Add shared Ollama residency snapshot/restore helpers and use them in direct `rag-quality` so the
  benchmark restores the exact starting main and embedding model sets on every exit path.
- Verify restoration against `/api/ps`; restoration failure is an infrastructure failure instead of
  a warning. The reload helper supports both generative and embedding-only registrations without a
  second benchmark-specific lifecycle implementation.
- Extend the existing telemetry contract with MemAvailable start/end and end delta. RAG result rows
  retain request boundaries, and canonical RAG summaries expose a chronological resident-session
  view: MemAvailable start/min/end/drift, swap start/peak/end/cumulative growth, and maximum GPU
  temperature.

## Deliberate non-changes

- no long-residency benchmark mode yet; current live RAG evidence should determine its final shape;
- no new 512 MiB or swap-growth failure threshold; the existing 128 MiB hard floor and 512 MiB
  informational tight-headroom diagnostic remain policy;
- no production model, role, Modelfile, Open WebUI desired-state or MTP tuning changes;
- no compatibility framework for obsolete pre-v1.0 benchmark interfaces.

## Validation status

Focused deterministic benchmark tests cover exact residency restoration, embedding-only reload
fallback, chronological MemAvailable/swap aggregation and canonical RAG resident-session summaries.
Touched Python modules are syntax-compiled. Full RPM/SRPM, Ruff/ShellCheck and exact-source BC-250
qualification remain external/deferred.

The newest complete whole-appliance hardware evidence remains exact installed
`bc250-llm-server-0.11.3-0.4.fc44.x86_64`; it must not be relabelled as 1.3 qualification.
