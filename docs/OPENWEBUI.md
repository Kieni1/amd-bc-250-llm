# Open WebUI

Current 0.14.1-1.12 source candidate: **Open WebUI v0.12.5** with **Ollama v0.40.13** and **Apache Tika v4.2.0-full**. Runtime pins
are recorded in `/usr/share/bc250-llm-server/runtime.env`.

The package uses two layers deliberately:

1. the Quadlet supplies safe bootstrap/offline defaults so a new database starts
   locally and conservatively;
2. `/usr/share/bc250-llm-server/openwebui/desired-state.json` is the single
   package authority for persisted providers/task/embedding/RAG settings and the
   small local/offline application-policy subset owned by the appliance;
   `bc250 advanced openwebui` applies it through supported administrator APIs.

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
sudo bc250 advanced openwebui init
sudo bc250 advanced openwebui init --token-file FILE
OWUI_API_KEY=TEMPORARY_ADMIN_KEY sudo -E bc250 advanced openwebui apply
bc250 advanced openwebui status
sudo bc250 advanced openwebui status --verbose
OWUI_API_KEY=TEMPORARY_ADMIN_KEY sudo -E bc250 advanced openwebui status
sudo bc250 advanced openwebui save-key --token-file FILE
```

`init` offers administrator sign-in/create or protected API-key-file authentication.
When the verified package credential at `/var/lib/bc250-llm-server/secrets/openwebui-admin.key`
is present, package consumers use it automatically. An explicit `--token-file FILE` overrides that
default. `status` without usable authentication checks reachability only; with the package key, a temporary
administrator key, or `--token-file`, it also compares package-owned settings with the reviewed desired state.
Add `--verbose` to print the verified active role/base-model mapping, translation budget/filter attachment,
task/RAG defaults and package-owned Function state. The installer may hold a sign-in JWT or supplied bearer token briefly
under `/run` for convergence and removes that temporary copy on exit. That temporary JWT is not the durable
maintenance credential. When the operator explicitly requests a package maintenance key, the helper enables
Open WebUI API-key support if needed, reuses the administrator's existing `sk-...` key when one already exists
or creates one through `/api/v1/auths/api_key`, verifies it live, then stores only that real API key at the
root-only package path. A legacy package-owned JWT at that path is not silently treated as a durable key and
may be replaced only through the explicit save-key flow. Credential contents are never printed.
A reported difference may be an intentional operator override; `status` does not
reset it. Verbose status also renders effective nested `params.custom_params` for model/request
policy and, when the pinned API exports it, reports the administrator-owned multi-model-chat
permission without converging that permission.

Open WebUI is a Podman Quadlet. Its generated `open-webui.service` is transient and is not directly
`systemctl enable`d. The package controls boot publication by installing/removing the Quadlet `[Install]`
drop-in and reloading systemd; successful publication is verified by the generated unit being wanted by
`multi-user.target` before nginx is enabled.

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
- authenticated-read (`user:*:read`) grants on the seven active production presets,
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
apply/status, `bc250 advanced openwebui` also discovers the actual `11434`/`11435` Ollama inventories and
creates or updates lightweight package-managed testing records. Discovery policy is declarative: an explicit
`testing_model_policies` entry has highest precedence, package catalog/profile capability metadata is next,
and generic testing defaults are only the fallback. Intrinsic capabilities may enable presentation features
such as MiniCPM-V vision/OCR/file-context, but they do not silently enable product request policy: a model
being reasoning- or tool-capable does not by itself force `think` or built-in tools. Ordinary-user-visible records receive
additive `user:*:read` access; package-managed records explicitly marked admin/testing-only do not. When a
previously public package-managed discovery record becomes admin/testing-only, convergence may remove only
the package wildcard `user:*:read` grant while preserving unrelated administrator grants.
Only records marked `bc250_managed=testing-discovery` are eligible for stale cleanup, and cleanup is
limited to provider lanes successfully inspected during that run. A temporarily unavailable lane is
therefore never interpreted as an empty lane. Administrator-created records and unrelated grants are
preserved. This is a testing surface, not a promise that every raw model remains user-facing for v1.


## Open WebUI 0.12.5 settings audit

The 0.12.5 refresh keeps BC-250 deliberately local and fail-closed. In addition to the
persisted application policy above, the Quadlet explicitly disables administrator cross-user
chat browsing and the in-product administrator export surface, OpenAI catch-all passthrough,
upstream version checks, runtime pip installation from Function/Tool frontmatter, remote-code
trust for embedding/reranking models, tool servers, Apps/channels/sub-agents, cloud-drive
integrations, realtime audio and web search. Authentication remains enabled. These are
bootstrap/runtime policy controls rather than a claim that an operating-system administrator is
cryptographically isolated from local data.

Open WebUI 0.12.5 makes the embedding query/content prefixes editable persisted settings. BC-250
therefore owns `Query: ` and `Document: ` through the supported retrieval API as well as fresh-DB
bootstrap environment values. The new embedding save buffer is pinned explicitly at the upstream
`1000`-chunk default. Batch size remains `1`, asynchronous embedding remains off and concurrency
remains `1` because the dedicated local Ollama embedding lane is intentionally serialized.

The audit deliberately does **not** change administrator workspace-visibility semantics, disable
the broader Analytics product, or enable `RAG_SYSTEM_CONTEXT`. Those choices affect operator/UI
or prompt behavior beyond the dependency refresh and require separate product evidence rather
than being inferred from a new upstream default.

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
sudo bc250 advanced agent enter
# coding/agent work
sudo bc250 advanced agent leave
```

