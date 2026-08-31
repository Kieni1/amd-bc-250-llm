# Experimental models

```bash
bc250-model list experiments
sudo bc250-model install experiments
bc250-benchmark
```

Experiments are discovered from `exp-*.Modelfile` templates and remain separate
from the production selection. The current packaged comparison set is:

```text
exp-gemma4-12b-google-qat-q4-0
exp-gemma4-12b-hauhaucs-uncensored-q4-k-m
exp-gemma4-e4b-hauhaucs-aggressive-q6-k-p
exp-glm-ocr-ggml-q8-0
exp-gpt-oss20b-davidau-neo-mxfp4-moe4
exp-granite42-3b-ibm-q6-k
exp-granite42-8b-ibm-q5-k-m
exp-ling30-tiny-bloomer-q5-k-m
exp-ministral3-8b-unsloth-ud-q5-k-xl
exp-ovisocr2-abiray-q8-0
exp-qwen3-4b-lmstudio-q6-k
exp-qwen35-4b-unsloth-q6-k
exp-qwen35-9b-davidau-defiant-fable-q6-k
exp-qwen35-9b-hauhaucs-uncensored-q6-k
exp-qwen36-14b-a3b-tvall43-fablevibes-q4-k-m
exp-qwen38-4b-distill-empero-q6-k
```

The 0.9.7-0.10 catalog deliberately retains the operator's broader comparison
pool for the next full BC-250 rerun. Qwen/Gemma derivatives that may prove
redundant remain available until that measured comparison is complete. Newer
Granite 4.2 3B/8B and Ling 3.0 Tiny definitions extend the architecture and
size coverage without changing production defaults.

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

The packaged OCR set is GLM-OCR Q8_0 plus OvisOCR2 Q8_0. GLM was the clear
text-fidelity winner on the packaged office fixture; Ovis remains as the faster
structured-page alternative. They stay experiments on the main Ollama instance.
Always verify representative DE/FR/EN scans before choosing an ingestion path.
