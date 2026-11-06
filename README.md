# BC-250 local LLM appliance

BC-250 LLM Server is a Fedora 44 appliance for private, local office AI on AMD BC-250 hardware.
It provides a Vulkan-oriented Ollama stack, Open WebUI, managed document workflows, model management,
hardware profiles, diagnostics and optional specialist tools.

Current accepted DEVICE baseline: **`bc250-llm-server-0.20.0-3`**. Its SOURCE, Fedora 44 GitHub BUILD and exact DEVICE upgrade/convergence/reboot/Tika acceptance are closed. The runtime stack remains Ollama 0.40.13, Open WebUI 0.12.5, Tika 4.2.0-full and governor 0.4.14.

The **`bc250-llm-server-0.20.0-4` SOURCE is frozen** as an earlier unaccepted candidate. The **`bc250-llm-server-0.20.0-5` SOURCE is finalized**: the original K6 Documents/RAG and evaluator changes are carried forward with translation-integrity safeguards, managed-document lifecycle corrections, experimental-model pruning, model workflow/Agent topology protections, and maintenance/backup/Pi companion fixes. Production role assignments and pinned upstream runtime remain unchanged. Authoritative Fedora 44 GitHub BUILD and exact-RPM DEVICE acceptance are still future independent gates. After upgrading, rerun `sudo bc250 maintenance setup` to enable the documents backup timer.

This is a pre-production project for a trusted office LAN. It prioritizes
repeatable model comparisons, local data processing and understandable
operator controls. It is not an Internet-facing appliance, and neither model
outputs nor experimental hardware settings should be treated as production
assurances.

## What this appliance is for

For an ordinary office user, the intended entry point is Open WebUI at `http://SERVER_IP/` and the curated **Office** roles: Standard for routine drafting, Documents for grounded work over reviewed local knowledge, Translation for explicit DE↔FR translation, Generalist/Advanced for harder general work, and Deep only when the extra latency is justified. Users should not need to manage raw model names for normal work.

For the appliance operator, the normal lifecycle is intentionally small: `bc250 status`, `bc250 health`, `bc250 verify`, controlled model/document updates, verified local backups, and occasional package upgrades. Advanced benchmark, Agent, MTP and OCR commands are opt-in specialist tools; they are not prerequisites for a healthy office appliance.

The filesystem corpus under `/srv/bc250-documents` remains the source of truth for managed organizational knowledge. Preparation stops at a human-review boundary before content becomes active Open WebUI Knowledge, so the appliance never silently promotes raw files into trusted organizational context.

## Install

Keep the Fedora 44 binary RPM beside the repository bootstrap and run:

```bash
sudo ./install
```

Before 1.0 this remains a greenfield/test-appliance workflow. The bootstrap installs the selected RPM, then hands off to the packaged
`bc250 install`, which owns Fedora update policy. After that, reruns use:

```bash
sudo bc250 install
sudo bc250 install --models-only   # model/Open WebUI reconciliation
```

