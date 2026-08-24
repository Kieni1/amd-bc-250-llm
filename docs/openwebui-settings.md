# Open WebUI settings

The package supplies local connections and privacy-oriented container defaults;
application accounts and model behavior remain operator-managed.

## First login and connections

Open `http://SERVER_IP/` from the trusted LAN and register immediately. The
first account becomes administrator. Configure HTTPS before using an untrusted
network.

| Service | URL |
|---|---|
| Main Ollama | `http://host.containers.internal:11434` |
| Task Ollama | `http://host.containers.internal:11435` |
| Agent Ollama | `http://host.containers.internal:11436` |
| Tika | `http://tika:9998` |

The main Ollama and Tika connections are packaged. Add task and agent only when
their services are installed. Tika must not be exposed as a host/LAN listener.

## Recommended baseline

- Keep authentication enabled.
- Disable cloud API connections unless explicitly required.
- Use Ollama embeddings with
  `embed-jina-v5-small-retrieval-q4-k-m`.
- Use Tika for content extraction.
- Disable public sharing and community features for private office data.
- Disable arbitrary tools, functions, pipelines and code execution for ordinary
  users.
- Keep uploads at or below nginx's 256 MiB limit.
- Leave request concurrency to the packaged one-parallel/one-loaded-model
  Ollama profile.

The Jina embedding model is CC-BY-NC-4.0; choose the packaged Qwen embedding
alternative if the intended use is incompatible with that license.

## Task model

Under **Admin Settings → Experience → Interface**, set the local task model to:

```text
task-gemma3-1b-unsloth-ud-q4-k-xl:latest
```

| Setting | Starting value |
|---|---|
| Title generation | On |
| Tags generation | On |
| Retrieval-query generation | On when using RAG |
| Follow-up generation | Off initially |
| Autocomplete | Off |
| Web-search query generation | Off unless configured |

Autocomplete can repeatedly load the task model while a larger chat model is
still warm, so keep it off unless the latency and memory behavior are acceptable.

## Model roles

| Role | Model | Context |
|---|---|---:|
| Standard office | `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` | 32,768 |
| Documents/RAG | `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` | 32,768 |
| German–French | `prod-lfm25-8b-a1b-liquidai-q6-k` | 32,768 |
| Deep reasoning | `prod-gpt-oss20b-ggml-org-mxfp4` | 16,384 |
| Embedding | `embed-jina-v5-small-retrieval-q4-k-m` | 32,768 |
| Task | `task-gemma3-1b-unsloth-ud-q4-k-xl` | 4,096 |
| Agentic/coding | `agentic-ornith15-9b-ornith-q5-k-m` | 32,768 |

Packaged Modelfiles already define hardware-tested context and sampling values.
Leave Open WebUI `num_ctx`, temperature, `top_p` and `top_k` unset unless the
test specifically compares an override. Enabling Open WebUI's context control
can override the Modelfile on every request.

For document/RAG use, enable file upload and file context, but start with memory,
builtin tools, web search, vision, code execution and image generation off. The
packaged Gemma 4 GGUF has no multimodal projector.

For GPT-OSS, leave `think` at default for the baseline. Use `low`, `medium` or
`high` only for deliberate reasoning/latency comparisons; leave Open WebUI's
separate Reasoning Effort field unset for local Ollama.

## Upgrades

Open WebUI v0.11.0 is pinned by OCI digest. Before changing the image on a host
with existing data:

```bash
sudo systemctl stop open-webui.service
sudo tar --xattrs --acls --numeric-owner -C /var/lib \
  -czf /ENCRYPTED-BACKUP/open-webui-full-$(date +%F).tar.gz open-webui
sudo systemctl start open-webui.service
```

The container applies database migrations at startup. A regular maintenance
configuration backup is not a substitute for this complete snapshot.
