# Ollama

The Ollama binary is reconciled from the pinned upstream release by `bc250 install`, while the RPM owns all four systemd lane definitions.

Package standard: **Ollama v0.40.13**. The helper installs this version unless `OLLAMA_VERSION` is deliberately overridden. Release 1.12 refreshed and DEVICE-qualified the runtime bytes without changing the four-lane service topology, context/KV-cache profiles, Vulkan/iGPU selection, keep-alive policy or model set; release 1.13 carries that accepted runtime baseline unchanged. Ollama 0.40.9 improved failure reporting for streamed OpenAI/Anthropic-compatible generation, 0.40.12 updated llama.cpp, and 0.40.13 adds Linux/Windows LFM3 runtime support. LFM3 support is runtime capability only and does not promote a new BC-250 model.

## Install and verify

```bash
sudo bc250 install
ollama --version
sudo systemctl status ollama.service --no-pager -l
curl -fsS http://127.0.0.1:11434/api/version
```

The helper installs the exact package-qualified Linux payload under `/usr/local`. `runtime.env` pins
the release asset URL and SHA-256, and the helper verifies the archive before extraction. It removes the
old `/usr/local/lib/ollama` payload before extracting the replacement, while the RPM-owned systemd units
and lane environment remain authoritative. A recognizable old upstream-generated `/etc/systemd/system/ollama.service`
may be removed; an unknown/custom override is refused rather than overwritten.

After installation the helper starts normal main/task/embedding topology and requires `/api/version` on
ports 11434, 11435 and 11437 to report the exact package version. The exclusive agent lane remains
operator-entered. This deliberately avoids running upstream `install.sh`, which could create service state
that supersedes the appliance-owned unit.

Non-package Ollama payload experiments are development/qualification work and are intentionally not exposed as an appliance command.


The main service uses:

```text
HOME=/var/lib/ollama
OLLAMA_MODELS=/var/lib/bc250-llm-server/ollama/main
OLLAMA_HOST=0.0.0.0:11434
```

The package owns a fixed four-lane service topology. A completed normal appliance runs main, task and embedding; agent remains static/inactive until explicitly entered:

| Lane | Port | Keepalive | Normal boot | Purpose |
|---|---:|---|---|---|
| main | 11434 | `20m` | yes | production chat/RAG answers; keep warm for interactive latency |
| task | 11435 | `0` | yes | Open WebUI title/tag tasks |
| embedding | 11437 | `10m` | yes | retrieval embeddings only |
| agent | 11436 | `5m` | **no** | exclusive coding/agent work |

`ollama-agent.service` has no boot enablement and conflicts with main/task/embedding. The normal lanes also conflict with the agent, so systemd enforces the mode boundary. Use `sudo bc250 advanced agent enter` before coding work and
`sudo bc250 advanced agent leave` afterwards. All lanes share the same BC-250 UMA
pool; the separation controls lifecycle and eviction, not physical memory.
The compact task model remains ephemeral while the main chat model stays warm. This is
intentional: real-device testing showed that the retired task candidate
`exp-qwen38-4b-distill-empero-q6-k` can OOM the task service when it overlaps GPT-OSS,
while making the main lane ephemeral adds a large cold-start penalty to normal chat.
That exact Distill candidate is now retired-source only, not an opt-in packaged
experiment. The similarly named active `exp-qwen38-4b-empero-q6-k` is a separate
general comparison. GPT-OSS 20B with warm Jina remains the production memory-edge
qualification; re-run it when a package/runtime change could affect residency or UMA
headroom.

## 0.40.13 settings audit

The 0.40.13 source still exposes the package's existing lane controls directly: `OLLAMA_VULKAN`,
`OLLAMA_IGPU_ENABLE`, `GGML_VK_VISIBLE_DEVICES`, `OLLAMA_CONTEXT_LENGTH`,
`OLLAMA_KV_CACHE_TYPE`, `OLLAMA_NUM_PARALLEL`, `OLLAMA_MAX_LOADED_MODELS`,
`OLLAMA_KEEP_ALIVE`, `OLLAMA_MODELS`, `OLLAMA_HOST` and `OLLAMA_NO_CLOUD`. The 1.13 package retains the 1.12 DEVICE-accepted four-lane values rather than translating them to new knobs.

Ollama also exposes llama.cpp automatic-fit controls (`LLAMA_ARG_FIT` /
`LLAMA_ARG_FIT_TARGET`) and queue/load/transfer tuning. BC-250 leaves those at upstream defaults:
there is no accepted evidence that overriding the fit target, load timeout, request queue or transfer
parallelism improves this UMA appliance, and pre-emptively pinning them would turn a runtime refresh
into an unrelated scheduler policy change. Recheck model placement, UMA headroom and load behavior on
the exact 0.40.13 DEVICE build before promoting any such tuning.

## 0.40.13 runtime and prior device baseline

Ollama 0.40.13 is the package-pinned runtime. The exact 1.4 device campaign on 0.40.6 proved package-created registrations remained unique and usable before and after supported restart, with no unexpected `llamacpp:` shadow name for the main package-owned registration. Keep those invariants for 0.40.13, and additionally record the 0.40.7+ `renderer`, `parser` and `template_source` fields from `/api/show` as semantic diagnostics. Do not delete or rewrite model-store state merely to make a check pass.
Main generation, task generation, Jina embedding, 8192-context recall, bounded long generation, Deep-to-task
transition and Open WebUI Documents/RAG all passed without kernel/GPU/OOM regression. Most measured workloads
were flat or modestly faster; GPT-OSS decode was about 5% slower but remained within the accepted appliance
envelope. `/api/tags` was measurably slower on this device but only by tens of milliseconds.

