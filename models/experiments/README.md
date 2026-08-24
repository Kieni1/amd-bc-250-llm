# Experimental model tools

Experimental models are intentionally separate from the production list. They
are discovered from `exp-*.Modelfile` templates in the shared packaged tree and
the operator drop-in directory.

```bash
bc250-model list experiments
sudo bc250-fetch-experiments
```

Names include model family, source and quantization, for example
`exp-qwen35-9b-unsloth-q6-k` and
`exp-gpt-oss20b-davidau-neo-mxfp4-moe4`.
The disabled evaluation set also includes
`exp-lfm25-8b-a1b-liquidai-q6-k`, `exp-qwen3-8b-qwen-q6-k` and
`exp-qwen36-14b-a3b-tvall43-fablevibes-q4-k-m`.

The `# Source:` revision accepts a commit, tag or branch such as `main`. Use
`latest` to follow the repository's default revision. Moving revisions favor
freshness over reproducibility; use `--refresh` to check them again.

Test quality, full GPU residency, cold load, context scaling and sustained
correctness before exposing any experiment in Open WebUI. The benchmark command
starts by asking whether to show regular, experimental or all registered models:

```bash
bc250-benchmark
```

MTP downloads are a separate feature and catalog; see
[`../mtp/README.md`](../mtp/README.md).
