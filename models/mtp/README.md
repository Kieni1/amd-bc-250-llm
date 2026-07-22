# MTP models

MTP models are optional `download-only` llama.cpp inputs. They are kept out of
the Ollama experiment catalog because they have no Ollama name or Modelfile.
Both entries are disabled by default.

```bash
sudoedit /etc/bc250-llm-server/mtp-models.toml
bc250-model list mtp --all
sudo bc250-fetch-mtp
LLAMACPP=/path/to/llama-server bc250-run-mtp 27b
```

Set `enabled = true` for the wanted entry before fetching it. The files are
stored by ID below `/var/lib/bc250-llm-server/gguf/mtp/`. `bc250-run-mtp`
accepts `27b`, `4b` or
the full catalog ID and binds llama.cpp to `127.0.0.1:8090` by default.

The RPM does not provide llama.cpp. The reviewed baseline is llama.cpp release
`b10069` (commit `178a6c44937154dc4c4eff0d166f4a044c4fceba`). The launcher checks the
required MTP, cache, context, GPU-offload and flash-attention options, so a
different release is accepted when its CLI is compatible. `PORT`, `CTX` and
`DRAFT_N_MAX` override the catalog runtime values. Treat MTP quality and
stability as experimental.
