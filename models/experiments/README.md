# Experimental models

```bash
sudo bc250-model list experiments
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

The 0.9.7-0.11 catalog deliberately retains the operator's broader comparison
pool for the next full BC-250 rerun. Qwen/Gemma derivatives that may prove
redundant remain available until that measured comparison is complete. Newer
Granite 4.2 3B/8B and Ling 3.0 Tiny definitions extend the architecture and
size coverage without changing production defaults.

The 2026-08-31 BC-250 generation rerun makes several candidates easier to
place. Qwen3.8 4B Distill (~74.5 tok/s, ~4.0 GiB) and Granite 4.2 3B (~91.5
tok/s, ~4.1 GiB) remain useful compact comparisons. Granite 4.2 8B (~50.3
tok/s, ~8.3 GiB) is exhausted as a production-promotion candidate unless a
future role-quality test shows a large advantage. Ling 3.0 Tiny decoded at about
144 tok/s but repeatedly spent the shared cap in reasoning before a usable final
answer, so it is likewise exhausted as an ordinary assistant promotion path.
The definitions stay packaged for reproducible comparisons; see `MODELS.md` for
the complete benchmark-status table.

Local-GGUF source revisions may be commits, tags, branches or `latest`. Moving
revisions favor flexibility over reproducibility; use `--refresh` to download
those manager-owned sources again. Vision/OCR `hf.co/...` sources are Ollama-managed instead because these
models require a vision projector in addition to the main GGUF. They therefore
do not appear as manager-owned source files under `/var/lib/bc250-llm-server/gguf/`;
`bc250-model list` labels their source as `Ollama-managed (main+projector)`. This
is intentional in 0.10: GLM-OCR is a ~950 MB main GGUF plus a ~484 MB projector,
and OvisOCR2 likewise requires a separate projector. Ollama 0.33.3 does not offer
a reliable local Modelfile import path for attaching an arbitrary separate
projector, so copying only the main OCR GGUF into the package source tree would
create a backup that cannot be safely restored. Keep these two OCR models in the
Ollama store until that local multimodal import path is dependable.

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

The packaged OCR set is GLM-OCR Q8_0 plus OvisOCR2 Q8_0. On the 2026-08-31
three-document office fixture, GLM remained the clear fidelity winner (about
0.996 mean word F1 with perfect field recall) while Ovis was faster but much
less precise (about 0.735 mean word F1). Ovis remains a speed-oriented
structured-page alternative. They stay experiments on the main Ollama instance.
Always verify representative DE/FR/EN scans before choosing an ingestion path.
