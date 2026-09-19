# MTP models

MTP entries are optional **download-only** llama.cpp experiments. They are not Ollama
role models and remain excluded from normal `apply all` / installer convergence until
real BC-250 qualification justifies a stronger integration decision.

The packaged entries are intentionally `enabled = false`. Ordinary `bc250-model list mtp` and
`apply mtp` therefore do not select them accidentally. Combined `apply all` / `refresh all` excludes
the MTP category entirely, even when `--include-disabled` is supplied. `bc250-fetch-mtp` is the
explicit opt-in workflow and deliberately exposes those disabled experiment definitions. MTP entries
intentionally have no Ollama Modelfile.

## Current first-campaign set

The first hardware funnel is deliberately small and ordered from the safest useful target
toward the heavier candidates:

```text
qwen3.5-9b-mtp             Unsloth Qwen3.5 9B UD-Q4_K_XL       primary safe candidate
qwen3.6-27b-mtp            Unsloth Qwen3.6 27B UD-Q2_K_XL      retained control
qwen3.8-27b-hauhaucs-mtp   HauhauCS Qwen3.8 27B IQ2_M          Qwen3.8 control (~10.32 GB)
qwen3.8-27b-ymq-xs-ti-mtp  ZeroDigest Qwen3.8 27B YMQ XS-TI    Qwen3.8 challenger (~10.2 GB)
qwen3.6-35b-a3b-mtp        Unsloth Qwen3.6 35B-A3B UD-IQ3_S    heavyweight challenger
```

Test one candidate at a time. Do not preload the whole set merely because it is cataloged.
The catalog `draft` values are conservative first-run settings for this 16 GiB BC-250,
not claims about each upstream model's maximum useful speculative depth. The HauhauCS and
YMQ entries both exercise native/embedded MTP in their selected text GGUFs. HauhauCS is the
Qwen3.8 27B control; YMQ XS-TI is the same-class architecture-aware mixed-precision challenger
with a slightly smaller published file size. The separate HauhauCS FastMTP sidecar is intentionally
outside this first package-owned hardware batch.

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
- verifies protected manager state is `CURRENT` and records the source SHA-256;
- rejects an occupied MTP port or another stale `llama-server` process;
- enforces a configurable `MemAvailable` launch floor (default 2048 MiB);
- validates required llama.cpp CLI options;
- verifies the `ollama` service user can execute the external runtime and read the GGUF;
- launches `llama-server` as `ollama`, never as root.

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
`qwen35-9b`, `qwen36-27b`, `qwen38-27b`, `qwen36-35b`. The YMQ challenger intentionally
has no convenience alias; use exact ID `qwen3.8-27b-ymq-xs-ti-mtp` in evidence.

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

The default comparison performs three identical requests per phase and writes one evidence
directory plus a `.tar.gz`. The bundle contains package/runtime identity, verified model
status/SHA, exact server logs/flags, per-request responses/timing, sampled MemAvailable and
swap, accepted/proposed draft counts, speedup, kernel journal evidence and cleanup state.

The comparison fails closed when completion integrity is invalid, the server dies, severe
GPU/kernel fault evidence is observed, or MTP draft-acceptance telemetry is absent. Missing
acceptance telemetry may still describe valid inference, but it is insufficient evidence
to qualify speculative decoding.

Do not claim an MTP win from tok/s alone. Final qualification still requires useful answer
quality, draft acceptance, memory/swap behavior, gfx1013 stability and clean normal-appliance
state after the run. After this pre-flight polish, do not extend the framework again until
real BC-250 evidence identifies a concrete measurement or runtime defect.
