# Open WebUI settings for the BC-250 server

The RPM deliberately keeps application settings user-managed. The Quadlet only
provides the local Ollama connection, private Tika extraction, local embedding
connection and basic privacy flags.

## First boot

Open `http://SERVER_IP/` from the trusted LAN and register immediately. The first
account becomes administrator; subsequent sign-ups are disabled automatically by
Open WebUI. No administrator password or application secret is committed by this
package.

The packaged HTTP endpoint is not encrypted. Complete `docs/HTTPS.md` before using
the service across an untrusted network.

## Packaged image and upgrades

The Quadlet pins Open WebUI v0.11.0 by OCI index digest. A clean installation
initializes the current schema automatically and needs no migration step.

Open WebUI v0.11.0 includes database schema changes. Before upgrading a host
with existing `/var/lib/open-webui` state, stop `open-webui.service` and take a
complete filesystem snapshot or offline copy of that directory. The packaged
configuration-backup helper excludes uploads, vector data and caches, so it is
not a complete substitute for this pre-upgrade snapshot. Start the service only
after the backup is complete; the container performs its migration at startup.

## Connections

```text
Ollama: http://host.containers.internal:11434
Task:   http://host.containers.internal:11435
Agent:  http://host.containers.internal:11436
Tika:   http://tika:9998
```

Tika is private to the Quadlet network and should never appear as a host/LAN
listener.

## Suggested starting settings

- Authentication: enabled
- OpenAI/API cloud connection: disabled unless explicitly required
- Embedding engine: Ollama
- Embedding model: `nomic-embed-text`
- Content extraction: Tika
- Community sharing and public links: disabled for office use
- Tools, Functions, Pipelines and arbitrary code execution: disabled for ordinary users
- File upload limit: at or below nginx's 256 MiB limit
- One loaded model and one parallel request in Ollama

No default chat model is forced because model installation is operator-selected.

## Task model

Open WebUI v0.11 uses its local task model for title, tag, follow-up,
autocomplete, retrieval-query and web-search-query generation. The packaged
Gemma 3 task Modelfile therefore leaves `SYSTEM` unset so that each Open WebUI
task prompt controls the response.

Under **Admin Settings -> Experience -> Interface**, set **Local Task Model** to
`task-gemma3-1b-unsloth-ud-q4-k-xl:latest` and start with:

| Setting | Value |
|---|---|
| Title Generation | On |
| Tags Generation | On |
| Retrieval Query Generation | On when using RAG |
| Follow Up Generation | Off initially |
| Autocomplete Generation | Off |
| Web Search Query Generation | Off unless web search is configured |

The task model has a 4,096-token context and a 128-token output limit. Keep
autocomplete off on the BC-250: it can repeatedly load the task model while a
larger chat model is still warm.

See the [Open WebUI v0.11 task router](https://github.com/open-webui/open-webui/blob/v0.11.0/backend/open_webui/routers/tasks.py)
and [task prompt defaults](https://github.com/open-webui/open-webui/blob/v0.11.0/backend/open_webui/config.py).

## Per-model Open WebUI settings

Open WebUI v0.11 enables most capabilities when a model workspace entry is
created. Review them explicitly rather than accepting every default.

### Gemma 4 E4B document/RAG model

The packaged Modelfile already carries the recommended sampling values and a
hardware-appropriate 32,768-token context. Do not duplicate them in Open WebUI.

| Capability or parameter | Value |
|---|---|
| File Upload | On |
| File Context | On |
| Memory | Off |
| Builtin Tools | Off initially |
| Web Search, Vision, Code Interpreter, Image Generation | Off |
| Function Calling | Default |
| `num_ctx`, temperature, `top_p`, `top_k` | Default/unset |
| `think` | Default |

This keeps document answers grounded in retrieved file context instead of also
injecting stored memories or autonomous tools. The downloaded GGUF has no
packaged multimodal projector, so do not advertise it as a vision model.

The current Ollama Gemma 4 definition recommends `temperature=1.0`,
`top_p=0.95`, and `top_k=64`, matching the packaged Modelfile:
[Gemma 4 E4B](https://ollama.com/library/gemma4:e4b-it-qat).

### GPT-OSS 20B reasoning model

The packaged 16,384-token context is the BC-250 baseline. Start with:

| Capability or parameter | Value |
|---|---|
| File Upload | On |
| File Context | On |
| Memory | Off initially |
| Builtin Tools | Off initially |
| Web Search, Vision, Code Interpreter, Image Generation | Off |
| Function Calling | Default/native |
| `num_ctx`, temperature, `top_p`, `top_k` | Default/unset |
| `think` | Default |
| Reasoning Effort | Default/unset |

With `think` left at Default, Ollama's GPT-OSS template selects medium
reasoning. Open WebUI v0.11 also supports a **Custom** `think` string; use
`low`, `medium`, or `high` only for deliberate reasoning/latency comparisons.
Do not use the boolean On/Off states for GPT-OSS because Ollama ignores boolean
`think` values for this model. Open WebUI's separate **Reasoning Effort** field
does not control a local Ollama connection.

References: [Ollama thinking levels](https://docs.ollama.com/capabilities/thinking),
[GPT-OSS 20B](https://ollama.com/library/gpt-oss:20b), and the
[Open WebUI v0.11 advanced-parameter control](https://github.com/open-webui/open-webui/blob/v0.11.0/src/lib/components/chat/Settings/Advanced/AdvancedParams.svelte).

For both production models, leave `num_ctx` unset in Open WebUI. A configured
Open WebUI value is sent on every request and overrides Ollama's model setting;
enabling the control initially inserts 2,048 in v0.11. The Modelfiles are the
source of truth for this appliance.

## Container memory limit

The packaged Quadlet allows Open WebUI 2 GiB. For unusually large concurrent
RAG uploads, copy the vendor Quadlet to `/etc/containers/systemd/`, adjust
`Memory=`, then run `sudo systemctl daemon-reload` and restart
`open-webui.service`. A file in `/etc/containers/systemd/` overrides the vendor
definition and remains administrator-owned.

## Suggested model roles

| Example | Use | Context starting point |
|---|---|---:|
| `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` | Documents and RAG | 32,768 |
| `prod-gpt-oss20b-ggml-org-mxfp4` | Deeper analysis | 8,192–16,384 |
| `prod-ministral3-8b-unsloth-ud-q5-k-xl` | Translation | 32,768 |
| `prod-qwen3-4b-lmstudio-q6-k` | Fast office work | 8,192 |
| `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` | Fast text generation | 32,768 |
| `prod-qwen35-9b-hauhaucs-uncensored-q6-k` | General comparison | 32,768 |
| `agentic-ornith1-9b-deepreinforce-q5-k-m` | Dedicated agentic work | 32,768 |
| `agentic-qwable9b-empero-q6-k` | Dedicated agentic comparison | 32,768 |

All contexts must be validated for full GPU residency on the particular board.
Model output is not authoritative; verify consequential facts against source
material.
