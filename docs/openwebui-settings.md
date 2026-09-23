# Open WebUI settings

Package baseline: **Open WebUI v0.11.3** with **Ollama v0.34.2** and **Apache Tika v4.0.0**. Runtime pins
are recorded in `/usr/share/bc250-llm-server/runtime.env`.

The package uses two layers deliberately:

1. the Quadlet supplies safe bootstrap/offline defaults so a new database starts
   locally and conservatively;
2. `/usr/share/bc250-llm-server/openwebui/desired-state.json` is the single
   package authority for persisted providers/task/embedding/RAG settings and the
   small local/offline application-policy subset owned by the appliance;
   `bc250-openwebui-setup` applies it through supported administrator APIs.

The package never edits `webui.db` directly and does not store the administrator
password or the temporary API/session token used for setup. It does persist a
generated Open WebUI signing secret in the root-only
`/var/lib/bc250-llm-server/secrets/open-webui.env`; this is application key
material, not an administrator credential, and keeps sessions/tokens valid when
the container is recreated.

## First setup

The guided installer offers this step after the model lanes are configured. On a
fresh interactive install it can create the first administrator; on an existing
installation it can sign in an administrator and apply the reviewed baseline.
Unattended installation never waits for credentials.

Manual equivalents:

```bash
sudo bc250-openwebui-setup init
sudo bc250-openwebui-setup init --token-file /root/owui-test.key
OWUI_API_KEY=TEMPORARY_ADMIN_KEY sudo -E bc250-openwebui-setup apply
bc250-openwebui-setup status
sudo bc250-openwebui-setup status --verbose --token-file /root/owui-test.key
OWUI_API_KEY=TEMPORARY_ADMIN_KEY sudo -E bc250-openwebui-setup status
```

`init` offers administrator sign-in/create or protected API-key-file authentication.
When `/root/owui-test.key` is present with protected permissions, it is offered as
the default choice without asking for the same path a second time. It is never
consumed silently: the operator still selects whether to use it, sign in, create
the first administrator, or choose a different API key file. `status` without a key checks reachability only. With a
temporary administrator key or `--token-file` it also compares the package-owned
settings with the reviewed desired state. Add `--verbose` to print the verified active
role/base-model mapping, translation budget/filter attachment, task/RAG defaults and
package-owned Function state. The helper does not persist credentials;
the install orchestrator may hold the authenticated token briefly under `/run` so
its final verification can reuse the same session, then removes it on exit.
A reported difference may be an intentional operator override; `status` does not
reset it.

## Configuration ownership

The package manages only the settings needed to make the appliance coherent.
Those persisted values live in `desired-state.json`, not as duplicate Quadlet
environment variables:

- normal Open WebUI Ollama providers: main `11434` and task `11435`;
- the local task model and conservative task-generation toggles;
- the RAG/Tika baseline and dedicated embedding endpoint `11437`;
- persisted upload limits/extension allowlist;
- local/offline application policy: Arena off, cloud OpenAI/direct connections,
  code execution/interpreter, memories and community sharing off;
- package-owned BC-250 workspace model presets from the versioned
  `config/openwebui/models.json` payload;
- active workspace overrides for the five production implementation models and
  the dedicated task model. During pre-v1 testing these records are deliberately
  visible so operators can compare curated roles with raw implementations;
- authenticated-read (`user:*:read`) grants on the six active production presets
  and the six implementation/task overrides required by those roles.

The operator owns users, credentials, custom prompts, unrelated workspace models,
knowledge bases, UI preferences, permissions and any intentional settings that
are outside that baseline. Model presets are imported through the additive
`/api/v1/models/import` endpoint; the package does **not** use destructive model
sync and therefore does not remove operator-created models.
Required model access is converged separately and additively: package desired state
means that required grants must exist, not that the complete ACL must equal a package-owned
set. Existing unrelated grants are retained, including historical grants on inactive records.
The current pre-v1 testing policy deliberately keeps raw production/task implementations visible.
The main and task providers are unrestricted, so experimental models that are actually installed on
those normal lanes are visible too. This is a testing surface, not a promise that every raw model will
remain user-facing for v1.

## Ollama lanes

| Purpose | Endpoint | Open WebUI use |
|---|---|---|
| Main/chat | `http://host.containers.internal:11434` | enabled, unrestricted during testing: installed production + experimental models |
| Task | `http://host.containers.internal:11435` | enabled, unrestricted during testing: installed task-lane models |
| Embedding | `http://host.containers.internal:11437` | retrieval API only, not a chat provider |
| Agent/coding | host `11436` | intentionally absent from Open WebUI |
| Tika | `http://tika:9998` | private document extraction |

