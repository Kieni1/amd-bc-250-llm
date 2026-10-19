# Current state and next work — 0.14.1-1

## Current source/release identity

The active line is `bc250-llm-server-0.14.1-1`.

RPM naming rule:

- new product version -> `Release: 1`;
- package-only correction -> increment integer Release (`2`, `3`, ...);
- next product version -> reset Release to `1`.

Never publish changed bytes under an already-used NVR.

## Current architecture

The supported core is:

- Fedora 44 stock kernel/userspace path;
- package-owned Ollama/Open WebUI/Tika/governor stack;
- normal main/task/embedding Ollama lanes and optional exclusive agent mode;
- package model management and public `bc250` commands;
- GitHub Actions/Fedora 44 as primary release-build authority;
- local Fedora execution as secondary reproduction/debugging;
- no package-owned patched kernel boot, private Mesa/RADV or GFX lifecycle.

Current runtime pins in source:

```text
Ollama       0.34.4
Open WebUI   0.11.4
Tika         4.1.0-full
Governor     0.4.13
```

Treat these as current package choices, not permanent architectural commitments.

## Immediate next iteration — low-cost core functionality

The next device round answers only:

> Does the exact selected `0.14.1-1` RPM behave like a usable stock BC-250 appliance?

Use `03_CORE_FUNCTIONALITY_CHECK.md`. Do not reopen broad benchmarking, tuning, GFX qualification or full resilience campaigns during this round.

## If the core check passes

Freeze:

- exact RPM filename/NEVRA and SHA-256;
- selected GitHub run identity;
- device/kernel identity;
- short PASS/FAIL evidence for the core smoke.

Then use `08_GREENFIELD_SIMPLIFICATION_PLAN.md` only for bounded cleanup that clearly reduces ownership/failure surface. After that, shift directly to the product roadmap: excellent local RAG/document workflows, German–French translation UX and polished ordinary-user assistant operation.

## Bounded simplification target

The next engineering pass should reduce:

- obsolete scripts and dead compatibility paths;
- wrapper chains;
- duplicated state derivation;
- qualification/resilience remnants that are no longer active product needs;
- validation logic that became architecture;
- tests that only preserve implementation detail;
- duplicated docs and handover machinery.

Do not let cleanup become the roadmap. Keep it bounded and stop when the stock baseline is understandable and reliable. Then prioritize office intelligence/product UX rather than starting another infrastructure campaign.

## Deferred until deliberately reopened

- Ollama upgrade beyond 0.34.4;
- context-ceiling changes;
- performance tuning campaigns;
- broad model tournaments;
- experimental GPU/kernel/Mesa work;
- repository signing/SBOM/distribution hardening unless release distribution requires it.
