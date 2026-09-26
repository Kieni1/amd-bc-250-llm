# BC-250 0.12.2-0.1 development patch note

## Release identity

```text
VERSION      0.12.2
RPM Release  0.1%{?dist}
NVR          bc250-llm-server-0.12.2-0.1
```

## Why 0.12.2 exists

Exact-installed 0.12.1-0.6 proved the appliance topology, resource recovery, Deep unload,
ordinary-user lifecycle, RAG path and multi-model serialization were sound, but it left one
production quality issue: Translate-Gemma could strengthen a recommendation into an obligation.
The following model campaign also showed repeatable arithmetic weakness from production Advanced
under `think=false` and uncomfortably low warm-memory headroom in two large experimental 16K
profiles. At the same time, Open WebUI 0.11.4 and Ollama 0.34.4 became relevant pinned upgrade
candidates.

0.12.2-0.1 is therefore a deliberately new device candidate rather than another packaging revision.
It changes runtime pins, selected model/request policy and upgrade qualification contracts, while
retaining the proven four-lane architecture, Mesa/Vulkan backend, Deep unload policy and serialized
large-model behavior.

## Runtime candidates

- Ollama: `0.34.4`, generic Linux AMD64 payload, package-pinned URL/SHA-256.
- Open WebUI: `0.11.4`, standard digest-pinned image; do not switch to the slim image in this tranche.
- Apache Tika: retain `4.0.0-full`; explicitly set `TIKA_SERVER_VERSION=4` in the OWUI container and
  desired state.
- Cyan Skillfish governor: `0.4.13`, with the package retaining the existing 350–1850 MHz normal
  range and explicitly selecting `temp-read = "sysfs"`.

The package keeps Mesa/Vulkan. This release does not switch to the Ollama ROCm archive.

## Migration-safe Open WebUI upgrade

An RPM update with an existing `/var/lib/open-webui/webui.db` now removes the package-owned boot
enablement drop-in. A reboot between package update and guided convergence therefore cannot
silently start the newly pinned OWUI image over existing persistent state.

Before `bc250-install` restores boot enablement or starts the new image it requires a stopped-state
rollback snapshot when existing OWUI data needs migration. The snapshot helper:

- requires the service to be stopped;
- runs SQLite `PRAGMA integrity_check`;
- archives the complete package-owned persistent tree, not only the database;
- rejects unsafe/archive member types and requires `webui.db` to be present;
- creates and verifies a SHA-256 sidecar;
- keeps the result under `/var/backups/bc250-llm-server/rollback/openwebui` with root-only mode.

Only after this succeeds does the installer restore OWUI boot enablement and start the new image.
The device gate must prove the real upgrade/migration/readiness/desired-state sequence and retain the
snapshot as rollback evidence.

## Advanced candidate policy

The production Advanced workspace model remains Qwen3.5 9B Q6_K and keeps its existing sampler
policy:

```text
temperature=0.7
top_p=0.8
top_k=20
min_p=0
presence_penalty=0
repeat_penalty=1
```

For this greenfield test candidate, request-scoped `think` changes from `false` to `true`. It remains
an Open WebUI request policy under `params.custom_params`; it is not encoded in the Modelfile. The
new device phase must test deterministic arithmetic, constraints, structured extraction, history,
latency, memory and visible-answer behavior. A bounded `think=false` reference may be run to decide
whether the new candidate is actually better before release acceptance.

## Translation hardening

The production Translate-Gemma implementation remains unchanged. Package-owned prompts/wrappers now
make the recommendation/obligation distinction explicit:

- German `sollte` must remain a recommendation such as French `devrait`, never `doit`;
- French `devrait` must remain a recommendation such as German `sollte`, never `muss`;
- true `muss` / `doit` obligations remain obligations;
- prohibitions and negation remain intact.

The bounded filter still withholds high-confidence modality corruption rather than rewriting the
translation. Currency/percentage values are compared numerically across locale formatting, while
localized date wording is allowed rather than requiring literal source-date spelling. Benchmark
classification now reports recommendation/obligation drift as `modality` instead of falsely calling
it `source-leakage`.

## Large experimental profile reset

Two profiles are reduced before the next device campaign because successful unload/recovery did not
make their previous routine memory pressure desirable:

