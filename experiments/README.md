# Experimental model tools

Experimental models are intentionally separate from the regular office list.
The RPM installs every experimental Modelfile in this directory and a commented
catalog in `/etc/bc250-llm-server/experiment-sources.sh`.

```bash
sudoedit /etc/bc250-llm-server/experiment-sources.sh
sudo bc250-fetch-experiments
```

Names include model family, source and quantization, for example
`exp-qwen35-9b-unsloth-q6-k` and `exp-gpt-oss20b-unsloth-ud-q4-k-xl`.

The revision field accepts a commit, tag or branch such as `main`. Use `latest`
to follow the repository's default revision without passing `--revision` to
Hugging Face. Moving revisions favor freshness over reproducibility.

Test quality, full GPU residency, cold load, context scaling and sustained
correctness before exposing any experiment in Open WebUI. The benchmark command
starts by asking whether to show regular, experimental or all registered models:

```bash
bc250-benchmark
```

MTP examples are kept in `mtp-sources.example.sh`; copy a line into the editable
source list before using `run-mtp-llamacpp.sh`.