Entering agent mode stops main/task/embedding; leaving restores normal mode. Open WebUI itself
remains reachable, and its persisted catalogue may continue to list normal office roles while those
backends are intentionally unavailable. Return with `sudo bc250 advanced agent normal`; do not dynamically
rewrite Open WebUI provider/model state merely to mirror the temporary exclusive topology.
This is intentional on the BC-250 unified-memory pool.

### Curated role tool policy

Open WebUI can inject built-in knowledge/chat tools into native-tool-capable models unless model
metadata disables them. The package therefore makes the role boundary explicit:

- `Office - Standard`, `Office - General / Higher Quality`, `Office - Advanced Structured`,
  `Office - Deep Reasoning` and both translation roles disable built-in tools. They answer ordinary questions from model knowledge and
  still accept pre-injected/attached file context.
- `Office - Documents / RAG` keeps built-in retrieval enabled, but disables unrelated chat-history,
  notes, web, automation and similar tool categories. Knowledge retrieval is therefore concentrated in
  the dedicated document role instead of being silently attempted by general chat roles.
- raw/testing models are exposed according to package visibility policy; Qwen3.6 35B is retired from active candidates,
  Qwen3.8 27B Unsloth and ISTA IQ3_S are admin/testing-only while IQ3_XXS remains the ordinary-user
  deployability comparison; models may retain their own native/default
  behavior unless a package-owned base override says otherwise.

The system prompts in the production Modelfiles remain authoritative for Standard, Documents,
Advanced and Deep. Their Open WebUI presets intentionally do not add a second system prompt. The
translation base Modelfile intentionally has no `SYSTEM`; its exact product contract is owned by the
Open WebUI translation preset plus direction filter.

## OpenAI-style API compatibility boundary

Open WebUI's `/api/chat/completions` endpoint is used internally by package product-path tests, but
the Open WebUI OpenAI-style adapter is **not** an advertised external BC-250 API contract. Historical
exact-device attribution found metadata/compatibility limitations that remain useful interpretation cautions:

- a client-supplied root OpenAI-style `max_tokens=N` is outside the advertised BC-250 contract for Ollama-backed requests;
- `completion_tokens_details.reasoning_tokens` can be `0` even when `reasoning_content` is present;
- an Ollama `done_reason=length` can be surfaced as OpenAI-style `finish_reason=stop`.

Package-owned direct callers that require a hard Ollama generation cap use native nested
`options.num_predict`. Separately, the package-owned Advanced Open WebUI record stores
`params.max_tokens=6144`; the exact 1.4 device campaign captured the supported internal Open WebUI path forwarding that setting to Ollama as `options.num_predict=6144`, with no root-level Ollama `max_tokens`. Later releases treat this as a bounded regression observation when the Open WebUI/Ollama request path changes rather than as an unresolved 4096→6144 migration. The raw outbound capture is not retained in this source tree. The external
OpenAI-style client field above remains outside the advertised product contract. Do not infer absence
of reasoning or truncation from the adapter metadata fields alone.
`/openai/responses` workspace aliases likewise remain outside the qualified product path unless they are
explicitly adopted and tested.

