# MTP qualification and Phase-2 optimization state — 2026-09-19

## Evidence identity

Real-device evidence in this record was collected on:

```text
BC-250 / Cyan Skillfish
40/40 live-routed CUs
~16 GiB unified memory
Fedora 44
bc250-llm-server-0.11.3-0.4.fc44.x86_64
llama.cpp b10964
commit b29c606e28a01b1bc8c1351026a0fa6e616bf6c4
Vulkan backend
```

This evidence is historical for exact installed `0.11.3-0.4`. It informs current package
defaults and experiment ordering, but does not make later same-source or `0.11.3-1.4` bytes
hardware-qualified.

## Phase 1 — qualified configurations

### qwen3.5-9b-mtp — PASS

`Qwen3.5-9B-UD-Q4_K_XL.gguf`

| budget | baseline tok/s | MTP tok/s | speedup | acceptance |
|---:|---:|---:|---:|---:|
| 128 | 46.40 | 61.50 | 1.325x | 81.8% |
| 256 | 46.42 | 57.12 | 1.231x | 71.6% |
| 400 | 46.46 | 53.97 | 1.162x | 64.8% |
| 768 | 46.20 | 48.22 | 1.044x | 53.2% |
| 1024 | 46.07 | 48.42 | 1.051x | 53.2% |

Quality lane passed deterministically with exact baseline/MTP parity. MTP consumed roughly
0.5–0.6 GiB additional headroom. Interpretation: strong short-generation benefit, diminishing
benefit as generation length increases.

### qwen3.6-27b-mtp — PASS

`Qwen3.6-27B-UD-Q2_K_XL.gguf`

| budget | baseline tok/s | MTP tok/s | speedup | acceptance |
|---:|---:|---:|---:|---:|
| 128 | 18.59 | 26.06 | 1.402x | 87.0% |
| 256 | 18.63 | 23.59 | 1.266x | 72.6% |
| 400 | 18.66 | 22.83 | 1.224x | 68.7% |
| 768 | 18.59 | 22.13 | 1.191x | 64.9% |
| 1024 | 18.56 | 22.11 | 1.191x | 65.0% |

Quality lane passed deterministically with exact parity. Baseline minimum MemAvailable was about
1.96–2.02 GiB; MTP minimum about 1.18–1.26 GiB. Interpretation: strongest sustained long-generation
MTP gain among the Phase-1 passers, but the tightest successful memory margin.

### qwen3.8-27b-hauhaucs-mtp — PASS

| budget | baseline tok/s | MTP tok/s | speedup |
|---:|---:|---:|---:|
| 128 | 19.91 | 25.49 | 1.280x |
| 256 | 19.96 | 24.66 | 1.235x |
| 400 | 19.99 | 23.12 | 1.157x |
| 768 | 19.89 | 21.71 | 1.091x |
| 1024 | 19.86 | 21.42 | 1.078x |

Quality lane passed deterministically with exact parity. The reviewed run also preserved exact
performance-stream parity through 1024 tokens. Baseline minimum MemAvailable was about
3.54–3.56 GiB and MTP about 2.63–2.71 GiB. Interpretation: smaller long-form speedup than the
Qwen3.6 27B control, but materially more memory headroom and excellent parity behavior.

## Phase 1 — rejected stock-fit configuration

### qwen3.6-35b-a3b-mtp — stock 8K/full-GPU configuration DOES NOT FIT SAFELY

`Qwen3.6-35B-A3B-UD-IQ3_S.gguf`

The first baseline load at context 8192 / 99 GPU layers reduced MemAvailable from roughly
13.5 GiB to 120.4 MiB, below the 128 MiB hard safety floor, while swap was already increasing.
The live safety gate terminated the server (`safety_rc=60`) and restoration passed.

This is a model-fit/baseline limitation, not an MTP speed result: speculative inference was never
reached. Do not rerun the exact stock 8K/full-GPU configuration. Retest only under an explicitly
different fit hypothesis (for example materially lower context or another model/quant) with a clear
product reason.

## Phase 2 — first sweep invalid for depth selection, useful for repeatability

The first long draft-depth campaign did not actually vary depth. Its wrapper exported
`DRAFT_N_MAX=1/2/3/4`, but the then-used Phase-1 core reset the variable before resolving the
catalog value. Effective depths therefore remained 3 for Qwen3.5 9B and 2 for both 27B models.

Do **not** use that campaign to select a draft depth. Preserve it as repeatability evidence: repeated
default-setting results showed extremely low variability, with typical throughput CV around
0.01–0.19% and speedup moving only by small fractions of a percent. Treat sub-percent differences
as the measured noise floor; a new default should require approximately >=1.0% balanced improvement
over the catalog default, with quality/safety/restoration complete.

## Corrected override canary

A corrected hardware canary forced `qwen3.5-9b-mtp` to `DRAFT_N_MAX=1` and verified all three
relevant layers agreed:

```text
requested_draft_depth=1
run-info draft_n_max=1
recorded_draft_depth=1
CANARY PASS
canary_rc=0
```

At 64 tokens the canary produced about 46.258 -> 57.447 tok/s (1.242x), 96.9% acceptance,
exact parity, quality 3/3 PASS and no safety/restoration failure. This canary proves the override
path; it is not depth-selection evidence.

## Current Phase-2 question

Phase 2 is now optimization of already-qualified MTP configurations, not basic functionality
qualification. Sweep only `--spec-draft-n-max` for the three Phase-1 passers at depths 1,2,3,4,
using budgets 256 and 1024 with reduced exploratory repeats. Every point must prove requested depth
== effective emitted depth.

Only recommend a non-default depth when quality, completeness, safety and restoration pass, both
256- and 1024-token speedups remain above baseline, and balanced improvement over the catalog
default is approximately >=1.0%. If a non-default depth materially wins, confirm only that
model/depth with higher repeats; do not rerun a full four-depth confirmation sweep.

The new YMQ Qwen3.8 27B challenger is not part of the completed historical Phase-1 evidence above;
it remains pending a matched HauhauCS-control comparison on current package/source.
