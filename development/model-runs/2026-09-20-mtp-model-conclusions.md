# MTP model conclusions — final package selection

ID: MTP-CONCLUSION-20260920
Status: PROMOTED / RETIRED
Evidence package: BC-250 campaigns through installed 0.11.3-1.7 using reviewed external llama.cpp commit `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`; summarized from operator-supplied conclusion. Raw bundles were not independently re-opened for this source integration.
Role: standalone opt-in llama.cpp speculative decoding

## Package selection

| Model | Policy | Context | Draft |
|---|---|---:|---:|
| `qwen3.5-9b-mtp` | primary fast | 16384 | 2 |
| `qwen3.8-27b-ymq-xs-ti-mtp` | primary general 27B | 8192 | 1 |
| `qwen3.8-27b-hauhaucs-mtp` | specialist alternative | 8192 | 2 |
| `qwen3.6-27b-mtp` | retired legacy | 8192 | 2 historical |
| `qwen3.6-35b-a3b-mtp` | retired / does not fit stock envelope | 8192 tested | 2 tested |

## Decision evidence

Qwen3.5 depth 2 and depth 3 were directly compared on installed 1.7. At 256 tokens throughput was effectively equal; at 1024 tokens depth 2 reached about 52.8 tok/s versus 48.4 tok/s for depth 3, with higher acceptance and slightly better memory headroom. Both passed deterministic parity-quality checks.

YMQ depth 1 produced about 24.0 tok/s at 256 and 23.8 tok/s at 1024 with roughly 65% acceptance at both points and about 2.8--3.0 GiB free-memory class. The advantage over depth 2 was materially larger than the established sub-percent repeated-run noise floor. A symmetric three-repeat confirmation is optional, not a package gate.

HauhauCS remains useful as the short-output/parity specialist. Qwen3.6 27B retains valid historical MTP qualification but no longer has a strong user-facing niche: optimized Qwen3.8 choices provide better absolute throughput, more memory headroom and better reasoning completion efficiency. The 35B-A3B stock 8K/full-GPU baseline fell below the 128 MiB hard floor before MTP inference and remains retired.

## Package consequence

The active MTP catalog owns only the three current choices and carries `role` / `recommendation` metadata for operator presentation. All remain disabled/download-only and outside normal installer/Open WebUI/Ollama convergence. Retired definitions remain source-only in `graveyard.toml`; no automatic promotion/retirement machinery is introduced. Broad MTP qualification is closed unless a materially new product/runtime/hardware question appears.
