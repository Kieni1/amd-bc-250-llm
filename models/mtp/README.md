# MTP models

MTP entries are optional download-only llama.cpp inputs. Both are disabled by
default and remain in TOML because they have runtime fields but no Ollama name
or Modelfile.

```bash
sudoedit /etc/bc250-llm-server/mtp-models.toml
bc250-model list mtp --all
sudo bc250-fetch-mtp
LLAMACPP=/path/to/llama-server bc250-run-mtp 27b
```

Enable the intended entry in the TOML before downloading. Current IDs are:

```text
qwen3.6-27b-mtp
qwen3.5-4b-mtp
```

The runner accepts `27b`, `4b` or the full ID and binds to
`127.0.0.1:8090` by default. Files are stored below
`/var/lib/bc250-llm-server/gguf/mtp/`.

The RPM does not provide llama.cpp. The reviewed baseline is release `b10069`
(commit `178a6c44937154dc4c4eff0d166f4a044c4fceba`), but another release is
accepted when its CLI supports the required MTP, cache, context, GPU-offload
and flash-attention options. `PORT`, `CTX` and `DRAFT_N_MAX` override catalog
values. Treat quality and stability as experimental.
