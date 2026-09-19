# MTP final qualification / optimization state — 2026-09-19

## Purpose

This is the current consolidated MTP evidence record for the BC-250 project. It supersedes the
intermediate pending-work interpretation in `2026-09-19-mtp-phase1-and-phase2-state.md` while
preserving that older file as historical experiment state.

MTP is now qualified enough for current package use as an explicit opt-in experimental lane. Broad
qualification is closed; only targeted confirmation/optimization remains optional.

## Platform / runtime contract

```text
hardware: AMD BC-250 / Cyan Skillfish / RADV GFX1013
CU routing: 40/40 live-routed
memory: approximately 16 GiB unified/TTM-constrained
OS: Fedora 44
package at final handoff: bc250-llm-server 0.11.3-1.5.fc44.x86_64
external llama-server: /opt/llama.cpp/build/bin/llama-server
llama.cpp commit: b29c606e28a01b1bc8c1351026a0fa6e616bf6c4
backend: Vulkan
```

Package 1.5 did not materially alter MTP runtime defaults, resource thresholds, service topology or
inference configuration from the immediately preceding tested line, so the accumulated MTP evidence
remains relevant. Package 1.6 records the conclusion without changing MTP runtime defaults.

## Methodology / evidence rules

- same target GGUF for baseline and MTP phases;
- same llama.cpp build, context, cache, GPU and request settings;
- performance and semantic-quality lanes are separate;
- fixed-budget throughput runs must consume the intended budget and end with `finish_reason=length`;
- require nonzero proposal/acceptance telemetry before claiming speculative-decoding evidence;
- incomplete evidence is infrastructure/incomplete, not a model score;
- monitor MemAvailable, swap, GPU temperature, kernel/GPU faults, owned-process cleanup, port cleanup
  and final appliance verification;
- only exact experiment-owned PIDs/process groups may be terminated; no broad `pkill`/`killall`;
- preserve failure artifacts rather than automatically rerunning;
- change one meaningful parameter family at a time.

The specialist reference artifact supplied with this evidence is:

```text
artifact: bc250-mtp-reference-kit-v3.tar.gz
sha256: 16251f8f5bd6a753921f593897fcee3be7cbade26d0a1b83c4b8c2d9f5b7469b
```

The reference kit is not part of the RPM payload. It contains the reviewed Phase-1/Phase-2 harness,
operator helpers, validation notes, evidence summaries and historical package snapshots for
reproduction/reference. The compact execution guide and validator output are preserved source-only in
`development/references/mtp/`. The validator reports `KIT VALIDATION PASS`, including executable-mode,
shell/Python syntax, override propagation, effective-depth verification, exact process-cleanup rules,
mock resume integrations and scorer RC behavior. It performs no BC-250 inference; ShellCheck was
unavailable and is not claimed.

## Phase-1 qualified candidates

### qwen3.5-9b-mtp — PASS

GGUF: `Qwen3.5-9B-UD-Q4_K_XL.gguf`

Approximate reviewed performance:

| Budget | Baseline tok/s | MTP tok/s | Speedup | Acceptance |
| ---: | ---: | ---: | ---: | ---: |
| 128 | 46.40 | 61.50 | 1.325x | 81.8% |
| 256 | 46.42 | 57.12 | 1.231x | 71.6% |
| 400 | 46.46 | 53.97 | 1.162x | 64.8% |
| 768 | 46.20 | 48.22 | 1.044x | 53.2% |
| 1024 | 46.07 | 48.42 | 1.051x | 53.2% |

Quality was deterministic with exact baseline/MTP parity. This is the fastest absolute qualified
candidate and benefits most at shorter generations. MTP cost was roughly 0.5–0.6 GiB of additional
headroom in the reviewed Phase-1 run.

### qwen3.6-27b-mtp — PASS

GGUF: `Qwen3.6-27B-UD-Q2_K_XL.gguf`

| Budget | Baseline tok/s | MTP tok/s | Speedup | Acceptance |
| ---: | ---: | ---: | ---: | ---: |
| 128 | 18.59 | 26.06 | 1.402x | 87.0% |
| 256 | 18.63 | 23.59 | 1.266x | 72.6% |
| 400 | 18.66 | 22.83 | 1.224x | 68.7% |
| 768 | 18.59 | 22.13 | 1.191x | 64.9% |
| 1024 | 18.56 | 22.11 | 1.191x | 65.0% |

Quality was deterministic with exact parity. Baseline minimum MemAvailable was roughly 1.96–2.02
GiB and MTP minimum roughly 1.18–1.26 GiB. This showed the strongest sustained long-generation gain
of the original qualified set, but also the tightest successful memory margin.

### qwen3.8-27b-hauhaucs-mtp — PASS

| Budget | Baseline tok/s | MTP tok/s | Speedup |
| ---: | ---: | ---: | ---: |
| 128 | 19.91 | 25.49 | 1.280x |
| 256 | 19.96 | 24.66 | 1.235x |
| 400 | 19.99 | 23.12 | 1.157x |
| 768 | 19.89 | 21.71 | 1.091x |
| 1024 | 19.86 | 21.42 | 1.078x |

Quality was deterministic with exact baseline/MTP parity and especially strong performance-stream
parity. Baseline minimum MemAvailable was roughly 3.54–3.56 GiB and MTP minimum roughly 2.63–2.71
GiB. It trades some long-form acceleration for materially more memory headroom than Qwen3.6 27B.

### qwen3.8-27b-ymq-xs-ti-mtp — PASS

GGUF: `Qwen3.8-27B-Uncensored-YMQ-XS-TI.gguf`  
Repository: `zerodigest/Qwen3.8-27B-Uncensored-YMQ-MTP-GGUF`  
Context: 8192  
Draft depth: 2

