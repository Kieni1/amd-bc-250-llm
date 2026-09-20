# 2026-09-20 Qwen3.8 27B IQ3_XXS RAG follow-up

This record preserves operator-supplied BC-250 campaign results used to refine the package model
definition. The source handoff did not include the raw evidence archive, so the numbers below are
recorded as supplied evidence rather than independently re-derived by this source release. They do
not qualify `0.11.3-2.1` package bytes.

## Platform / candidate

- AMD BC-250 / Cyan Skillfish, modified 40-CU configuration
- approximately 16 GiB unified memory
- Ollama 0.34.0
- candidate: `exp-qwen38-27b-ista-gsq-rco-iq3-xxs`
- source GGUF: `Qwen3.8-27B-GSQ-RCO-IQ3_XXS.gguf`, approximately 10.1 GB
- tested context: 16384
- `num_predict=1024`, `think=false`
- campaign safety threshold: 512 MiB MemAvailable

## 16K result

The first five RAG qualification cases were answered correctly, including citations. Memory
headroom declined progressively:

| Point | Approx. MemAvailable |
|---|---:|
| early resident state | 3.17 GiB |
| after case 2 | 2.47 GiB |
| after case 3 | 1.93 GiB |
| after case 4 | 1.29 GiB |
| after case 5 | 0.67 GiB |
| before next request | 0.28 GiB |

The safety harness aborted before OOM. After unloading the model, MemAvailable recovered to
approximately 13.8 GiB.

## Decision

The 16K configuration is not production-safe on the current 16 GiB profile. Five correct cases are
encouraging but insufficient for a broad quality conclusion. Keep the model experimental. Reuse the
same verified model identity/GGUF and bound its package default to 8K rather than creating a second
`-8k` identity. Production RAG remains `bc250-office-documents` /
`prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl`.

A future 8K run is justified only if the experiment still answers a current product question; it is
not a release gate and does not reopen the completed production RAG model tournament.
