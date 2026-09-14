# MTP models

MTP entries are optional download-only llama.cpp inputs. Both are disabled by
default and remain in TOML because they have runtime fields but no Ollama name
or Modelfile.

```bash
sudoedit /etc/bc250-llm-server/mtp-models.toml
sudo bc250-model list mtp --all
sudo bc250-fetch-mtp
LLAMACPP=/path/to/llama-server bc250-run-mtp 27b
# Only for an affected-path A/B; do not make this a global default:
LLAMACPP=/path/to/llama-server UBATCH=384 bc250-run-mtp 27b
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
and flash-attention options. The runner prints the exact executable, version/build text,
launch flags, KV types and effective ubatch before starting the server. `PORT`, `CTX` and
`DRAFT_N_MAX` override catalog values; `UBATCH=384` is an explicit stability-control run
only when the model/runtime path warrants it, while an unset `UBATCH` preserves the
runtime default. Treat quality and stability as experimental.

`bc250-compare-mtp` fails nonzero when either backend does not reach a valid terminal
state, returns no usable completion text/reasoning, or emits a pathological repeated
reserved/unused-token run. Accepted/proposed draft tokens and acceptance rate are
reported when available; missing acceptance telemetry does not make valid inference
corrupt, but it is insufficient evidence for MTP qualification. MTP is not qualified
from tok/s alone.
