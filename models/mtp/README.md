# MTP models

MTP entries are optional **download-only** llama.cpp experiments. They are not Ollama
role models and remain excluded from normal `apply all` / installer convergence until
real BC-250 qualification justifies a stronger integration decision.

The packaged entries are intentionally `enabled = false`. That means ordinary
`bc250-model list mtp`, `apply mtp` and combined-catalog operations do not select them
by accident. `bc250-fetch-mtp` is the explicit opt-in workflow and deliberately exposes
those disabled experiment definitions.

## Prepare one experiment

```bash
bc250-model list mtp --all
sudo bc250-fetch-mtp qwen3.6-27b-mtp
sudo bc250-model status mtp qwen3.6-27b-mtp --include-disabled --verbose
```

With no selection, `sudo bc250-fetch-mtp` shows both candidates and prompts for one.
Long-lived scripts should use the exact ID rather than the displayed index. The two
current IDs are:

```text
qwen3.6-27b-mtp
qwen3.5-4b-mtp
```

`bc250-fetch-mtp` is equivalent to an explicit lifecycle apply of the MTP catalog with
disabled entries exposed. Advanced/operator testing can use the underlying form directly:

```bash
sudo bc250-model apply mtp qwen3.6-27b-mtp --include-disabled
sudo bc250-model refresh mtp qwen3.6-27b-mtp --include-disabled
sudo bc250-model remove mtp qwen3.6-27b-mtp
```

MTP has no Ollama registration, so `unregister mtp` is intentionally rejected. `remove`
deletes only the manager-owned MTP GGUF/state after confirmation and keeps the catalog
definition. `path mtp ID` remains the machine-readable source/context/draft resolver used
by the runner.

Files are stored below `/var/lib/bc250-llm-server/gguf/mtp/`.

## Run and compare

The RPM does not provide llama.cpp. The reviewed baseline is release `b10069`
(commit `178a6c44937154dc4c4eff0d166f4a044c4fceba`), but another release is accepted
when its CLI supports the required MTP, cache, context, GPU-offload and flash-attention
options. The exact executable/build/flags must be captured as qualification evidence.

```bash
LLAMACPP=/path/to/llama-server bc250-run-mtp 27b

# In another terminal, after the server is ready:
bc250-compare-mtp
```

The runner accepts `27b`, `4b` or the full ID and binds to `127.0.0.1:8090` by default.
It prints the exact executable, version/build text, launch flags, KV types and effective
ubatch before starting the server. `PORT`, `CTX` and `DRAFT_N_MAX` override catalog
values. `UBATCH=384` is an explicit gfx1013 stability-control A/B only when the affected
model/runtime path warrants it; an unset `UBATCH` preserves the runtime default.

When supported, the runner adds `--cache-ram 0` and `--no-cache-idle-slots` alongside
`--parallel 1` to avoid shared serialized prompt-cache state and its RAM reservation.

`bc250-compare-mtp` fails nonzero when either backend lacks a valid terminal state, has
no usable completion text/reasoning, or emits a pathological repeated reserved/unused
token run. Accepted/proposed draft tokens and acceptance rate are reported when
available. Missing acceptance telemetry does not make otherwise valid inference corrupt,
but it is insufficient evidence for MTP qualification.

Do not claim an MTP win from tok/s alone. Final qualification still requires useful
answer quality, draft acceptance, memory/swap behavior, stability/journal evidence and
restoration of the normal appliance topology.