Reviewed artifact: `bc250-mtp-reviewed-qwen3.8-27b-ymq-xs-ti-mtp-20260919-204422.tar.gz`.
The run executed on `bc250-llm-server-0.11.3-1.4.fc44.x86_64` with the same reviewed external
llama.cpp commit, context 8192, draft depth 2, three performance repeats and two quality repeats.
Quality/infrastructure/safety/restoration RCs were all zero, evidence was complete, final appliance
verification was clean, and every reviewed quality probe had deterministic exact baseline/MTP parity.

| Budget | Baseline tok/s | MTP tok/s | Speedup | Acceptance | MTP min MemAvailable |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | 20.798 | 24.614 | 1.183x | 60.0% | 2466.7 MiB |
| 256 | 20.793 | 22.164 | 1.066x | 48.4% | 2486.5 MiB |
| 400 | 20.902 | 23.196 | 1.110x | 52.8% | 2487.0 MiB |
| 768 | 20.785 | 23.728 | 1.142x | 55.6% | 2492.6 MiB |
| 1024 | 20.802 | 23.070 | 1.109x | 52.7% | 2384.4 MiB |

Compared with the earlier HauhauCS evidence, YMQ baseline decode was consistently about 4–5% faster.
At 128/256 tokens YMQ MTP was weaker, around 400 tokens it was similar, and at 768/1024 tokens its
absolute MTP throughput was materially better. Observed memory headroom was *lower*, not higher: YMQ
baseline roughly 3.18 GiB and MTP roughly 2.38–2.49 GiB versus HauhauCS roughly 3.54–3.56 GiB baseline
and 2.63–2.71 GiB MTP. Smaller GGUF size must not be treated as proof of lower runtime memory
consumption. A same-current-package HauhauCS control remains optional only if a publication-grade
comparison is required.

## Retired configuration

`qwen3.6-35b-a3b-mtp` at stock 8192 context/full GPU offload does not fit safely. During the first
baseline load MemAvailable fell from roughly 13.5 GiB to about 120 MiB, below the 128 MiB hard floor,
with swap growth; the live safety gate terminated the run before MTP inference and restoration
passed. This is a baseline memory-fit failure, not an MTP-speed failure. The exact active definition
is retired to `models/mtp/graveyard.toml`; do not rerun the same configuration without a new explicit
memory-fit hypothesis.

## Phase-2 history and noise floor

The first long draft-depth campaign was invalid for depth selection because the wrapper exported
`DRAFT_N_MAX=1/2/3/4` but the Phase-1 core reset it before catalog/default resolution. In reality,
Qwen3.5 repeatedly ran depth 3 and both 27B models repeatedly ran depth 2.

That campaign remains useful repeatability evidence: typical throughput CV was roughly 0.01–0.19%
and repeated speedups varied by only small fractions of a percent. Treat small sub-percent changes
as noise/workload preference. A conservative material-change threshold is approximately 1% balanced
improvement over the current package default.

A corrected hardware canary then forced Qwen3.5 to depth 1 and proved requested, run-info and emitted
server configuration all matched. The canary is override-plumbing evidence, not a depth-selection
benchmark.

## Corrected draft-depth sweep

Authoritative reviewed artifact: `bc250-mtp-phase2-draft-20260919-185429.tar.gz`.

The corrected sweep actually applied depths 1, 2, 3 and 4 to all three original qualified models.
All 12 points had complete evidence, passing quality, and quality/infrastructure/safety/restoration/archive
RC 0. Every requested depth was checked against the emitted runtime evidence rather than trusted from
a wrapper label.

### Qwen3.5 9B

Packaged/default depth: 3. Best exploratory result: depth 2.

```text
balanced speedup depth 2: ~1.185x
balanced speedup depth 3: ~1.139x
relative balanced improvement: about +4%
1024-token speedup depth 2: ~1.145x
1024-token speedup depth 3: ~1.049x
```

Depth 2 is a real candidate for replacing depth 3 and the gain is well above the measured noise
floor. Keep packaged depth 3 until confirmation-grade repeats are available if changing the default
is important. A confirmation, if desired, should test only depth 2 at 256/1024 tokens with 3
performance repeats and 2 quality repeats.

### Qwen3.6 27B

Keep depth 2. Depth 1 was fractionally better at longer generation but gave up more at shorter
generation; no non-default setting had a material balanced advantage.

### HauhauCS Qwen3.8 27B

Keep depth 2. Depth 1 improved long-form performance somewhat, but the balanced advantage was only
about 0.2%, below the material-improvement threshold.

## Package decision

- MTP remains explicit opt-in and excluded from generic installer/apply-all convergence.
- Keep current packaged draft depths: Qwen3.5=3, Qwen3.6=2, HauhauCS Qwen3.8=2, YMQ=2.
- No broad MTP campaign is required before general package work continues.
- Optional future testing is limited to a specific release/product decision:
  1. Qwen3.5 depth-2 confirmation if changing its default matters;
  2. same-current-package HauhauCS comparator if rigorous YMQ/HauhauCS memory comparison matters;
  3. YMQ depth optimization only if YMQ is being promoted/preferred.

## Retest only if

- a package-default change requires confirmation-grade evidence;
- model/quant/llama.cpp/runtime behavior materially changes;
- a new product role makes YMQ/HauhauCS selection materially important;
- a new hardware/runtime condition creates a justified memory-fit hypothesis.

Otherwise, move engineering attention to support/maintenance, real-document/product acceptance and
pre-v1 code cleanup after behavior is stable.
