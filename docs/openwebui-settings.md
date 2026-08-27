# Open WebUI settings

The package supplies local connections and privacy-oriented container defaults;
application accounts and model behavior remain operator-managed.

Package baseline: **Open WebUI v0.11.0** with standard **Ollama v0.32.15**.

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
- Use Ollama embeddings with `embed-jina-v5-small-retrieval-q4-k-m`.
- Use Tika for content extraction.
- Start document retrieval with the **moderate** package profile: token splitting,
  1500-token chunks, 200-token overlap, Top K 8, Markdown-header splitting on,
  hybrid search off and async embedding off.
- The **conservative** alternative is 1000/100/Top-K-5 when model/context headroom
  is tighter or when deliberately testing smaller retrieval chunks.
- Jina's fresh-install prefixes are `Query: ` and `Document: `. Changing the
  embedding model, prefixes or chunking requires reindexing Knowledge documents;
  extraction-engine/source-text changes require re-uploading or re-syncing content.
- Disable public sharing and community features for private office data.
- Disable arbitrary tools, functions, pipelines and code execution for ordinary
  users.
- Keep uploads at or below nginx's 256 MiB limit.
- Leave request concurrency to the packaged one-parallel/one-loaded-model
  Ollama profile.

The Jina embedding model is CC-BY-NC-4.0; choose the packaged Apache-2.0 Qwen
embedding alternative if the intended use is incompatible with that license.
For Qwen, use an English retrieval instruction on the query side and leave the
content prefix empty. See [`RAG.md`](RAG.md) for the exact pilot settings.

Open WebUI persists many RAG settings in `webui.db`; values saved in the Admin
UI can override packaged fresh-install environment defaults after first launch.

For bulk document work, keep originals under `/srv/bc250-documents` and use
`sudo bc250-rag-import plan` before syncing. The importer separates authoritative
German originals from French translations into distinct knowledge bases so a
French query can deliberately use the translation set without weakening the
German source-of-truth policy. Public/confidential filesystem branches are also
kept as separate Open WebUI knowledge bases.

## Task model

Under **Admin Settings → Experience → Interface**, set the local task model to:

```text
task-gemma3-1b-unsloth-ud-q4-k-xl:latest
```

| Setting | Starting value |
|---|---|
| Title generation | On |
| Tags generation | On |
| Retrieval-query generation | **Off for the baseline; test later** |
| Follow-up generation | Off initially |
| Autocomplete | Off |
| Web-search query generation | Off unless configured |

Keep retrieval-query generation off while establishing the raw embedding/chunking
baseline; enabling it later deliberately tests whether task-model query rewriting
improves retrieval enough to justify another model invocation. Autocomplete can
repeatedly load the task model while a larger chat model is still warm, so keep it
off unless the latency and memory behavior are acceptable.

## Model roles

| Role | Model | Context |
|---|---|---:|
| Standard office | `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` | 32,768 |
| Documents/RAG | `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` | 32,768 |
| German–French translation | `prod-lfm25-8b-a1b-liquidai-q6-k` | 32,768 |
| General / higher-quality office | `prod-qwen35-9b-unsloth-q6-k` | 32,768 |
| Deep reasoning | `prod-gpt-oss20b-ggml-org-mxfp4` | 16,384 |
| Embedding | `embed-jina-v5-small-retrieval-q4-k-m` | 32,768 |
| Embedding alternative | `embed-qwen3-0.6b-q8-0` | 32,768 |
| Task | `task-gemma3-1b-unsloth-ud-q4-k-xl` | 4,096 |
| Agentic/coding | `agentic-ornith15-9b-ornith-q5-k-m` | 32,768 |

### Where model settings belong

- **Modelfile:** `SYSTEM`, context and sampling. Packaged values are the baseline.
- **Open WebUI persistent model settings:** **Workspace → Models → edit/create a
  model preset**. Use **Advanced Parameters** for `think`/reasoning parsing and
  the model editor's capabilities for File Context, Builtin Tools, Memory, etc.
