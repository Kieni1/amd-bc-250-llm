# Open WebUI settings

The package supplies local connections and a fresh-install privacy baseline;
application accounts and model behavior remain operator-managed. The Quadlet
explicitly disables community sharing, code execution, the code interpreter and
memories. Operators can deliberately re-enable those features later.

Package baseline: **Open WebUI v0.11.1** with standard **Ollama v0.32.15**.

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
- Jina's fresh-install prefixes are `Query: ` and `Document: `. The packaged
  The packaged Jina GGUF carries upstream `pooling_type` metadata. Reindex after
  replacing the older package GGUF, and whenever changing embedding model,
  prefixes or chunking. Extraction-engine/source-text changes require re-uploading
  or re-syncing content.
- Keep the packaged community-sharing, code-execution/interpreter and memory
  defaults **off** for private office data unless local policy explicitly enables
  them.
- Disable arbitrary tools, functions and pipelines for ordinary users.
- Keep uploads at or below nginx's 256 MiB limit.
- Leave request concurrency to the packaged one-parallel/one-loaded-model
  Ollama profile.

The Jina embedding model is CC-BY-NC-4.0; choose the packaged Apache-2.0 Qwen
embedding alternative if the intended use is incompatible with that license.
For Qwen, use an English retrieval instruction on the query side and leave the
content prefix empty. See [`RAG.md`](RAG.md) for the exact pilot settings.

Open WebUI persists many application/RAG settings in `webui.db`; values saved in
the Admin UI can override packaged fresh-install environment defaults after first
launch. The four privacy feature flags above are therefore a green-field baseline,
not a migration policy for an existing database.

The packaged fresh-install RAG template is source-grounded and does not silently
fill missing document facts from general model knowledge. Review the saved RAG
template in **Admin Settings → Documents** on upgraded/existing instances because
a database value takes precedence over the Quadlet default.

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

Open WebUI 0.11.1 adds `TASK_MODEL_PARAMS`. The package explicitly leaves it at
`{}` so upstream task limits/behavior remain unchanged until measured on the
dedicated Gemma 3 1B service. Tune it only after `bc250-benchmark task`; the packaged LFM2.5 2.6B task
candidate exists specifically to compare multilingual adherence without changing
the default. Note that setting a non-empty object replaces Open WebUI's built-in task token-limit behavior,
so include an explicit `max_tokens` if you later set other task parameters.

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
| `task-gemma3-1b-unsloth-ud-q4-k-xl` | Admin Settings → Experience → Interface | selected as Local Task Model | Current smallest default; do not expose as a normal office-chat preset. |
| `task-lfm25-2.6b-liquidai-q6-k` | Admin Settings → Experience → Interface | task-model comparison | Multilingual challenger; benchmark before replacing Gemma 3 1B. |
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

Open WebUI v0.11.1 is pinned by OCI digest. Before changing the image on a host
with existing data:

```bash
sudo systemctl stop open-webui.service
sudo tar --xattrs --acls --numeric-owner -C /var/lib \
  -czf /ENCRYPTED-BACKUP/open-webui-full-$(date +%F).tar.gz open-webui
sudo systemctl start open-webui.service
```

The container applies database migrations at startup. A regular maintenance
configuration backup is not a substitute for this complete snapshot.

For the 0.11.1 upgrade, smoke-test one normal chat, a multi-turn Ollama reasoning
chat, title/tag generation, one RAG upload/search/rebuild and Workspace → Knowledge.
Open WebUI 0.11.1 substantially changed streaming and reasoning-history handling.
Upstream issue #29035 reports a frontend streaming failure with some thinking-model
responses, so treat GPT-OSS/Ornith streaming as an upgrade acceptance check and use
the pre-upgrade snapshot if it reproduces on the appliance. Avoid switching models
inside an existing reasoning-heavy conversation when the provider uses opaque,
model-specific reasoning state. Keep Tika on major version 3
(`TIKA_SERVER_VERSION=3`) and knowledge-file retention disabled for this appliance.