The task connection must be enabled because Open WebUI resolves its local task model from the
active provider model map. During pre-v1 testing both normal providers intentionally use an empty
`model_ids` allowlist, which Open WebUI treats as unrestricted discovery. The task implementation
model therefore remains selectable as a raw test target even though its supported purpose is title/tag
work.

Agent/coding mode is exclusive. Use:

```bash
sudo bc250-agent-mode enter
# coding/agent work
sudo bc250-agent-mode leave
```

Entering agent mode stops main/task/embedding; leaving restores normal mode. Open WebUI itself
remains reachable, and its persisted catalogue may continue to list normal office roles while those
backends are intentionally unavailable. Return with `sudo bc250-agent-mode normal`; do not dynamically
rewrite Open WebUI provider/model state merely to mirror the temporary exclusive topology.
This is intentional on the BC-250 unified-memory pool.

### Curated role tool policy

Open WebUI 0.11.x injects built-in knowledge/chat tools into native-tool-capable models unless model
metadata disables them. The package therefore makes the role boundary explicit:

- `Office - Standard`, `Office - General / Higher Quality`, `Office - Deep Reasoning` and both
  translation roles disable built-in tools. They answer ordinary questions from model knowledge and
  still accept pre-injected/attached file context.
- `Office - Documents / RAG` keeps built-in retrieval enabled, but disables unrelated chat-history,
  notes, web, automation and similar tool categories. Knowledge retrieval is therefore concentrated in
  the dedicated document role instead of being silently attempted by general chat roles.
- raw/experimental models are exposed for comparison testing and may retain their own native/default
  behavior unless a package-owned base override says otherwise.

The system prompts in the production Modelfiles remain authoritative for Standard, Documents,
Advanced and Deep. Their Open WebUI presets intentionally do not add a second system prompt. The
translation base Modelfile intentionally has no `SYSTEM`; its exact product contract is owned by the
Open WebUI translation preset plus direction filter.

## OpenAI-style API compatibility boundary

Open WebUI's `/api/chat/completions` endpoint is used internally by package product-path tests, but
the pinned Open WebUI v0.11.3 OpenAI-style adapter is **not** an advertised external BC-250 API
contract. Exact-device attribution found three upstream adapter limitations for Ollama-backed models:

- a root OpenAI-style `max_tokens=N` is not reliably propagated as an Ollama generation cap;
- `completion_tokens_details.reasoning_tokens` can be `0` even when `reasoning_content` is present;
- an Ollama `done_reason=length` can be surfaced as OpenAI-style `finish_reason=stop`.

Package-owned callers that require a hard Ollama generation cap use the native nested
`options.num_predict` path. Package preset `params.max_tokens` is a separate Open WebUI model-parameter
path and remains part of the device-tested translation contract. Do not infer absence of reasoning or
absence of truncation from the two affected OpenAI-style metadata fields on v0.11.3. If a future
release wants to advertise this endpoint as an external compatibility surface, first qualify a newer
Open WebUI version or carry a deliberately reviewed adapter patch with dedicated device tests.

## Package model presets

`bc250-openwebui-setup` imports package-owned workspace presets:

| Preset | Base model | State |
|---|---|---|
| Office – Standard | `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` | active |
| Office – Documents | `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` | active |
| Office – Translation DE → FR | `prod-translate-gemma4-sub-e4b-17s-q4-k-xl` | active |
| Office – Translation FR → DE | `prod-translate-gemma4-sub-e4b-17s-q4-k-xl` | active |
| Office – Translation DE/FR (Legacy LFM reference) | `exp-lfm25-8b-a1b-liquidai-q6-k` | inactive |
| Office – General / Higher Quality | `prod-qwen35-9b-unsloth-q6-k` | active |
| Office – Deep Reasoning | `prod-gpt-oss20b-ggml-org-mxfp4` | active |

For the current 16 GiB profile, **Office – Documents** is the production RAG/document role.
The September 2026 product-path campaign found both Documents/Gemma E4B and Advanced/Qwen 9B
functionally strong in short sessions, but only Gemma retained comfortable memory headroom during
continuous residency. Keep Advanced as an optional heavier general-office role rather than treating
it as an equivalent long-lived RAG default.

The two active Translate-Gemma roles reproduce the selected Stage-2E product contract.
Both use the exact installed `openwebui/prompts/translation-explicit-direction-v1.txt`
prompt, `max_tokens=2048`, and leave `think` unspecified. The package-owned non-global
`bc250_translation_direction` Filter prepends only the tested DE→FR or FR→DE wrapper to
the current text user message.

