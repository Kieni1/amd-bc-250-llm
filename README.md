# BC-250 local LLM server

Fedora 44 integration for testing local LLMs on AMD BC-250 hardware. The
package provides a Vulkan-oriented Ollama stack, Open WebUI, model management,
hardware profiles, diagnostics and optional BC-250 tools.

This is a pre-production project for a trusted office LAN. It prioritizes
repeatable model comparisons, local data processing and understandable
operator controls. It is not an Internet-facing appliance, and neither model
outputs nor experimental hardware settings should be treated as production
assurances.

## Install

Keep the Fedora 44 binary RPM beside the repository bootstrap and run:

```bash
sudo ./install
```

Before 1.0 this remains a greenfield/test-appliance workflow. The bootstrap installs the selected RPM, then hands off to the packaged
`bc250-install`, which owns Fedora update policy. After that, reruns use:

```bash
sudo bc250-install
sudo bc250-install --models-only   # model/Open WebUI reconciliation
```

Because the 0.x line is greenfield, the RPM owns all four Ollama lane units.
`bc250-install-ollama` rejects a custom `/etc/systemd/system/ollama.service` before
invoking the pinned upstream installer; the upstream installer supplies the binary
only. Reruns reconcile observable appliance state rather than an installer-history
database.

The packaged installer shows the setup plan, avoids no-op root-LV growth, keeps
the reviewed official Ollama/TTM/swap baseline, and combines kernel update plus
TTM activation into one primary reboot. After reboot it prepares 40-CU support
for the exact running kernel, establishes the static main/task/embedding normal
mode, installs every model required by the active package-owned Open WebUI roles
plus the task and Jina embedding defaults, then presents one global prompt only for
experiments, rollback/reference, agent and other optional models. The base Open WebUI Quadlet is deliberately not boot-enabled, so the primary reboot cannot expose an incomplete application. The resumed installer enables and starts Open WebUI only after that model infrastructure is ready, then finishes by applying its
desired state, then offers one default-No optional-setup gate after core appliance
verification. Only when accepted does it separately offer local BC-250 maintenance and
Raspberry Pi integration. Selected optional setup is verified before the installer
finishes. Pi integration keeps HTTP :80 as the office endpoint and uses only restricted
SSH :22; it does not expose internal Open WebUI/Ollama ports. A second reboot is requested only if persistent 40-CU mode was already configured
and its newly prepared replacement module is not yet loaded.

The optional-model prompt accepts global indexes, ranges, exact names, `recommended`,
`production` or `all`; Enter skips optional extras only. Active package-owned role bases
are reconciled before this prompt. For unattended extra-model setup use
`BC250_MODEL_SELECTION`. Runtime routing remains main 11434, task 11435,
embedding 11437 and exclusive agent 11436.

The reviewed fresh-machine memory profile uses only
`ttm.pages_limit=4194304 ttm.page_pool_size=4194304`; the older explicit
`amdgpu.gttsize` and full `amdgpu.ppfeaturemask` settings are not defaults.
40-CU preparation remains dynamically bound to `uname -r`.

## First checks

```bash
sudo bc250-status
sudo bc250-verify
bc250-verify-lan SERVER_IP
```

Storage visibility and explicit reclamation:

```bash
sudo bc250-storage status          # protected accounting requires sudo
sudo bc250-model purge-retired     # preview/purge package-retired model data
sudo bc250-storage dedupe          # confirmed XFS extent sharing
sudo bc250-storage prune-sources   # optional verified offline-source removal
sudo bc250-storage prune-40cu      # removed-kernel build caches only
```

Open `http://SERVER_IP/` only from the trusted LAN. The guided installer can
create/sign in the administrator and apply the package-owned Open WebUI baseline.
Persisted providers, task, embedding and RAG settings come from the single packaged
`openwebui/desired-state.json` through supported APIs; use
`sudo bc250-openwebui-setup init` later if that step was skipped. The default endpoint is unencrypted HTTP; see
[`docs/HARDENING.md`](docs/HARDENING.md) before using a less trusted network.

## Recommended starting models

| Role | Model |
|---|---|
| Standard office work | `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` |
| Documents and RAG | `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` |
| German–French translation | `prod-translate-gemma4-sub-e4b-17s-q4-k-xl` via explicit DE→FR / FR→DE Open WebUI roles |
| General / higher-quality office | `prod-qwen35-9b-unsloth-q6-k` |
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