The focused Vulkan/UMA, `/api/show`, structured-output and large-library lookup checks were part of the runtime promotion campaign and later exact-device qualification. Those results plus the 1.4 device campaign are historical/baseline evidence for later changed package bytes. Re-run the bounded runtime boundaries that can regress: all normal lanes, local GGUF registration/show/run/restart, embedding, representative long generation, Deep/task transition and memory headroom.

The earlier runtime upgrade also demonstrated why serialized `/api/show` Modelfile/parameter text is not immutable model
identity: those strings can change while canonical model names, sizes and digests remain unchanged. Package
checks therefore use the supported runtime version and stable model/digest provenance rather than old textual
serialization.

The package continues to use the experimental Vulkan backend on BC-250. The stock clean-core verifier requires the effective main Ollama service environment to contain all three package settings:

```text
OLLAMA_VULKAN=1
OLLAMA_IGPU_ENABLE=1
GGML_VK_VISIBLE_DEVICES=0
```

These settings select the intended stock Vulkan/iGPU path and are part of the normal appliance configuration. The 0.40.13 review found no upstream change requiring different values for `OLLAMA_VULKAN=1`, `OLLAMA_IGPU_ENABLE=1`, `GGML_VK_VISIBLE_DEVICES=0`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`, Flash Attention, keep-alive policy, or the package's q8/q4 KV-cache profiles. Keep those settings unless exact BC-250 evidence shows a regression.

Ollama 0.40.12 updated llama.cpp; the completed 1.12 DEVICE campaign exercised the 0.40.13 runtime across normal lanes, streaming/residency/error handling and combined RAG without a runtime regression. The 1.13 package does not change those runtime bytes, so DEVICE retesting should focus on the package-owned surfaces changed by 1.13 unless later work alters model/runtime configuration. The 0.40.9 streaming-failure improvement is also a reason to keep benchmark completion/error oracles strict rather than accepting partial output as success.

For more accurate Vulkan free-memory information the upstream docs suggest `cap_perfmon`; this package does **not** grant that capability automatically. An operator may test it deliberately after locating the real binary:

```bash
command -v ollama
sudo setcap cap_perfmon+ep "$(command -v ollama)"
getcap "$(command -v ollama)"
```

Granite 4.2 needs special context discipline on small shared-memory systems: its
GGUF advertises 128K context and an open 0.33.x upstream report documents OOMs on
<=16 GB hosts when that full value is selected. The packaged Granite experiments
therefore retain explicit `PARAMETER num_ctx 32768`; do not remove that bound for
BC-250 comparison runs.

## Runtime profiles

```bash
bc250 advanced ollama-profile status
sudo bc250 advanced ollama-profile balanced
sudo bc250 advanced ollama-profile max-context
sudo bc250 advanced ollama-profile reset
```

| Profile | Context | KV cache | Parallel/loaded models |
|---|---:|---|---|
| Balanced | 32,768 | q8_0 | 1 / 1 |
| Max context | 65,536 | q4_0 | 1 / 1 |

Both enable flash attention. `balanced` is the production default. `max-context` remains an explicit operator profile for 65,536-token experiments/needs; its q4_0 KV setting was **not** promoted to the production default after integrated acceptance found Advanced/Qwen instability at the 6,144-token reasoning ceiling. Service profiles do not modify individual Modelfiles.

## Benchmark API baseline

`bc250 advanced benchmark` targets the package-pinned Ollama **0.40.13** request schema. Neutral generation
uses the top-level `/api/generate` `system` override without `raw=true`; production
mode omits the override. `think` may be omitted, boolean, or
`low`/`medium`/`high`/`max` where supported by the pinned runtime/model. Embedding tests use `/api/embed` with `truncate=false` on the dedicated 11437
lane; RAG-quality uses 11437 for vectors and 11434 for the answer model. Model
allocation comes from `/api/ps`. The `bc250 advanced benchmark agent` lane and `bc250 advanced code run`
product helper use `/api/chat` on exclusive port 11436. `bc250 advanced code run` requests
`think:true`, consumes only final `message.content`, and fails closed on nonterminal or
output-limit-truncated completion instead of writing a partial file.

The benchmark samples BC-250 temperature and memory/AMDGPU counters during each
request. `RUN_THERMAL=1` adds sustained decode windows; no second `watch` terminal
is required for peak resource values.

## Network exposure

The host listeners let rootful Open WebUI reach Ollama. They are unauthenticated
and must remain blocked from untrusted networks:

```bash
sudo firewall-cmd --list-all
ss -ltnp | grep -E ':(11434|11435|11436|11437)\b'
```

## Updating safely

Treat **0.40.13** as the package-standard runtime for this release. Before accepting the selected RPM, review
release notes and smoke-test each Vulkan update with:

1. a small known-good model;
2. the largest intended model;
3. a representative long prompt; and
4. `sudo bc250 verify` plus the kernel journal.

```bash
BC250_UPDATE_OLLAMA=1 sudo -E bc250 install
sudo bc250 verify
# Comparison/rollback payloads require explicit VERSION + URL + SHA-256; never follow a moving installer.
```

Recent upstream AMD shared-memory reports include Vulkan device loss,
command-submission memory failures and compute-ring timeouts. Verification
prints the exact Ollama version and scans recent Ollama/kernel logs for those
patterns. A smaller `PARAMETER num_batch 128` in a copied operator Modelfile is
a diagnostic for long-prompt prefill failures, not a package-wide default or a
confirmed BC-250 fix.
