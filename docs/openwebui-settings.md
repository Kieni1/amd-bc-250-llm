# Open WebUI settings

Package baseline: **Open WebUI v0.11.3** with **Ollama v0.33.2**. Runtime pins
are recorded in `/usr/share/bc250-llm-server/runtime.env`.

The package uses two layers deliberately:

1. the Quadlet supplies safe bootstrap/offline defaults so a new database starts
   locally and conservatively;
2. `bc250-openwebui-setup` applies the package-owned application state through
   Open WebUI's supported administrator APIs after authentication.

The package never edits `webui.db` directly and does not store the administrator
password or the temporary API/session token used for setup.

## First setup

The guided installer offers this step after the model lanes are configured. On a
fresh interactive install it can create the first administrator; on an existing
installation it can sign in an administrator and apply the reviewed baseline.
Unattended installation never waits for credentials.

Manual equivalents:

```bash
sudo bc250-openwebui-setup init
OWUI_API_KEY=TEMPORARY_ADMIN_KEY sudo -E bc250-openwebui-setup apply
bc250-openwebui-setup status
OWUI_API_KEY=TEMPORARY_ADMIN_KEY sudo -E bc250-openwebui-setup status
```

`status` without a key checks reachability only. With a temporary administrator
key it also compares the package-owned settings with the reviewed desired state.
The key is read from the process environment and is never written by the helper.
A reported difference may be an intentional operator override; `status` does not
reset it.

## Configuration ownership

The package manages only the settings needed to make the appliance coherent:

- normal Open WebUI Ollama providers: main `11434` and task `11435`;
- the local task model and conservative task-generation toggles;
- the RAG/Tika baseline and dedicated embedding endpoint `11437`;
- five additive BC-250 workspace model presets from the versioned
  `config/openwebui/models.json` payload.

The operator owns users, credentials, custom prompts, unrelated workspace models,
knowledge bases, UI preferences, permissions and any intentional settings that
are outside that baseline. Model presets are imported through the additive
`/api/v1/models/import` endpoint; the package does **not** use destructive model
sync and therefore does not remove operator-created models.

## Ollama lanes

| Purpose | Endpoint | Open WebUI use |
|---|---|---|
| Production/chat | `http://host.containers.internal:11434` | enabled provider, production models only |
| Task | `http://host.containers.internal:11435` | enabled provider, task models only |
| Embedding | `http://host.containers.internal:11437` | retrieval API only, not a chat provider |
| Agent/coding | host `11436` | intentionally absent from Open WebUI |
| Tika | `http://tika:9998` | private document extraction |

The task connection must be enabled because Open WebUI resolves its local task
model from the active provider model map. Its model allowlist prevents task
models from becoming the ordinary user-facing production fleet.

Agent/coding mode is exclusive. Use:

```bash
sudo bc250-agent-mode enter
# coding/agent work
sudo bc250-agent-mode leave
```

Entering agent mode stops main/task/embedding; leaving restores normal mode.
This is intentional on the BC-250 unified-memory pool.

## Package model presets

`bc250-openwebui-setup` imports friendly presets additively:

| Preset | Base model |
|---|---|
| Office – Standard | `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` |
| Office – Documents | `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` |
| Office – Translation DE/FR | `prod-lfm25-8b-a1b-liquidai-q6-k` |
| Office – General / Higher Quality | `prod-qwen35-9b-unsloth-q6-k` |
| Office – Deep Reasoning | `prod-gpt-oss20b-ggml-org-mxfp4` |

The Qwen3.5 preset carries request-level `think=false`; the package keeps
Ollama's native renderer/parser rather than replacing the model template.
GPT-OSS remains the likely memory-edge production model when the dedicated
embedding service is resident, so rerun the production benchmark on the target
board before treating that combination as qualified.

## Task baseline

The API helper selects:

```text
task-gemma3-1b-unsloth-ud-q4-k-xl:latest
```

and keeps title/tag generation on while follow-up, autocomplete, search-query and
retrieval-query generation remain off. `TASK_MODEL_PARAMS` stays `{}` so Open
WebUI v0.11.3 retains its upstream task-token behavior. The helper first reads the
complete v0.11.3 task configuration and then updates only reviewed fields, which
preserves upstream prompt templates.

## RAG baseline

The dedicated embedding lane uses Jina on `11437`, a 10-minute Ollama keepalive,
batch size 1 and asynchronous embedding disabled. The reviewed retrieval baseline
remains token splitting, 1500-token chunks, 200-token overlap, Markdown-header
splitting, Top K 8, hybrid search off and Tika extraction.

`RAG_SYSTEM_CONTEXT=false` remains deliberate for 0.10.0. Test it later with a
real repeated-turn RAG acceptance run before changing the default. Likewise keep
`CHUNK_MIN_SIZE_TARGET=0` and embedding batch size 1 until measured on the real
corpus.

Open WebUI enforces **128 MiB per file**. nginx has a larger **256 MiB reverse-proxy ceiling** so multipart/request overhead does not make nginx the accidental
application limit.

See [`RAG.md`](RAG.md) for ingestion and retrieval acceptance testing.

## Local/offline application baseline

The Quadlet keeps authentication enabled and disables cloud OpenAI access,
community sharing, direct browser connections, code execution/interpreter,
memories and frontmatter-driven pip installation. It also sets:

```text
OFFLINE_MODE=true
HF_HUB_OFFLINE=1
RAG_EMBEDDING_MODEL_AUTO_UPDATE=false
RAG_RERANKING_MODEL_AUTO_UPDATE=false
WHISPER_MODEL_AUTO_UPDATE=false
```

This reduces application-initiated outbound activity. It is **not** an air-gap
or firewall boundary. nginx/firewalld remain the network security boundary, and
the unauthenticated Ollama listeners must remain inaccessible from untrusted
networks.

## Persistent settings and upgrades

Open WebUI persists many settings in its database. That is why the package now
uses a supported, explicit API setup/drift workflow instead of assuming Quadlet
environment variables remain authoritative forever. This pre-1.0 release does
not add automatic database-backup/migration machinery; treat application data as
test-appliance state and keep any operator-required backup policy separate.

For a later Open WebUI update, smoke-test normal chat, title/tag tasks, document
upload/extraction, embedding/retrieval, the five package presets and an
authenticated `bc250-openwebui-setup status` before changing the pin.

## Deferred candidates

Keep these as later measurements, not 0.10.0 defaults:

- `RAG_SYSTEM_CONTEXT=true` repeated-turn quality/cache A/B;
- larger embedding batches;
- nonzero `CHUNK_MIN_SIZE_TARGET`;
- any additional Open WebUI tools/subagent fan-out that would increase model
  concurrency or memory pressure.
