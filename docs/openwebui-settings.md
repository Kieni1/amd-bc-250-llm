# Open WebUI settings

Package candidate baseline: **Open WebUI v0.11.4** with **Ollama v0.34.4** and **Apache Tika v4.0.0-full**. Runtime pins
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
reset it. Verbose status also renders effective nested `params.custom_params` for model/request
policy and, when the pinned API exports it, reports the administrator-owned multi-model-chat
permission without converging that permission.

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
- authenticated-read (`user:*:read`) grants on the six active production presets,
  the six package implementation/task overrides, and package-managed testing records
  dynamically discovered on the normal main/task lanes.

The operator owns users, credentials, custom prompts, unrelated workspace models,
knowledge bases, UI preferences, permissions and any intentional settings that
are outside that baseline. Model presets are imported through the additive
`/api/v1/models/import` endpoint; the package does **not** use destructive model
sync and therefore does not remove operator-created models.
Required model access is converged separately and additively: package desired state
means that required grants must exist, not that the complete ACL must equal a package-owned
set. Existing unrelated grants are retained, including historical grants on inactive records.
The current pre-v1 testing policy keeps raw production/task implementations and ordinary-size
experiments visible, while pressure-heavy large experimental profiles can be package-marked
admin/testing-only. Provider allowlists alone are not treated as proof of the ordinary-user selector. On authenticated
apply/status, `bc250-openwebui-setup` also discovers the actual `11434`/`11435` Ollama inventories and
creates or updates lightweight package-managed testing records. Ordinary-user-visible records receive
additive `user:*:read` access; package-managed records explicitly marked admin/testing-only do not. When a
previously public package-managed discovery record becomes admin/testing-only, convergence may remove only
the package wildcard `user:*:read` grant while preserving unrelated administrator grants.
Only records marked `bc250_managed=testing-discovery` are eligible for stale cleanup, and cleanup is
limited to provider lanes successfully inspected during that run. A temporarily unavailable lane is
therefore never interpreted as an empty lane. Administrator-created records and unrelated grants are
preserved. This is a testing surface, not a promise that every raw model remains user-facing for v1.

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
- raw/testing models are exposed according to package visibility policy; pressure-heavy Qwen3.6 35B,
  Qwen3.8 27B Unsloth and ISTA IQ3_S are admin/testing-only while IQ3_XXS remains the ordinary-user
  deployability comparison; models may retain their own native/default
  behavior unless a package-owned base override says otherwise.

The system prompts in the production Modelfiles remain authoritative for Standard, Documents,
Advanced and Deep. Their Open WebUI presets intentionally do not add a second system prompt. The
translation base Modelfile intentionally has no `SYSTEM`; its exact product contract is owned by the
Open WebUI translation preset plus direction filter.

## OpenAI-style API compatibility boundary

Open WebUI's `/api/chat/completions` endpoint is used internally by package product-path tests, but
the Open WebUI OpenAI-style adapter is **not** an advertised external BC-250 API contract. Exact-device
attribution on the preceding v0.11.3 baseline found three limitations that must be rechecked rather than
assumed fixed merely because the candidate pin is v0.11.4:

- a root OpenAI-style `max_tokens=N` is not reliably propagated as an Ollama generation cap;
- `completion_tokens_details.reasoning_tokens` can be `0` even when `reasoning_content` is present;
- an Ollama `done_reason=length` can be surfaced as OpenAI-style `finish_reason=stop`.

Package-owned callers that require a hard Ollama generation cap use the native nested
`options.num_predict` path. Package preset `params.max_tokens` is a separate Open WebUI model-parameter
path and remains part of the device-tested translation contract. Do not infer absence of reasoning or
absence of truncation from those metadata fields until the v0.11.4 candidate is explicitly requalified.
`/openai/responses` workspace aliases likewise remain outside the qualified product path unless they are
explicitly adopted and tested.

## Package model presets

`bc250-openwebui-setup` imports package-owned workspace presets:

| Preset | Base model | State |
|---|---|---|
| Office – Standard | `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` | active |
| Office – Documents | `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` | active |
| Office – Translation DE → FR | `prod-translate-gemma4-sub-e4b-17s-q4-k-xl` | active |
| Office – Translation FR → DE | `prod-translate-gemma4-sub-e4b-17s-q4-k-xl` | active |
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

The former LFM comparison translator is retired from active discovery and no longer has an Open WebUI
preset. Its source Modelfile remains only in the graveyard as historical comparison evidence.

The Qwen3.5 Advanced preset carries request-level `think=true` for the 0.12.2 quality candidate;
the package keeps Ollama's native renderer/parser rather than replacing the model template. The
existing temperature/top-p/top-k/min-p/presence/repeat sampler policy remains unchanged and the
next device gate decides whether this reasoning-enabled candidate is retained. The Deep Reasoning
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
WebUI v0.11.4 retains its upstream task-token behavior. The helper first reads the
complete v0.11.4 task configuration and then updates only reviewed fields. Those
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
The package provides two distinct backup classes. Scheduled `bc250-maintenance` config and
identity/user backups remain scoped recovery artifacts and are not complete RAG backups. For an
Open WebUI version migration with an existing database, RPM upgrade holds OWUI boot and the guided
installer creates a stopped-state, SQLite-integrity-checked archive of the complete
`/var/lib/open-webui` persistent tree, validates archive members, writes a SHA-256 sidecar and only
then allows the newly pinned image to start. That rollback snapshot is migration safety, not a
replacement for the normal retention policy. The archive preserves numeric ownership, ACLs and
xattrs; the supported restore sequence is documented in [`MAINTENANCE.md`](MAINTENANCE.md).

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
