# MTP models

MTP entries are optional **download-only** standalone llama.cpp models. They are not Ollama
role models and remain deliberately excluded from normal `apply all` / installer convergence.
BC-250 qualification now defines their package-facing roles and defaults without turning MTP into a
persistent production lane.

The packaged entries are intentionally `enabled = false`. Ordinary `bc250-model list mtp` and
`apply mtp` therefore do not select them accidentally. Combined `apply all` / `refresh all` excludes
the MTP category entirely, even when `--include-disabled` is supplied. `bc250-fetch-mtp` is the
explicit opt-in workflow and deliberately exposes those disabled experiment definitions. MTP entries
intentionally have no Ollama Modelfile.

## Current package policy

Broad MTP qualification is closed for the current BC-250/runtime combination. The active catalog
contains only the choices that still have a clear operator role:

```text
qwen3.5-9b-mtp             primary / fast         ctx 16384  draft 2
qwen3.8-27b-ymq-xs-ti-mtp  primary / general-27b  ctx 8192   draft 1
qwen3.8-27b-hauhaucs-mtp   alternative / specialist ctx 8192 draft 2
```

`role` and `recommendation` are package-policy metadata in the existing MTP catalog. They are
displayed by `bc250-model list mtp --all`; they do not make an entry enabled, production-resident,
or part of generic convergence. Context and draft defaults remain runtime metadata consumed by the
existing `bc250-model path` / `bc250-run-mtp` path. No separate recommendation database or automatic
promotion mechanism exists.

Qwen3.5 depth 2 is the final package default: confirmation-grade 1.7 testing kept short-output
throughput effectively equal to depth 3 while improving 1024-token MTP throughput by about 9%, with
higher acceptance, slightly better memory headroom and clean parity-quality evidence.

YMQ XS-TI is the preferred general 27B choice at depth 1. The reviewed depth-1 point improved both
short and long MTP throughput over depth 2, retained about 2.8--3.0 GiB free-memory class, and passed
the parity-quality screen. A symmetric three-repeat depth-1 confirmation is optional evidence, not a
package-release gate.

HauhauCS remains a defensible specialist alternative at depth 2 because it has the strongest tested
short-output 27B point and unusually strong exact baseline/MTP output parity.

`qwen3.6-27b-mtp` is retired from the active/recommended lane because optimized Qwen3.8 choices now
provide better absolute throughput, memory headroom and completion efficiency. Its historical passing
qualification remains valid and its exact definition is preserved in source-only `graveyard.toml`.
`qwen3.6-35b-a3b-mtp` also remains in the graveyard: stock 8K/full-GPU loading crossed the 128 MiB
whole-appliance hard floor before MTP inference, so that configuration should not be rerun unchanged.

The packaged active entries remain `enabled = false`; MTP stays explicit opt-in and separate from
normal model convergence. Do not reopen broad MTP qualification without a materially new product,
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

Exact IDs are preferred. Only the unambiguous `qwen35-9b` convenience alias remains for interactive
use. Use exact IDs for 27B models so a future package-policy change cannot silently retarget an
alias. Retired MTP entries have no alias and are not accepted by the active runner.

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
