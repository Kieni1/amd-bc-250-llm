# BC-250 current work / next-build handover — 0.13.1-1.2

## Identity

```text
VERSION       0.13.1
RPM Release   1.2
NVR target    bc250-llm-server-0.13.1-1.2
```

## Qualified baseline and optimization closures

Exact-device `0.13.1-1.0.fc44` is the measured optimization baseline. The earlier `0.12.2-0.8 -> 0.13.1-1.0` upgrade/convergence passed, `bc250 verify` was 53/0/0/0, Open WebUI desired state was clean, live CU routing matched the saved board profile, RAG passed, operator-added model registrations were preserved, and final `rpm -V` was clean.

Optimization program state:

```text
Sidechat 15  CLOSED — NO GAIN, keep residency/keepalive/swappiness defaults
Sidechat 16  CLOSED — keep 32K; q4_0 KV advanced only as a candidate
Sidechat 17  CLOSED — keep parallel=1, flash=1, num_batch auto, full offload
Sidechat 18  CLOSED — TOP_K=4 survived RAG/product qualification
Sidechat 19  CLOSED — reject combined q4_0 + TOP_K=4; promote TOP_K=4 alone
```

Sidechat 19 authoritative result:

```text
CLASSIFICATION=REJECT — COMBINED CANDIDATE
production KV     q8_0   KEEP
production TOP_K  4      PROMOTE
```

The q4_0 rejection is Advanced/Qwen quality instability at the existing 6144-token production ceiling, not memory/OOM failure. Clean 6144-token hidden-reasoning exhaustion with no visible answer remains INCOMPLETE; repetition at that ceiling remains a genuine quality defect.

## 0.13.1-1.2 implementation delta

This release does not reopen model identities, context limits, lane topology, keepalive, Deep admission, flash attention, parallelism or GPU offload.

Implemented changes:

1. Promote package Open WebUI/Documents RAG `TOP_K` from 8 to 4 while keeping the qualified 1500/200 chunk profile, Jina embedding, Tika extraction, hybrid search off and 32K Documents context.
2. Keep `OLLAMA_KV_CACHE_TYPE=q8_0`; do not package the rejected q4_0 candidate.
3. Extend optional-model semantics to the inactive alternate embedding model `embed-qwen3-0.6b-q8-0`: absent/cached-unselected is OPTIONAL, not MISSING/DRIFT, with no repair recommendation.
4. Keep operator-added registrations informational. Default qualification checks required package identities rather than exact total registration count and never deletes extra registrations merely to create a clean baseline.
5. Normalize unambiguous office dates/times in use-case acceptance so equivalent forms such as `04.09.2026` / `4. September 2026` and `10 AM` / `10:00` do not create semantic false negatives.
6. Preserve numeric acceptance as expected-value membership rather than a "last number in the explanation" heuristic.
7. Parse grouped RAG citations by source membership, so `[alpine-ops, alpine-ops-neighbor]` satisfies required source `alpine-ops`, while a prefix-only different source does not.
8. Treat semantically equivalent invoice identifiers such as `INV-2026-0441` and `Invoice 2026-0441` as the same required identifier without weakening unrelated matching.
9. Classify clean RAG hidden-reasoning budget exhaustion with empty visible output as INCOMPLETE/retry; repetition or independent retrieval/semantic failure still remains a quality failure.
10. Distinguish Open WebUI listener, backend and usable front-door readiness. HTTP 502/listener-only state is not application readiness; installer publication and `bc250 verify` use `/api/version` through the actual path.
11. Record benchmark starting MemAvailable, SwapUsed, memory PSI and per-lane Ollama residency in canonical metadata; revalidation snapshots/checkpoints also capture memory PSI.
12. Add explicit generation benchmark automation controls: `--context/--no-context`, `--thermal/--no-thermal`, `--board-note`, `--non-interactive`. Optional prompts are disabled in non-interactive mode rather than hanging wrappers.
13. Verify zram through the active swap set (`swapon --show`/equivalent), including the initialized-but-not-swapped failure mode, and parse actual failed systemd unit rows rather than trusting `systemctl --failed` exit status. This does not change swap size/swappiness policy.
14. Correct generic CU documentation: the stable profile is board-specific; 40/40 is an example/qualified state for an individual board, not a universal health requirement.
15. Preserve task title/tag qualification as result/persistence semantics; a short-lived task model escaping residency sampling is not by itself a failure.
16. Preserve fail-closed bounded package-tree bytecode cleanup and distinguish unavailable registration state from a proven unregistered optional model.
17. Fail closed before destructive managed disk-swap resize/removal: if active-swap state cannot be read or the active swap file cannot be deactivated, do not unlink or replace it.
18. Harden firewalld verification to detect protected internal TCP ports exposed by numeric ranges, active custom service definitions or accepting rich rules.
19. Make Source0 cache hygiene recursive for pytest/Ruff caches and exclude both `*.pyc` and `*.pyo`, with archive-level regression coverage.
20. Narrow date/time/invoice semantic-equivalence substitution to standalone required values; a compound required phrase cannot pass merely because its embedded semantic token is present.
21. Broaden positive HTTP publication verification to accept direct TCP/80, ranges containing 80, custom active services containing 80/tcp and accepting rich rules, while treating service-inspection failure as unverified.
22. Distinguish unreadable active-swap inspection from a known-empty swap set in read-only status/verification; destructive swap lifecycle remains fail-closed.
23. Clear Ruff-default one-line-suite/semicolon statement violations without suppressing lint rules or changing runtime behavior.