- **Open WebUI test override:** **Chat Controls → Advanced Parameters**. Do not
  save benchmark overrides into the production preset.
- **Task model:** **Admin Settings → Experience → Interface** as documented above.
- **Embedding model and prefixes:** **Admin Settings → Documents**. See
  [`RAG.md`](RAG.md).
- **Ollama service behavior:** systemd/service environment. See [`OLLAMA.md`](OLLAMA.md).

Leave Open WebUI `num_ctx`, temperature, `top_p` and `top_k` unset unless a test
specifically compares an override. Enabling those controls can override the
Modelfile on every request. Do not add a generic Open WebUI system prompt on top
of the packaged multilingual `SYSTEM` prompt unless the preset deliberately
changes the model's role.

### Per-model Open WebUI baseline

Gemma 4 thinking is enabled only when its Modelfile `SYSTEM` starts with
`<|think|>`; the packaged E2B/E4B system prompts deliberately do not.

| Model | Persistent setting | Starting value | Notes |
|---|---|---|---|
| `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` | Workspace model preset | `think`: leave unset/default | Non-thinking is selected by the packaged Modelfile. File Context optional; Memory, Web Search and Code Interpreter off initially. |
| `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` | Workspace model preset | `think`: leave unset/default | Same Gemma 4 non-thinking behavior. Enable File Context for RAG. Keep Builtin Tools off for chat-attached knowledge; if knowledge is permanently bound to the preset, enable only the Knowledge Base builtin-tool category. |
| `prod-lfm25-8b-a1b-liquidai-q6-k` | Workspace model preset | Reasoning Tags: Default; `think`: leave unset/default | LFM2.5 emits native reasoning before the final answer; Open WebUI's default `<think>` parsing is sufficient. For the translation preset keep Builtin Tools, Memory and Web Search off. |
| `prod-qwen35-9b-unsloth-q6-k` | Workspace model preset → Advanced Parameters | `think`: **Off** | The packaged sampling profile is the Qwen3.5 non-thinking profile. Do not enable thinking on this production preset; use a separate experimental preset/Modelfile when testing Qwen3.5 reasoning. |
| `prod-gpt-oss20b-ggml-org-mxfp4` | Workspace model preset → Advanced Parameters | `think`: Default | Ollama defaults GPT-OSS to medium reasoning. Use `low`, `medium` or `high` only for deliberate latency/quality comparisons. Leave Open WebUI's separate Reasoning Effort field unset for local Ollama. |
| `task-gemma3-1b-unsloth-ud-q4-k-xl` | Admin Settings → Experience → Interface | selected as Local Task Model | Do not expose as a normal office-chat preset. |
| `agentic-ornith15-9b-ornith-q5-k-m` | Agent connection + Workspace model preset | Reasoning Tags: Default; `think`: leave unset/default | Ornith emits native `<think>` reasoning. Enable only the tools required by the coding-agent workflow. The agent service is intended for exclusive use, not concurrently with a large main model. |
| `embed-jina-v5-small-retrieval-q4-k-m` | Admin Settings → Documents | embedding model + Jina prefixes | Not a chat/task model. Reindex when changing model or prefixes. |
| `embed-qwen3-0.6b-q8-0` | Admin Settings → Documents | embedding model + Qwen query instruction | Alternative embedding backend; content prefix stays empty. Reindex when switching from Jina. |

For document/RAG use, keep Memory, Web Search, Code Interpreter and Image
Generation off initially. The packaged Gemma 4 GGUFs are text-only because no
multimodal projector is packaged.

### User-facing presets after testing

After validation, create friendly **Workspace → Models** presets and expose those
to normal users instead of the raw model fleet. Example names:

```text
Office – Standard
Office – Documents
Office – Translation DE/FR
Office – General / Higher Quality
Office – Deep Reasoning
Coding / Agent
```

Embedding, task and OCR models normally remain operator-facing. Experimental
models can stay hidden until a benchmark justifies promotion.

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