- `exp-qwen36-35b-a3b-unsloth-ud-iq3-s`: `num_ctx 16384 -> 8192`;
- `exp-qwen38-27b-unsloth-ud-iq3-s`: `num_ctx 16384 -> 8192`.

The ISTA profiles remain distinct at 8K:

- IQ3_S: quality-oriented experimental profile;
- IQ3_XXS: lower-pressure/deployability-oriented experimental profile.

Device qualification must distinguish a true leak/unload failure from a successful-but-excessively-
tight profile and a comfortable profile. Repeated recovery after sub-512 MiB operation is a profile-
quality signal even when the 128 MiB emergency floor is never crossed.

## Package-owned role/profile metadata

`models/model-profiles.json` now records intended role, profile class, reasoning/residency policy,
context target and specialized role where applicable. This is qualification metadata; Modelfiles
remain runtime-parameter authority.

Translation and OCR implementations must be probed according to their package role rather than
judged as generic chat models. OCR remains a separate image/document product path and is not
qualified by registration or text-only generation alone.

## Open WebUI contract and observability

- OWUI model-record terminology follows upstream semantics: workspace/derived records have
  `base_model_id != null`; direct/base-model override records have `base_model_id == null`.
- Existing desired-state status already compares complete package-owned params/meta/access state for
  all desired models; the next device gate must capture this for every curated preset.
- Critical settings are to be proven at three stages: stored OWUI record, merge/adapter behavior and
  effective Ollama request/runtime. Generated answer quality is not evidence of sampler values.
- Exact browser request shape, reasoning persistence after reload and explicit background-task state
  are next-device evidence requirements, particularly after the 0.11.4 reasoning-stream changes.

## Model-management responsiveness

Independent read-only Ollama registration probes are collected concurrently per distinct host for
status/inventory operations. Mutation, model creation/download, topology changes and agent-mode work
remain serial. This reduces installer/status waiting without introducing shared-state races.

## 40-CU wording

Operator output now separates live routing from optional boot persistence. Healthy `40/40` live CU
routing can coexist with persistent boot activation being disabled; the latter is no longer phrased
as if live 40-CU operation were disabled.

## Version and harness cleanup

The packaged office-usecase fixture also adds a finite-set factual-calibration case with objectively valid/invalid choices and explicit abstention guidance; open-ended factual calibration remains human-review evidence rather than a deterministic release gate.

Package runtime metadata is the authority for pinned runtime version assertions. Source validation
checks version/URL/hash shape and consistency instead of repeating stale version literals in several
places. Revalidation identifies this candidate as harness v4.6; the detailed new device matrix lives
in `development/handovers/RELEASE-TESTING-HANDOVER-0.12.2-0.1.md`.

## Source closure

The source was rechecked after the final model-retirement/visibility cleanup with static preflight,
shell/Python/JSON syntax checks and focused affected-module tests. The full deterministic suite was
intentionally not rerun in this integration pass. The authoritative RPM/SRPM build and exact-device
qualification remain external gates; source closure does not relabel 0.12.1-0.6 device evidence as
qualification of 0.12.2.

## Deliberate non-changes

- `OLLAMA_MAX_LOADED_MODELS=1` stays in all Ollama service lanes.
- Main-lane large-model execution remains serialized.
- Deep keeps request-scoped `keep_alive=0`.
- The separate task and embedding lanes remain.
- Multi-model-chat permission remains administrator-owned and is observed, not package-forced.
- No generic memory scheduler is introduced.
- No pre-emptive multi-model restriction is introduced.
- `/openai/responses` workspace aliases remain outside the qualified product path unless explicitly
  adopted and tested.
- Raw production/task and ordinary-size testing models remain visible, but the pressure-heavy Qwen3.6
  35B, Qwen3.8 27B Unsloth and ISTA IQ3_S records are admin/testing-only; IQ3_XXS remains the
  ordinary-user deployability comparison. Package ACL convergence removes only its own wildcard read
  grant on those package-managed records and preserves unrelated administrator grants.
- Retire Gemma4 26B after repeated wrong/template-contaminated arithmetic and output degeneration;
  retire the LFM 8B comparison translator after it reproduced the same recommendation→obligation
  failure and therefore cannot serve as a credible rollback.