`bc250-install` now ensures the base model behind every active package-owned Open WebUI
role before applying desired state, including the production Translate-Gemma role. Manual
model installation is therefore needed only for experiments/rollback paths or deliberate
operator changes.

To inspect the live verified contract:

```bash
sudo bc250-openwebui-setup status --verbose --token-file /root/owui-test.key
```

The legacy LFM preset is intentionally inactive. Its base model now lives in the
experiments catalog and is installed only for deliberate rollback/comparison work.

The Qwen3.5 preset carries request-level `think=false`; the package keeps Ollama's
native renderer/parser rather than replacing the model template. The Deep Reasoning
preset sets `keep_alive=0` so GPT-OSS unloads after each response before the dedicated
task model cold-loads for title/tag generation. Standard and Advanced keep their
existing residency behavior. The GPT-OSS Modelfile also carries an accuracy-first factual fallback: when reliable recall is insufficient, it should return fewer items and state uncertainty instead of filling a requested list with plausible names or placeholders. Sampling/context/residency are unchanged. GPT-OSS remains the likely memory-edge production model
when the dedicated embedding service is resident.

## Task baseline

The API helper selects:

```text
task-lfm25-1.2b-instruct-liquidai-q6-k:latest
```

and keeps title/tag generation on while follow-up, autocomplete, search-query and
retrieval-query generation remain off. `TASK_MODEL_PARAMS` stays `{}` so Open
WebUI v0.11.3 retains its upstream task-token behavior. The helper first reads the
complete v0.11.3 task configuration and then updates only reviewed fields. Those
reviewed fields now include package-owned title, tag and retrieval-query prompt
templates so live Open WebUI and direct task qualification share one prompt policy. The
0.11.3-0.3 tag prompt keeps broad themes and specific subtopics in one `tags` array and
requires exactly one raw JSON object with no second object, prose or Markdown; the task
model and 128-token tag budget are unchanged.

## RAG baseline

The dedicated embedding lane uses Jina on `11437`, a 10-minute Ollama keepalive,
batch size 1 and asynchronous embedding disabled. The reviewed retrieval baseline
remains token splitting, 1500-token chunks, 200-token overlap, Markdown-header
splitting, Top K 8, hybrid search off and Tika extraction. Open WebUI is explicitly
set to `TIKA_SERVER_VERSION=4` so it uses the Tika 4 API; smoke-test representative
office/PDF extraction after this major Tika refresh.

`RAG_SYSTEM_CONTEXT=false` remains the packaged default pending promotion evidence
from repeated-turn RAG acceptance on the real appliance. Likewise keep
`CHUNK_MIN_SIZE_TARGET=0` and embedding batch size 1 until measured on the real
corpus.

Open WebUI enforces **128 MiB per file**. nginx has a larger **256 MiB reverse-proxy ceiling** so multipart/request overhead does not make nginx the accidental
application limit.

See [`RAG.md`](RAG.md) for ingestion and retrieval acceptance testing. Explicit
setting comparisons use `bc250-benchmark owui-embedding-batch`,
`bc250-benchmark owui-chunk-min` and the root-only
`bc250-benchmark owui-system-context`; routine revalidation tests only the packaged
values and does not choose among candidates.

## Local/offline application baseline

The Quadlet keeps authentication enabled and supplies conservative bootstrap
defaults. `bc250-openwebui-setup` also owns the persisted values for Arena,
cloud OpenAI access, community sharing, direct browser connections, code
execution/interpreter and memories so a later database-side admin change is
visible as drift and is reconverged on apply. Arena is disabled rather than
maintaining a separate Arena model pool because the product surface is the
curated office-role set.

The Quadlet additionally sets:

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

Open WebUI persists many settings in its database. The packaged JSON plus the
supported API setup/drift workflow are therefore authoritative for package-owned
application state; the Quadlet is limited to process bootstrap/runtime controls.
The package now provides scheduled, verified config and identity/user backups through
`bc250-maintenance`; those are deliberately scoped recovery artifacts, not a complete
`/var/lib/open-webui` snapshot or an automatic database-migration framework. Keep any
broader operator retention/migration policy explicit and separate.

For a later Open WebUI update, smoke-test normal chat, title/tag tasks, document
upload/extraction, embedding/retrieval, the six active package presets and an
authenticated `bc250-openwebui-setup status` before changing the pin.

## Deferred candidates

Keep these as explicit benchmark candidates, not packaged defaults:

- `RAG_SYSTEM_CONTEXT=true` repeated-turn quality/cache A/B;
- larger embedding batches;
- nonzero `CHUNK_MIN_SIZE_TARGET`;
- any additional Open WebUI tools/subagent fan-out that would increase model
  concurrency or memory pressure.