Open WebUI 0.12 also adds several network/tool surfaces that are outside the appliance contract. The package explicitly keeps direct integrations, external tool servers, Tool Search, channels/encrypted channels, Apps, subagents, realtime voice, web search and Google Drive/OneDrive integrations disabled at bootstrap and persisted where supported. Skills are not enabled/adopted by this release; in 0.12.5 Skills remain outside the appliance contract; the upstream optional lazy-loading feature does not change that package policy.

## Package model presets

`bc250 advanced openwebui` imports package-owned workspace presets:

| Preset | Base model | State |
|---|---|---|
| Office – Standard | `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` | active |
| Office – Documents | `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` | active |
| Office – Translation DE → FR | `prod-translate-gemma4-sub-e4b-17s-q4-k-xl` | active |
| Office – Translation FR → DE | `prod-translate-gemma4-sub-e4b-17s-q4-k-xl` | active |
| Office – General / Higher Quality | `prod-qwen35-9b-unsloth-q6-k` | active |
| Office – Advanced Structured | `prod-qwen35-9b-unsloth-q6-k` | active |
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
the current text user message. Its post-generation `outlet()` performs the bounded modality/literal
integrity check. Package qualification follows direct `/api/chat/completions` with
`/api/chat/completed` before scoring the final assistant message, because tagged Open WebUI releases
do not rewrite the direct completion HTTP response with outlet-filter changes.

`bc250 install` now ensures the base model behind every active package-owned Open WebUI
role before applying desired state, including the production Translate-Gemma role. Manual
model installation is therefore needed only for experiments/rollback paths or deliberate
operator changes.

To inspect the live verified contract, an explicit protected token file still overrides the package default:

```bash
sudo bc250 advanced openwebui status --verbose
```

The package may store a verified administrator maintenance API key at
`/var/lib/bc250-llm-server/secrets/openwebui-admin.key` inside a root-owned `0700` secrets directory;
the key file is root-owned `0600`. `bc250 advanced openwebui`, `bc250 verify` and `bc250 advanced revalidate` use this
default automatically when no explicit token file is supplied. Existing keys are never silently overwritten,
and token contents must not be printed or collected in support/revalidation evidence.

The former LFM comparison translator is retired from active discovery and no longer has an Open WebUI
preset. Its source Modelfile remains only in the retired source set as historical comparison evidence.

The Qwen3.5 general Advanced preset carries `think=true` and `max_tokens=6144`; the explicit
`Office - Advanced Structured` preset uses the same base model, 6144-token ceiling and sampler set with
only `think=false`. This is intentionally visible product policy rather than prompt-based automatic switching.
Strict machine-consumed Advanced extraction should use the Structured preset; normal reasoning stays on
General / Higher Quality. Open WebUI 0.12.5 retains the package-owned stored/request parameter path,
including `think` at the Ollama root and `max_tokens` as `options.num_predict`; no package patch to generic
`payload.py` is required.

For other strict structured workflows, use explicit request parameters rather than a global model change:

- Standard: exact JSON schema as `params.format` plus request `temperature=0.0`; do not override `think`.
  The final focused campaign produced 200/200 strict exact outputs with this policy.
- Documents: exact JSON schema as `params.format` plus request `temperature=0.0`; leave the model's thinking policy otherwise unchanged.
  The focused campaign produced 25/25 strict outputs and no larger confirmation is required for this release.
- Advanced Structured: use the explicit preset above; a schema may additionally be supplied as `params.format` when
  the caller has one.
- Deep: leave production behavior unchanged.

Do not infer structured intent by matching prompt text such as `return JSON`, and do not disable reasoning globally.

Deep Reasoning now uses package-owned `keep_alive=2m`. Before either the curated Deep role or the raw
GPT-OSS implementation is admitted, the `bc250_deep_residency` filter inspects the dedicated embedding
and task Ollama lanes through `host.containers.internal`, unloads any resident model through its model API,
and verifies `/api/ps` is empty. If that absence cannot be established, the Deep request is failed/deferred.
This is a narrow pre-Deep residency rule, not a generic scheduler; services are not restarted. Standard and
Advanced keep their existing residency behavior. The GPT-OSS Modelfile also carries an accuracy-first factual
fallback: when reliable recall is insufficient, it should return fewer items and state uncertainty instead of
filling a requested list with plausible names or placeholders. Exact-device acceptance must verify Deep reuse
inside the two-minute window, idle unload, task/embedding cold reload and UMA headroom.

## Task baseline

The API helper selects:

```text
task-lfm25-1.2b-instruct-liquidai-q6-k:latest
```

and keeps title/tag generation on while follow-up, autocomplete, search-query and
retrieval-query generation remain off. `TASK_MODEL_PARAMS` stays `{}` so Open
WebUI v0.12.5 retains upstream ownership of unreviewed task behavior. The helper first reads the
complete v0.12.5 task configuration and then updates only reviewed fields, preserving new/unowned fields. Those
reviewed fields now include package-owned title, tag and retrieval-query prompt
templates so live Open WebUI and direct task qualification share one prompt policy. The
0.11.3-0.3 tag prompt keeps broad themes and specific subtopics in one `tags` array and
requires exactly one raw JSON object with no second object, prose or Markdown; the task
model and 128-token tag budget are unchanged.

## RAG baseline

The dedicated embedding lane uses Jina on `11437`, a 10-minute Ollama keepalive,
batch size 1 and asynchronous embedding disabled. The reviewed retrieval baseline
remains token splitting, 1500-token chunks, 200-token overlap, Markdown-header
splitting, Top K 4, hybrid search off and Tika extraction. Open WebUI is explicitly
set to `TIKA_SERVER_VERSION=4` so it uses the Tika 4 API; smoke-test representative
office/PDF extraction after this major Tika refresh. Exact-device testing with genuine LibreOffice-authored DOCX files confirms that Tika 4 serializes real Word bullets as middle-dot-prefixed lines (`· item`) while preserving heading structure, table Markdown, list ordering and list/table facts through Open WebUI extraction and Documents retrieval. Treat this as a Tika 4 Markdown serialization characteristic; no package-side list-marker rewrite is applied.

Dedicated repeated title/tag testing (single-model and Advanced+Deep chats) also persisted titles and tags reliably with task-lane activity and clean cleanup. The earlier isolated missing-tags event is closed unless reproduced by a future release; task-lane topology and title/tag configuration remain unchanged.

`RAG_SYSTEM_CONTEXT=false` remains the packaged default pending promotion evidence
from repeated-turn RAG acceptance on the real appliance. Likewise keep
`CHUNK_MIN_SIZE_TARGET=0` and embedding batch size 1 until measured on the real
corpus.

Open WebUI enforces **128 MiB per file**. nginx has a larger **256 MiB reverse-proxy ceiling** so multipart/request overhead does not make nginx the accidental
application limit.

See [`RAG.md`](RAG.md) for ingestion and retrieval acceptance testing. Explicit
setting comparisons use `bc250 advanced benchmark owui-embedding-batch`,
`bc250 advanced benchmark owui-chunk-min` and the root-only
`bc250 advanced benchmark owui-system-context`; routine revalidation tests only the packaged
values and does not choose among candidates.

## Local/offline application baseline

The Quadlet keeps authentication enabled and supplies conservative bootstrap
defaults. `bc250 advanced openwebui` also owns the persisted values for Arena,
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
The package provides two distinct backup classes. Scheduled `bc250 maintenance` config and
identity/user backups remain scoped recovery artifacts and are not complete RAG backups. For an
Open WebUI version migration with an existing database—including the current 0.12.5 transition and earlier 0.12.x schema-bearing upgrades—RPM `%pre` unconditionally requests `open-webui.service` stop, proves `ActiveState=inactive`, and removes its boot-enablement drop-in before the new Quadlet payload can become restart-eligible. The guided installer then creates a stopped-state, SQLite-integrity-checked archive of the complete
`/var/lib/open-webui` persistent tree, validates archive members, writes a SHA-256 sidecar and only
then allows the newly pinned image to start. That rollback snapshot is migration safety, not a
replacement for the normal retention policy. The archive preserves numeric ownership, ACLs and
xattrs; the supported restore sequence is documented in [`OPERATIONS.md`](OPERATIONS.md).

For a later Open WebUI update, smoke-test normal chat, title/tag tasks, document
upload/extraction, embedding/retrieval, the seven active package presets and an
authenticated `bc250 advanced openwebui status` before changing the pin.

## Deferred candidates

Keep these as explicit benchmark candidates, not packaged defaults:

- `RAG_SYSTEM_CONTEXT=true` repeated-turn quality/cache A/B;
- larger embedding batches;
- nonzero `CHUNK_MIN_SIZE_TARGET`;
- any additional Open WebUI tools/subagent fan-out that would increase model
  concurrency or memory pressure.
