# Experimental models

```bash
bc250-model list experiments
sudo bc250-fetch-experiments
bc250-benchmark
```

Experiments are discovered from `exp-*.Modelfile` templates and remain separate
from the production selection. The deliberately compact packaged set is:

```text
exp-gemma4-12b-google-qat-q4-0
exp-gemma4-12b-hauhaucs-uncensored-q4-k-m
exp-glm-ocr-ggml-q8-0
exp-ministral3-8b-unsloth-ud-q5-k-xl
exp-ovisocr2-abiray-q8-0
exp-qwen35-4b-unsloth-q6-k
exp-qwen36-14b-a3b-tvall43-fablevibes-q4-k-m
exp-qwen38-4b-distill-empero-q6-k
```

The 0.9.7-0.8 catalog intentionally drops redundant 9B Qwen/Qwythos variants and
OCR candidates that lost the measured office fixture. Keep an experiment only
when it tests a distinct size, architecture, quant/runtime path or use case.
`exp-qwen35-4b-unsloth-q6-k` remains as the same-family baseline for the optional
Qwen3.5 4B MTP workflow; Qwen3.8 4B is the compact current reasoning comparison.

Local-GGUF source revisions may be commits, tags, branches or `latest`. Moving
revisions favor flexibility over reproducibility; use `--refresh` to download
those manager-owned sources again. Vision/OCR `hf.co/...` sources are
Ollama-managed instead.

Compare answer quality, full GPU residency, cold load, context scaling,
temperature and sustained correctness before promoting an experiment. Very large
27B/35B MTP models are not packaged merely because a low-bit quant can approach
16 GB: BC-250 unified-memory headroom, KV/cache and runtime overhead still have
to fit. MTP is a separate download-only llama.cpp workflow; see
[`../mtp/README.md`](../mtp/README.md).

## Office OCR experiments

```bash
bc250-ocr list
sudo bc250-ocr install glm
bc250-ocr test glm PAGE.png
```

The packaged OCR set is now GLM-OCR Q8_0 plus OvisOCR2 Q8_0. GLM was the clear
text-fidelity winner on the packaged office fixture; Ovis remains as the faster
structured-page alternative. They stay experiments on the main Ollama instance.
Always verify representative DE/FR/EN scans before choosing an ingestion path.
