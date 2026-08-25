# Experimental models

```bash
bc250-model list experiments
sudo bc250-fetch-experiments
bc250-benchmark
```

Experiments are discovered from `exp-*.Modelfile` templates and remain separate
from the production selection. The current packaged set is:

```text
exp-chandra-ocr2-prithivmlmods-q4-k-m
exp-dots-ocr-ggml-q8-0
exp-gemma4-12b-google-qat-q4-0
exp-gemma4-12b-hauhaucs-uncensored-q4-k-m
exp-gemma4-e4b-hauhaucs-aggressive-q6-k-p
exp-gpt-oss20b-davidau-neo-mxfp4-moe4
exp-glm-ocr-ggml-q8-0
exp-ministral3-8b-unsloth-ud-q5-k-xl
exp-ovisocr2-abiray-q8-0
exp-qwen3-4b-lmstudio-q6-k
exp-qwen35-4b-unsloth-q6-k
exp-qwen35-9b-davidau-defiant-fable-q6-k
exp-qwen35-9b-hauhaucs-uncensored-q6-k
exp-qwen36-14b-a3b-tvall43-fablevibes-q4-k-m
exp-qwen38-9b-distill-empero-q5-k-m
exp-qwythos9b-v2-empero-q5-k-m
```

Local-GGUF source revisions may be commits, tags, branches or `latest`. Moving
revisions favor flexibility over reproducibility; use `--refresh` to download
those manager-owned sources again. The vision/OCR `hf.co/...` sources are
Ollama-managed instead.

Compare answer quality, full GPU residency, cold load, context scaling,
temperature and sustained correctness before treating an experiment as a new
default. MTP is a separate download-only llama.cpp workflow; see
[`../mtp/README.md`](../mtp/README.md).

## Office OCR experiments

```bash
bc250-ocr list
sudo bc250-ocr install glm
bc250-ocr test glm PAGE.png
```

The packaged OCR set is GLM-OCR Q8_0, dots.ocr Q8_0, OvisOCR2 Q8_0 and
Chandra OCR 2 Q4_K_M. They remain experiments on the main Ollama instance so
the normal global model indexes, status renderer and cleanup rules still apply.
GLM uses a 16K context for image/table headroom. Chandra stays at Q4_K_M until
its image path proves reliable on the BC-250; a successful model registration is
not treated as an OCR compatibility result. Review each upstream weight license
before office deployment.