When an RPM upgrade changes the pinned Open WebUI image and an existing database is present, RPM `%pre` unconditionally requests Open WebUI stop, proves `ActiveState=inactive`, and holds boot enablement before the new Quadlet can become restart-eligible. Run `sudo bc250 install` to create/verify the rollback snapshot and perform the guided migration; see [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

Because the 0.x line is greenfield, the RPM owns all four Ollama lane units. `bc250 install`
reconciles the exact package-qualified upstream Ollama payload and keeps service topology under
RPM ownership. Reruns reconcile observable appliance state rather than an installer-history database.

The packaged installer shows the setup plan, avoids no-op root-LV growth, keeps
the reviewed official Ollama/TTM/swap baseline, and combines kernel update plus
TTM activation into one primary reboot. After reboot it establishes the static main/task/embedding normal
mode, installs every model required by the active package-owned Open WebUI roles
plus the task and Jina embedding baselines, then presents one global prompt only for experiments,
Agent add-ons, rollback/reference and other optional models. Ornith remains the recommended Agent
when installed, but Agent coverage is optional and is not downloaded by the baseline installer. The base Open WebUI Quadlet is deliberately not boot-enabled, so the primary reboot cannot expose an incomplete application. The resumed installer enables and starts Open WebUI only after that model infrastructure is ready, then finishes by applying its
desired state, then offers local BC-250 maintenance and Raspberry Pi/companion integration
as two separate optional setup decisions after core appliance verification. Both top-level choices remain optional/default-No; Pi/companion setup
remains separate. Selected optional setup is verified before the installer
finishes. Pi integration keeps HTTP :80 as the office endpoint and uses only restricted
SSH :22; it does not expose internal Open WebUI/Ollama ports. CU routing is configured separately with the packaged live manager on the stock Fedora AMDGPU path.

The optional-model prompt accepts global indexes, ranges, exact names, `recommended`,
`production` or `all`; Enter skips optional extras only. Active package-owned role bases
are reconciled before this prompt. For unattended extra-model setup use
`BC250_MODEL_SELECTION`. Runtime routing remains main 11434, task 11435,
embedding 11437 and exclusive agent 11436.

Model metadata is split by authority: the package catalog owns source/provider/capability/ownership
facts, profiles own BC-250 qualification and comparison intent, Modelfiles own runtime parameters,
and product roles own request policy. Use `bc250 model inspect MODEL --json` for the consolidated
package view and `sudo bc250 model inspect MODEL --effective --json` when protected/effective state
is required. Pre-1.0 `tracking` sources update only through explicit `refresh`; ordinary convergence
reuses the recorded artifact, while `pinned` sources continue to enforce revision+digest.

The reviewed fresh-machine memory profile uses only
`ttm.pages_limit=4194304 ttm.page_pool_size=4194304`; the older explicit
`amdgpu.gttsize` and full `amdgpu.ppfeaturemask` settings are not defaults.
CU expansion uses the packaged live WGP manager on the stock Fedora AMDGPU path.

## First checks

```bash
sudo bc250 status
sudo bc250 status --json    # machine-readable appliance state
sudo bc250 health           # read-only integrated diagnostics
bc250 version               # exact package/runtime identity
sudo bc250 verify
sudo bc250 support-bundle   # redacted mode-0600 archive exported to this directory
```

Release qualification adds `sudo bc250 advanced qualification capture` and the durable
`sudo bc250 advanced resilience ...` manager. See [`docs/QUALIFICATION.md`](docs/QUALIFICATION.md)
for the closed gate format, Tika 4.2 bounded smoke, interruption semantics and
post-reboot Lane 26 resume rules. `sudo bc250 advanced qualification list` inventories package-gate and
resilience evidence; `qualification clean` is dry-run-first and only prunes old terminal evidence.

Storage visibility and explicit reclamation:

```bash
sudo bc250 storage status          # protected accounting requires sudo
bc250 model remove experiments MODEL --explain  # read-only provider-aware removal plan
sudo bc250 model purge-retired     # preview/purge package-retired model data
sudo bc250 storage dedupe          # confirmed XFS extent sharing
sudo bc250 storage prune-sources   # optional verified offline-source removal
```

Open `http://SERVER_IP/` only from the trusted LAN. The guided installer can
create/sign in the administrator and apply the package-owned Open WebUI baseline.
Persisted providers, task, embedding, document-retrieval and local/offline application policy come
from the single packaged `openwebui/desired-state.json` through supported APIs.
During the pre-v1 testing phase the normal main/task Open WebUI providers remain available for
comparison, and `bc250 advanced openwebui` synchronizes their discovered Ollama inventories into
package-managed testing records. Curated Office roles remain the recommended product paths. Raw
production/task models and the selected non-forbidden experiments remain available for comparison. Retired Qwen3.6 35B, Qwen3.8 Unsloth and ISTA IQ3_S are no longer active package-published choices; ISTA IQ3_XXS remains the ordinary-user Deep-fit experiment. New Heretic controls have `forbidden` package exposure (admins may still see raw provider models). Only package-managed discovery records and grants are reconciled; unrelated administrator-created records and grants are preserved.
Agent `11436` and embedding `11437` remain separate from the chat selector by topology. Arena is
package-converged off; use `sudo bc250 advanced openwebui init` later
if that step was skipped. The default endpoint is unencrypted HTTP; see
[`docs/SECURITY.md`](docs/SECURITY.md) before using a less trusted network.

## Recommended starting models

| Role | Model |
|---|---|
| Standard office work | `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` |
| Documents and RAG | `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` |
| German–French translation | `prod-translate-gemma4-sub-e4b-17s-q4-k-xl` via explicit DE→FR / FR→DE Open WebUI roles |
| Generalist (0.20.0 candidate) | `prod-nemotron35-bolt-e4b-atomicchat-uncensored-q6-k` via Office - Generalist (`think=false`, bounded output); community safety-ablated weights, pending DEVICE qualification |
| General / higher-quality office | `prod-qwen35-9b-unsloth-q6-k` via Advanced (`think=true`, `presence_penalty=1.5`) and explicit Advanced Structured (`think=false`, retained `presence_penalty=0.0`) roles |
| Deep reasoning | `prod-gpt-oss20b-ggml-org-mxfp4` |
| Retrieval embedding | `embed-jina-v5-small-retrieval-q4-k-m` |
| Open WebUI task model | `task-lfm25-1.2b-instruct-liquidai-q6-k` |
| Coding and agentic work | `agentic-ornith15-9b-ornith-q5-k-m` |

The completed BC-250 RAG finalist campaign keeps Gemma E4B as the document/RAG default for the
16 GiB profile. Both Gemma E4B and Qwen 9B passed short authenticated Open WebUI RAG testing, but
Gemma retained about 2.7 GiB MemAvailable through a 42-turn continuous-residency run while Qwen
reached the campaign's 512 MiB safety floor after only a few resident subruns. Qwen remains the
separate higher-quality general-office option; this RAG decision is about sustained memory margin,
not a semantic-quality failure.

The accepted 0.20.0-3 release and the 0.20.0-5 SOURCE catalog retain only bounded, role-relevant comparisons. Active experiment candidates include official Index-Translate 9B (with a conditional 2B efficiency variant), TIR Qwen3.5 9B non-thinking, Unsloth Gemma 4 12B QAT, ISTA Qwen3.8 27B IQ3_XXS (the sole remaining Deep fit gate), Spark-X2.6 4B, GLM-OCR and OvisOCR2, and two admin-only Heretic controls. Official LFM3 1.7B is now an **optional `task-*` challenger** on the task lane, not an `exp-*` main-lane model. Redundant Granite 3B, MiniCPM-V, LFM3-VL, DavidAU, ISTA IQ3_S and other eliminated controls have retirement records; they are **not** active discovery or publication targets. Actual candidate identities come from `models/model-catalog.json`; use `bc250 model list` rather than this narrative as the operator inventory. No retirement record deletes previously installed weights automatically.

The manager keeps model capabilities distinct from role-policy and measured quality: the catalog owns provider and intrinsic capability metadata, profiles own qualification/exposure, and Modelfiles own runtime parameters. Native tool capability is not proven by the static Agent output-contract tests. Experimental registration, community model provenance, local memory fit and online model-card claims do not constitute DEVICE promotion; current Standard, Documents, Advanced, Deep, Translation, task and embedding role choices remain unchanged.
Experimental models are never silent replacements for the defaults above. During `bc250 install`,
required role models are converged first; entries that are already fully current are summarized rather
than printed model-by-model. The optional picker shows one indexed overview across ordinary Ollama models and standalone
MTP candidates. For routine interactive model installation, use `sudo bc250 model install`.
Explicit MTP ID/index/range selections prepare and verify the download-only GGUF only; they do not
register Ollama or start llama.cpp. Broad `all`, `recommended` and `production` groups never acquire
MTP, and generic combined `apply all` / `refresh all` remain MTP-free. The specialist
`bc250 advanced mtp list` / `bc250 advanced mtp prepare` entry points remain available for direct
MTP discovery and preparation.

These are starting points, not a fixed production set. Packaged and
operator-added `.Modelfile` definitions remain easy to replace for hardware,
quality and quantization comparisons. The main lane keeps models warm for 20 minutes
for responsive chat, the compact task lane unloads after each request, and the Jina
embedding lane keeps its small retrieval model warm for 10 minutes. The former task candidate `exp-qwen38-4b-distill-empero-q6-k` and the old Qwen3.8 4B general
comparison `exp-qwen38-4b-empero-q6-k` are both retired from normal discovery for different reasons: the task candidate failed the
co-residency envelope, while the later general comparison no longer answers a distinct campaign question
beside current Qwen3.5/LFM3/Spark controls. The Jina embedding model uses a non-commercial license;
community/uncensored candidates may also have different upstream licenses and intentionally modified refusal
behavior, so review each model's current license/provenance before use.

## Daily commands

```bash
sudo bc250 status
sudo bc250 verify
sudo bc250 model status all --compact
sudo bc250 advanced openwebui status
sudo bc250 maintenance status
bc250 advanced agent topology

# Enter/leave the exclusive coding lane only when needed:
sudo bc250 advanced agent enter
sudo bc250 advanced agent leave   # or: sudo bc250 advanced agent normal
```

Keep experiments, MTP qualification, benchmark suites, destructive model lifecycle actions,
reset and maintenance internals out of the normal daily path. Their complete syntax remains in
[`docs/OPERATIONS.md`](docs/OPERATIONS.md); model policy and MTP opt-in details are in
[`MODELS.md`](MODELS.md), and Raspberry Pi/WOL/safe-power operations are also in
[`docs/OPERATIONS.md`](docs/OPERATIONS.md).

## Components

| Component | Purpose |
|---|---|
| Cyan Skillfish governor v0.4.14 | BC-250 SMU governor; fresh-install range 350–1850 MHz |
| Ollama v0.40.13 | Vulkan runtime with normal main/task/embedding lanes and exclusive agent mode |
| Open WebUI v0.12.5 and Tika v4.2.0-full | 1.12 DEVICE-accepted runtime baseline; 1.13 adds no-text/duplicate ingestion UX hardening without changing the dependency pins |
| nginx | Trusted-LAN HTTP entry point |
| Model manager | Strict Modelfile discovery, GGUF download/registration, OCR experiments and cleanup |
| Document lifecycle | Local DE/FR/bilingual preparation, human review, provenance validation and Open WebUI knowledge sync |
| Operations | Status, verification, benchmark, maintenance and diagnostics |
| CU tools | Live WGP manager with saved boot restoration and compact status verification |

Release 0.14.1-1.12 is the accepted runtime/dependency DEVICE baseline. It updated Ollama to 0.40.13, Open WebUI to 0.12.5 and Apache Tika to 4.2.0-full while retaining the four-lane Vulkan/iGPU topology, model set and retrieval tuning; the completed DEVICE campaign also covered malformed-input containment, broad Tika formats, RAG endurance, parallel ingestion, restart persistence and full authenticated revalidation.

Release 0.14.1-1.13 was a historical DEVICE-accepted baseline. Release 0.20.0-3 is now the current accepted package and carries the subsequent quality-campaign/model work, Tika operator-boundary and translation-oracle corrections. The frozen 0.20.0-4 SOURCE proposed K6 and bounded evaluator fixes but never gained transferable BUILD/DEVICE acceptance. Those changes are carried into the finalized 0.20.0-5 SOURCE with subsequent corrections; its authoritative BUILD and DEVICE acceptance have not happened.

Release 0.14.1-1.9 remains an older broad device baseline: it combined the bounded model-management UX update with focused Managed Documents corrections from 1.8 device acceptance. Standalone MTP candidates appear in the same indexed interactive model overview as Ollama models, while explicit MTP selection remains prepare-only and broad convergence excludes MTP. Multi-chunk document normalization fails closed on missing chunk identity, duplicate output or dropped critical identifiers, Agent-mode cleanup covers the readiness-failure window, and review output exposes explicit readiness state.
Runtime updates remain deliberately pinned rather than following upstream automatically.
Open WebUI RPM migrations with existing state are held until a verified stopped-state rollback
snapshot exists; recovery from that archive is documented in
[`docs/OPERATIONS.md`](docs/OPERATIONS.md). See [`docs/OLLAMA.md`](docs/OLLAMA.md)
for Ollama upgrade, rollback and Granite-context notes.

Normal mode uses main `11434`, task `11435` and dedicated embedding `11437`.
Coding/agent mode uses `11436` exclusively and stops the normal lanes. `bc250 advanced code run`
uses the chat API so native thinking is separated from final content and refuses to
write nonterminal, output-limit-truncated or reasoning-contaminated results. Keep all
unauthenticated Ollama APIs blocked from untrusted networks.

## Source and build

`make validate` is the deterministic repository check. The normal RPM build is
the Fedora 44 GitHub Actions workflow in `.github/workflows/build-rpm.yml`; it
produces binary and source RPM artifacts through the SRPM-first authoritative path.
Maintainers can reproduce the source-side release gate with `make release-gate`;
binary RPM construction remains part of the Fedora 44 authoritative build path.
Third-party governor and CU sources are pinned in `packaging/upstreams.toml`.

For repeated local builds, `make clean` keeps the verified `sources/` cache; use
`make clean-sources` only when an upstream refresh is actually wanted. `scripts/ci-local.sh`
defaults to Podman `--pull=missing` and accepts `BC250_BUILD_IMAGE` /
`BC250_BUILD_PULL_POLICY` overrides, so a maintainer can use a prebuilt Fedora builder image
without changing appliance/runtime code. Source integrity checks still run during the normal build.

Repository groups:

- `cmd/`: host commands, services and timers;
- `config/`: shipped governor, nginx and container configuration;
- `models/`: Modelfiles and specialized model workflows;
- `quality-checks/`: source-only engineering candidate screens and evidence helpers (not installed on appliances);
- `packaging/` and `scripts/`: RPM policy and build tooling;
- `docs/`: operator references.

## Documentation

- [`TLDR.md`](TLDR.md): shortest common-path setup and operations sheet.
- [`MODELS.md`](MODELS.md): curated model roles, selection policy and lifecycle guidance.
- [`CHANGELOG.md`](CHANGELOG.md): release history.
- [`docs/INSTALLATION.md`](docs/INSTALLATION.md): installation, deployment, services and kernel command line.
- [`docs/HARDWARE.md`](docs/HARDWARE.md): memory, sensors, governor and live CU routing.
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md): complete command reference, maintenance and companion contract.
- [`docs/OPENWEBUI.md`](docs/OPENWEBUI.md): Open WebUI setup, desired state, roles and API boundary.
- [`docs/OLLAMA.md`](docs/OLLAMA.md): Ollama runtime topology, profiles and safe updates.
- [`docs/RAG.md`](docs/RAG.md): office-document/RAG lifecycle and retrieval policy.
- [`docs/BENCHMARKING.md`](docs/BENCHMARKING.md): benchmarks, qualification and result interpretation. The 0.20.0-3 quality-campaign foundation audits current settings, keeps real PDFs external, separates Tika/retrieval from generation, validates gold evidence against exact extraction output, and requires an explicit retrieval freeze before fixed-evidence replay without changing production defaults.
- [`docs/QUALITY-CHECKS.md`](docs/QUALITY-CHECKS.md): candidate-quality screens and evidence semantics.
- [`docs/SECURITY.md`](docs/SECURITY.md): hardening, network exposure and secret handling.
- [`docs/HTTPS.md`](docs/HTTPS.md): TLS publication example and checklist.
- [`docs/FILESTRUCTURE.md`](docs/FILESTRUCTURE.md): installed package, configuration and state paths.
- [`docs/RESET.md`](docs/RESET.md): RPM removal versus greenfield appliance reset.

## Acknowledgements

This repository integrates work from many developers and communities. Special
thanks to:

- [filippor](https://github.com/filippor/cyan-skillfish-governor) and
  [Magnap](https://github.com/Magnap/cyan-skillfish-governor) for the Cyan
  Skillfish governor;
- [WinnieLV](https://github.com/WinnieLV/bc250-cu-live-manager) for live CU
  routing;
- [ElektricM's BC-250 documentation](https://elektricm.github.io/amd-bc250-docs/),
  [redbeard1083's toolkit](https://github.com/redbeard1083/bc250-toolkit) and
  [the SteamOS toolkit references](https://github.com/rpf16rj/bc250-steamos-real-toolkit)
  for community hardware findings; and
- the Fedora, Linux, Mesa, Ollama, Open WebUI, Hugging Face, Podman, nginx and
  Tika projects that provide the software base.

Exact carried revisions and licensing notes are in
[`licenses/THIRD_PARTY_NOTICES.md`](licenses/THIRD_PARTY_NOTICES.md).

## License

Repository integration code and documentation are GPL-2.0-only. Pinned sources
and model weights retain their own licenses.

The Ollama services set `OLLAMA_NO_CLOUD=1`; this appliance intentionally uses local inference only.
