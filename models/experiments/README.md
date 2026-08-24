# Experimental models

```bash
bc250-model list experiments
sudo bc250-fetch-experiments
bc250-benchmark
```

Experiments are discovered from `exp-*.Modelfile` templates and remain separate
from the production selection. The current packaged set is:

```text
exp-gemma4-12b-google-qat-q4-0
exp-gemma4-12b-hauhaucs-uncensored-q4-k-m
exp-gemma4-e4b-hauhaucs-aggressive-q6-k-p
exp-gpt-oss20b-davidau-neo-mxfp4-moe4
exp-ministral3-8b-unsloth-ud-q5-k-xl
exp-qwen3-4b-lmstudio-q6-k
exp-qwen35-4b-unsloth-q6-k
exp-qwen35-9b-davidau-defiant-fable-q6-k
exp-qwen35-9b-hauhaucs-uncensored-q6-k
exp-qwen36-14b-a3b-tvall43-fablevibes-q4-k-m
exp-qwen38-9b-distill-empero-q5-k-m
exp-qwythos9b-v2-empero-q5-k-m
```

Source revisions may be commits, tags, branches or `latest`. Moving revisions
favor flexibility over reproducibility; use `--refresh` to download them again.

Compare answer quality, full GPU residency, cold load, context scaling,
temperature and sustained correctness before treating an experiment as a new
default. MTP is a separate download-only llama.cpp workflow; see
[`../mtp/README.md`](../mtp/README.md).
