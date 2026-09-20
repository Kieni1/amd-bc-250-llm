# RAG qualification conclusion — corrected final decision

ID: RAG-CONCLUSION-20260920
Status: PROMOTED / CLOSED
Evidence package: historical BC-250 campaigns summarized by the operator; raw bundles were not independently re-opened for this source integration.
Role: production document/RAG answer model

## Decision

Keep `bc250-office-documents` / `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` as the production RAG configuration on the current 16 GiB profile. Do not reopen broad answer-model selection without a candidate that materially improves both hard-case quality and resident-memory safety.

## Corrected finalist evidence

Same retrieval policy, two rounds / 96 answerable cases per model:

| Model | Overall | Fact | Language | Citation | Retrieval | Avg | P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Gemma E4B Q4_K_XL | 94/96 | 95/96 | 96/96 | 95/96 | 96/96 | 1.86 s | 2.39 s |
| Qwen3.5 9B Q6_K | 93/96 | 95/96 | 96/96 | 94/96 | 96/96 | 4.26 s | 7.31 s |

Both passed 8/8 abstention probes. Short authenticated Open WebUI RAG was 36/36 for each finalist. Under continuous residency Gemma completed 42/42 valid turns with about 2.7 GiB MemAvailable remaining; Qwen reached the campaign-specific 512 MiB safety threshold during the third subrun after six fully completed valid turns.

## Larger-candidate conclusion

The ISTA Qwen3.8 27B IQ3_XXS 16K experiment passed its first five cited RAG cases but then hit the campaign low-memory safety gate, with telemetry reaching roughly 0.12--0.28 GiB MemAvailable. Unload restored normal memory. This rejects the 16K RAG configuration on the current profile; the same model identity may remain an explicit 8K experiment only.

## Package consequence

- no production RAG model/preset change;
- Qwen3.5 9B remains useful for its separate higher-quality general-office role, not as the long-lived document default;
- GPT-OSS and other experiments are not removed merely for losing the RAG comparison when another role still justifies them;
- future RAG work should focus on real PDF/Tika/OCR/table/multilingual/multi-source/document-lifecycle acceptance with Gemma fixed.