## Runtime defaults explicitly preserved

```text
OLLAMA_CONTEXT_LENGTH=32768
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_NUM_PARALLEL=1
OLLAMA_FLASH_ATTENTION=1
OLLAMA_MAX_LOADED_MODELS=1
main keep_alive=20m
task keep_alive=0
embedding keep_alive=10m
Deep keep_alive=2m
Advanced max_tokens=6144
Translation num_predict=2048
vm.swappiness package policy unchanged
Deep task+embedding pre-eviction unchanged
full GPU offload unchanged
```

## Release qualification focus

This revision changes RAG retrieval breadth and package tooling/evaluators, so run source/package gates plus a bounded exact-RPM delta:

- `bc250 verify` and Open WebUI desired-state status;
- Documents/RAG direct + OWUI smoke with TOP_K=4;
- Advanced Structured normal q8_0 path (do not rerun q4_0 discovery);
- office-draft date semantic regression;
- readiness boot/front-door behavior, including 502 not-ready semantics;
- model status for alternate embedding optional state and preservation of extra registrations;
- active-zram-swap verification, including initialized-but-not-swapped behavior, plus actual failed-unit parsing;
- managed disk-swap failure-path smoke: a forced `swapoff` failure must leave the backing file/configuration untouched;
- firewalld verification smoke for a protected port inside a range and inside a custom active service;
- generation benchmark non-interactive CLI smoke and metadata starting-state fields;
- final `rpm -V`, failed-unit, registration/residency and secret-scan restoration checks.

Do not repeat Sidechats 15–19 unless a later runtime/model/RAG change invalidates their assumptions.

## Source validation checkpoint

```text
542/542 deterministic unittest cases PASS across 17 isolated modules
python3 scripts/validate.py preflight PASS
python3 development/scope.py check PASS
59 shell sources bash -n PASS
35 Python sources AST-parse PASS
15 JSON + 5 TOML parse PASS
Ruff binary unavailable locally; the user-supplied Ruff run's final SIM103 and I001 findings were corrected without suppressions, on top of the earlier E701/E702/no-placeholder-f-string cleanup
```

Ruff itself remains mandatory in the normal workstation/CI build gate before the RPM is accepted.