The packaged comparison catalog retains active measured challengers, including
`exp-granite42-3b-ibm-q6-k`, the former LFM translator as an explicit rollback/reference,
and the compact `agentic-qwen35-4b-khazarai-q6-k` /
`agentic-gemma4-e4b-sol-fable-q4-k-m` coding challengers. Exhausted task/translation comparisons are
kept only in the source graveyard and are not
exposed through normal model discovery. The installed retirement catalog lets
`sudo bc250-model status` identify stale package-retired registrations and
`sudo bc250-model purge-retired` remove only those explicitly catalogued models.
Experimental models are never silent replacements for the defaults above. During `bc250-install`,
required role models are converged first; entries that are already fully current are summarized rather
than printed model-by-model. The optional picker shows compact runtime state for ordinary Ollama
catalog entries only. Download-only MTP candidates never participate in that generic picker or
`apply all`; prepare them explicitly with `bc250-fetch-mtp`.

These are starting points, not a fixed production set. Packaged and
operator-added `.Modelfile` definitions remain easy to replace for hardware,
quality and quantization comparisons. The main lane keeps models warm for 20 minutes
for responsive chat, the compact task lane unloads after each request, and the Jina
embedding lane keeps its small retrieval model warm for 10 minutes. The former task
candidate `exp-qwen38-4b-distill-empero-q6-k` is retired from normal discovery: it
scored much better in focused task tests, but simultaneous residency with GPT-OSS
OOM-killed the task service and safe serialization would reintroduce large-model
cold starts. Do not confuse it with the separate active general comparison
`exp-qwen38-4b-empero-q6-k`. The Jina embedding model uses a non-commercial license;
review every model's current license before use.

## Daily commands

```bash
# Models
bc250-model list production
bc250-model list mtp --all          # experimental/download-only candidates
sudo bc250-fetch-mtp qwen3.5-9b-mtp  # explicit opt-in; not generic convergence
LLAMACPP=/opt/llama.cpp/build/bin/llama-server bc250-compare-mtp qwen3.5-9b-mtp
sudo bc250-model status production
sudo bc250-model status production MODEL --verbose
sudo bc250-model apply production
sudo bc250-model apply experiments
sudo bc250-model apply embedding
sudo bc250-model apply task
sudo bc250-model apply agentic     # temporarily switches to agent mode, then restores normal
sudo bc250-model unregister experiments MODEL  # keep verified source/state for later reuse
sudo bc250-model remove experiments MODEL      # also remove manager-owned source/state
bc250-ocr list
sudo bc250-rag-import plan /srv/bc250-documents
sudo bc250-openwebui-setup init
sudo bc250-agent-mode enter         # use the registered coding model exclusively
sudo bc250-agent-mode leave

# Profiles and hardware
bc250-memory-profile status
bc250-swap-profile status
bc250-ollama-profile status
sudo bc250-40cu status

# Optional maintenance / storage
sudo bc250-status
sudo bc250-maintenance setup --defaults
sudo bc250-maintenance companion status
sudo bc250-maintenance contract
sudo bc250-maintenance run backup
sudo bc250-maintenance run prune      # preflights the protected Open WebUI API key
# Optional Pi setup: companion enable = safe shutdown over SSH; backup export is separate.
# Check/apply package-owned Open WebUI state when needed:
sudo bc250-openwebui-setup status --verbose --owui-token-file /root/owui-test.key
sudo bc250-maintenance clean-cache
sudo bc250-revalidate status          # opt-in appliance revalidation state
# Destructive greenfield reset (operator documents are preserved):
# sudo bc250-reset

# Compare models and specialized model categories
bc250-benchmark generation
bc250-benchmark embeddings
bc250-benchmark ocr
bc250-benchmark task
bc250-benchmark agent
bc250-benchmark usecase
bc250-benchmark rag-cycle
bc250-benchmark translation
bc250-benchmark rag-quality
```

The complete installed interface and its exact syntax are in
[`docs/COMMANDS.md`](docs/COMMANDS.md). Raspberry Pi/WOL/safe-power integration
uses the stable interface in [`docs/MAINTENANCE-CONTRACT.md`](docs/MAINTENANCE-CONTRACT.md).

