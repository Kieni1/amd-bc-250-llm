# MTP models

MTP entries are optional **download-only** llama.cpp experiments. They are not Ollama
role models and remain excluded from normal `apply all` / installer convergence until
real BC-250 qualification justifies a stronger integration decision.

The packaged entries are intentionally `enabled = false`. Ordinary `bc250-model list mtp` and
`apply mtp` therefore do not select them accidentally. Combined `apply all` / `refresh all` excludes
the MTP category entirely, even when `--include-disabled` is supplied. `bc250-fetch-mtp` is the
explicit opt-in workflow and deliberately exposes those disabled experiment definitions. MTP entries
intentionally have no Ollama Modelfile.

## Current qualification / optimization state

MTP is qualified enough for current package use as an explicit opt-in **standalone llama.cpp runtime** on the
BC-250 with the reviewed external llama.cpp Vulkan runtime. It is **not** part of normal installer
convergence and no active production role depends on it.

Current evidence summary:

```text
qwen3.5-9b-mtp             PASS   fastest absolute model; strongest short-generation gains
qwen3.6-27b-mtp            PASS   strongest sustained gain of the original set; tightest passing memory margin
qwen3.8-27b-hauhaucs-mtp   PASS   more memory headroom; excellent deterministic/parity behavior
qwen3.8-27b-ymq-xs-ti-mtp  PASS   faster baseline decode and stronger long-form absolute MTP throughput than HauhauCS in the reviewed run
```

The retired 35B-A3B result is a baseline/model-fit safety failure, not an MTP speed failure: the
first baseline load crossed the 128 MiB hard floor before speculative inference began. Its exact
definition remains in `graveyard.toml` for source history, but it is not installed or discovered by
the active MTP workflow and should not be rerun unchanged.

The first long Phase-2 draft-depth campaign accidentally repeated catalog defaults and is **not**
valid for depth selection. It is retained as repeatability/noise-floor evidence: typical throughput
CV was approximately 0.01–0.19%, so sub-percent differences should not drive package defaults. The
corrected hardware canary proved requested draft depth reaches the emitted llama-server flags, and
the corrected sweep then applied depths 1, 2, 3 and 4 successfully to all three original passers.

Current draft-depth conclusions:

```text
qwen3.5-9b-mtp             packaged depth 3; depth 2 is the strongest exploratory candidate
qwen3.6-27b-mtp            keep depth 2
qwen3.8-27b-hauhaucs-mtp   keep depth 2
qwen3.8-27b-ymq-xs-ti-mtp  qualified at depth 2; further depth tuning is optional only if preferred-role promotion is contemplated
```

Qwen3.5 depth 2 showed a material exploratory advantage (about +4% balanced versus depth 3 and a
much larger long-generation gain than the default), well above the measured noise floor. Keep the
packaged depth-3 default until confirmation-grade repeats are available if changing the default is
important. Do not repeat the full sweep merely to reconfirm already-settled models.

YMQ XS-TI qualified with deterministic baseline/MTP quality parity and clean safety/restoration.
Compared with the earlier HauhauCS Qwen3.8 evidence, YMQ had roughly 4–5% faster baseline decode and
better absolute MTP throughput at longer generations, but somewhat lower observed memory headroom.
GGUF file size is therefore not a sufficient runtime-memory proxy.

Further MTP work is optional and question-driven only:

- confirm Qwen3.5 depth 2 with 3 performance repeats / 2 quality repeats at 256 and 1024 tokens only
  if changing the package default matters;
- run a same-current-package HauhauCS comparator only if a rigorous YMQ/HauhauCS memory comparison is
  required;
- explore YMQ depth 1 only if YMQ is being considered for a preferred package role.

The packaged entries remain `enabled = false`; MTP stays explicit opt-in and separate from normal
model convergence. Broad MTP qualification should not be reopened without a materially new product,
model, runtime or hardware question.

## Prepare one experiment

```bash
bc250-model list mtp --all
sudo bc250-fetch-mtp qwen3.5-9b-mtp
sudo bc250-model status mtp qwen3.5-9b-mtp --include-disabled --verbose
```

With no selection, `sudo bc250-fetch-mtp` shows the disabled candidates and prompts for
one. Long-lived scripts and recorded evidence should use the exact ID rather than a
displayed index or convenience alias.

`bc250-fetch-mtp` is equivalent to an explicit lifecycle apply of the MTP catalog with
disabled entries exposed. Advanced/operator testing can use the underlying form directly:

```bash
sudo bc250-model apply mtp qwen3.5-9b-mtp --include-disabled
sudo bc250-model refresh mtp qwen3.5-9b-mtp --include-disabled
sudo bc250-model remove mtp qwen3.5-9b-mtp
```

