# BC-250 release testing handover — 0.12.2-0.6

## Candidate

```text
NVR           bc250-llm-server-0.12.2-0.6
Ollama        0.34.4
Open WebUI    0.11.4
Tika          4.0.0-full
Governor      0.4.13
Revalidation  v4.6
```

Source/static success is not exact-device acceptance. This gate is intentionally focused.

## 1. Install / completion / topology

Install exact 0.12.2-0.6 and record `rpm -V`, runtime versions, kernel, configured/live CU profile and final normal main/task/embed active + Agent inactive topology. Guided OWUI convergence must still hold public/boot publication until authenticated desired-state apply/status succeeds. Never `systemctl enable open-webui.service`; it is Quadlet-generated.

Verify the compact installer footer on a real terminal: plain `OVERVIEW`, amber/yellow `NEXT STEPS`, CU routing, models, validation and benchmark entry points.

## 2. Optional Agent semantics

Agent is not a core install prerequisite.

Without an Agent model installed, expected result is:

```text
Agent phase       SKIPPED / optional coverage unavailable
Coverage          PARTIAL is acceptable
Infrastructure    not failed solely because Agent is absent
```

If Ornith or another Agent add-on is explicitly installed, revalidation must qualify the exclusive Agent lane and restore normal topology. Real Agent service/API/topology faults remain infrastructure failures.

## 3. Structured-output product policy

Confirm through the ordinary-user browser-shaped production path:

- Standard structured: exact schema in `params.format`, request `temperature=0.0`, no `think` override;
- Documents structured: exact schema in `params.format`, request `temperature=0.0`, normal/default thinking;
- Advanced normal: stored/effective `think=true`;
- Advanced Structured: same Qwen3.5 base/samplers/6144 ceiling with stored/effective `think=false`;
- Deep: unchanged.

Use type-sensitive exact JSON validation and include negative/control non-structured turns proving ordinary behavior is unchanged. Adapter/helper inspection alone is not sufficient; preserve effective request/routing evidence.

No additional Documents-only sampling is required before this integrated product-path check.

## 4. Translation disposition and EuroLLM challenger

Production Translate-Gemma remains current. The known native DE->FR `sollten -> doivent` strengthening is documented as an accepted model limitation; the package modality guard must continue to fail closed rather than silently expose a strengthened obligation.

Closed challenger evidence:

```text
exp-eurollm9b-instruct-2512-mradermacher-q4-k-m
```

Round 1 is sufficient. EuroLLM fixed the `sollten -> devraient` anchor (2/2) but reproducibly emitted English for German `muss nicht` (0/2); ordinary office cases were 6/6 for both models. Do not run Round 2. Retain Translate-Gemma and the fail-closed modality guard.

## 5. Benchmark contract

Confirm generated summaries expose separate cold-load time, 4K/16K target-vs-actual context aggregates, thermal mean/min/max/first/last/drift and selected-lane completeness. Missing selected lanes are infrastructure/completeness failures, not model-quality defects. No synthetic board ranking is part of release acceptance.

## 6. Final whole-appliance check

Run one final `sudo bc250 revalidate start` and preserve the evidence archive. Record Infrastructure, Quality, Restoration and Coverage independently, plus minimum MemAvailable/swap/OOM diagnostics, CU configured/live profile match, final topology, `rpm -V` and bounded kernel/device-error window.

Do not rerun closed Deep architecture, Tika list rendering, title/tag persistence, RAG/MTP/OCR/coding-agent/maintenance/uninstall campaigns unless this release actually crosses one of those boundaries.