## Components

| Component | Purpose |
|---|---|
| Cyan Skillfish governor v0.4.12 | BC-250 SMU governor; fresh-install range 350–1850 MHz |
| Ollama v0.34.0 | Vulkan runtime with normal main/task/embedding lanes and exclusive agent mode |
| Open WebUI v0.11.3 and Tika v4.0.0 | Digest-pinned local UI, API-driven baseline setup and document extraction |
| nginx | Trusted-LAN HTTP entry point |
| Model manager | Strict Modelfile discovery, GGUF download/registration, OCR experiments and cleanup |
| RAG import | Metadata-aware sync of operator-owned Markdown into Open WebUI Knowledge |
| Operations | Status, verification, benchmark, maintenance and diagnostics |
| CU tools | Default-off replacement-module helper and live WGP manager |

Ollama 0.34.0 is the package runtime baseline. It keeps the same llama.cpp
revision as 0.33.3; its headline changes are outside the BC-250 Vulkan path,
including desktop integration plus OpenAI-compatible tool-search and response-
compaction work. Re-run the normal BC-250 Vulkan/UMA smoke and revalidation after
the runtime refresh.
See [`docs/OLLAMA.md`](docs/OLLAMA.md) for upgrade, rollback and Granite-context notes.

Normal mode uses main `11434`, task `11435` and dedicated embedding `11437`.
Coding/agent mode uses `11436` exclusively and stops the normal lanes. `bc250-code`
uses the chat API so native thinking is separated from final content and refuses to
write nonterminal, output-limit-truncated or reasoning-contaminated results. Keep all
unauthenticated Ollama APIs blocked from untrusted networks.

## Source and build

`make validate` is the deterministic repository check. The normal RPM build is
the Fedora 44 GitHub Actions workflow in `.github/workflows/build-rpm.yml`; it
produces binary and source RPM artifacts. Maintainers can still use `make rpm`
in a matching Fedora build environment. Third-party governor and CU sources are
pinned in `packaging/upstreams.toml`.

Repository groups:

- `cmd/`: host commands, services and timers;
- `config/`: shipped governor, nginx and container configuration;
- `models/`: Modelfiles and specialized model workflows;
- `quality-checks/`: standalone real-device candidate screens and evidence helpers;
- `packaging/` and `scripts/`: RPM policy and build tooling;
- `docs/`: operator references.

## Documentation

- [`TLDR.md`](TLDR.md): short installation and operations sheet.
- [`docs/COMMANDS.md`](docs/COMMANDS.md): complete public command reference.
- [`MODELS.md`](MODELS.md): operator model roles, swapping, overrides and cleanup.
- [`docs/QUALITY-CHECKS.md`](docs/QUALITY-CHECKS.md): standalone candidate-quality screens, evidence bundles and separation from release qualification.
- [`models/README.md`](models/README.md): detailed Modelfile discovery/storage contract.
- [`docs/CU-UNLOCK.md`](docs/CU-UNLOCK.md): CU commands, testing and recovery.
- [`docs/RAG.md`](docs/RAG.md): German/French/English office-document and knowledge-base pilot.
- [`docs/MAINTENANCE.md`](docs/MAINTENANCE.md): backups, retention and power.
- [`docs/openwebui-settings.md`](docs/openwebui-settings.md): current UI connections and model roles.
- [`docs/FILESTRUCTURE.md`](docs/FILESTRUCTURE.md): package, configuration and state paths.
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): services, ports and persistent data.
- [`docs/UNINSTALL.md`](docs/UNINSTALL.md): RPM removal versus greenfield appliance reset.

## Acknowledgements

This repository integrates work from many developers and communities. Special
thanks to:

- [filippor](https://github.com/filippor/cyan-skillfish-governor) and
  [Magnap](https://github.com/Magnap/cyan-skillfish-governor) for the Cyan
  Skillfish governor;
- [fduraibi](https://github.com/fduraibi/bc250-40cu-unlock) and
  [duggasco](https://github.com/duggasco/bc250-40cu-unlock) for 40-CU research;
- [WinnieLV](https://github.com/WinnieLV/bc250-cu-live-manager) for live CU
  routing;
- [DryhoppedIPA](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) for the
  experimental paired GFX1013 kernel/RADV work;
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