MTP has no Ollama registration, so `unregister mtp` is intentionally rejected. `remove`
deletes only the manager-owned MTP GGUF/state after confirmation and keeps the catalog
definition. `path mtp ID` remains the machine-readable source/context/draft resolver used
by the runner.

Files are stored below `/var/lib/bc250-llm-server/gguf/mtp/`.

## Runtime preflight

The RPM does not provide llama.cpp. The reviewed baseline is release `b10964`
(commit `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`), but another release is accepted
when its CLI supports the required MTP, cache, context, GPU-offload and flash-attention
options. Every qualification run must capture the exact executable/build and flags.

`bc250-run-mtp` now performs a bounded fail-fast preflight before launch:

- resolves the exact MTP catalog entry and refuses a missing source;
- snapshots every reachable package Ollama lane (`11434`-`11437`) and drains all resident models
  before measuring launch headroom or starting llama.cpp;
- verifies protected manager state is `CURRENT` and records the source SHA-256;
- rejects an occupied MTP port or another stale `llama-server` process;
- enforces a configurable `MemAvailable` launch floor (default 2048 MiB);
- validates required llama.cpp CLI options;
- verifies the `ollama` service user can execute the external runtime and read the GGUF;
- launches `llama-server` as `ollama`, never as root.

A direct operator `bc250-run-mtp` owns this temporary lifecycle: after llama.cpp exits it restores the
exact pre-run Ollama residency set and lets each lane's configured keep-alive policy apply. The
comparison/qualification harness sets `BC250_MTP_RESIDENCY_POLICY=drain-only`; those isolated runs
intentionally do **not** rewarm Ollama afterward. Neither path stops/reconfigures Ollama services or
changes normal/agent topology.

Manual launch remains useful for diagnosis:

```bash
LLAMACPP=/opt/llama.cpp/build/bin/llama-server \
bc250-run-mtp qwen3.5-9b-mtp
```

For a controlled non-speculative baseline of the exact same target/settings:

```bash
LLAMACPP=/opt/llama.cpp/build/bin/llama-server \
bc250-run-mtp --no-mtp qwen3.5-9b-mtp
```

Exact IDs are preferred. Convenience aliases exist only for interactive use:
`qwen35-9b`, `qwen36-27b`, `qwen38-27b`. The YMQ challenger intentionally has no convenience
alias; use exact ID `qwen3.8-27b-ymq-xs-ti-mtp` in evidence. Retired MTP entries have no alias and
are not accepted by the active runner.

`PORT`, `CTX` and `DRAFT_N_MAX` override catalog values. `UBATCH=384` remains an explicit
gfx1013 stability-control A/B only when the affected model/runtime path warrants it; an
unset `UBATCH` preserves the runtime default. `MIN_MEM_AVAILABLE_MIB` may be changed only
as an explicitly recorded experiment, not merely to bypass a failed safety preflight.

When supported, the runner adds `--cache-ram 0` and `--no-cache-idle-slots` alongside
`--parallel 1` to avoid shared serialized prompt-cache state and its RAM reservation.

## Controlled same-model comparison

For qualification, prefer the package comparison harness rather than manually comparing
against an unrelated Ollama model:

```bash
LLAMACPP=/opt/llama.cpp/build/bin/llama-server \
bc250-compare-mtp qwen3.5-9b-mtp
```

It runs the **same target GGUF** sequentially with the same llama.cpp build, context,
cache/KV, ubatch and request settings:

1. baseline: MTP disabled;
2. candidate: `--spec-type draft-mtp` with the catalog draft limit.

Before either comparison phase, the runner verifies Ollama residency is drained. Comparison evidence
uses `drain-only` residency policy and leaves the appliance cold afterward by design; this is the
specialist benchmark isolation contract, not the direct operator-run restoration contract.

The default comparison performs three identical requests per phase and writes one evidence
directory plus a `.tar.gz`. The bundle contains package/runtime identity, verified model
status/SHA, exact server logs/flags, per-request responses/timing, sampled MemAvailable and
swap, accepted/proposed draft counts, speedup, kernel journal evidence and cleanup state. It also
records catalog/requested/effective draft depth and refuses MTP evidence when the requested depth
is not present in the actual llama-server flags. The baseline phase is likewise checked to ensure
MTP was not accidentally enabled.

The comparison fails closed when completion integrity is invalid, the server dies, severe
GPU/kernel fault evidence is observed, or MTP draft-acceptance telemetry is absent. Missing
acceptance telemetry may still describe valid inference, but it is insufficient evidence
to qualify speculative decoding.

Do not claim an MTP win from tok/s alone. Final qualification still requires useful answer
quality, draft acceptance, memory/swap behavior, gfx1013 stability and clean normal-appliance
state after the run. After this pre-flight polish, do not extend the framework again until
real BC-250 evidence identifies a concrete measurement or runtime defect.
