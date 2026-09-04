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

Before 1.0 this remains a green-field/test-appliance workflow. The bootstrap installs the selected RPM, then hands off to the packaged
`bc250-install`, which owns Fedora update policy. After that, reruns use:

```bash
sudo bc250-install
sudo bc250-install --models-only   # model/Open WebUI reconciliation
```

Because the 0.x line is greenfield, the RPM owns all four Ollama lane units. `bc250-install` refuses unrelated full-unit overrides instead of attempting an in-place migration; the pinned upstream installer is used for the Ollama binary only.

The packaged installer shows the setup plan, avoids no-op root-LV growth, keeps
the reviewed official Ollama/TTM/swap baseline, and combines kernel update plus
TTM activation into one primary reboot. After reboot it prepares 40-CU support
for the exact running kernel, establishes the static main/task/embedding normal
mode, installs the promoted task and Jina embedding infrastructure models, then
presents one global prompt for additional models. The base Open WebUI Quadlet is deliberately not boot-enabled, so the primary reboot cannot expose an incomplete application. The resumed installer enables and starts Open WebUI only after that model infrastructure is ready, then finishes by applying its
desired state and verifying the appliance. A
second reboot is requested only if persistent 40-CU mode was already configured
and its newly prepared replacement module is not yet loaded.

The model prompt accepts global indexes, ranges, exact names, `recommended`,
`production` or `all`; Enter skips. For unattended setup use
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
sudo bc250-storage status
sudo bc250-storage dedupe          # confirmed XFS extent sharing
sudo bc250-storage prune-sources   # optional verified offline-source removal
sudo bc250-storage prune-40cu      # removed-kernel build caches only
```

Open `http://SERVER_IP/` only from the trusted LAN. The guided installer can
create/sign in the administrator and apply the package-owned Open WebUI baseline;
use `sudo bc250-openwebui-setup init` later if that step was skipped. The default endpoint is unencrypted HTTP; see
[`docs/HARDENING.md`](docs/HARDENING.md) before using a less trusted network.

## Recommended starting models

| Role | Model |
|---|---|
| Standard office work | `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` |
| Documents and RAG | `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` |
| German–French translation | `prod-lfm25-8b-a1b-liquidai-q6-k` |
| General / higher-quality office | `prod-qwen35-9b-unsloth-q6-k` |
| Deep reasoning | `prod-gpt-oss20b-ggml-org-mxfp4` |
| Retrieval embedding | `embed-jina-v5-small-retrieval-q4-k-m` |
| Open WebUI task model | `task-gemma3-1b-unsloth-ud-q4-k-xl` |
| Coding and agentic work | `agentic-qwen25-coder7b-unsloth-q5-k-m` |

The packaged comparison catalog also retains the operator's broader experiment
set and adds `task-lfm25-2.6b-liquidai-q6-k`,
`agentic-ornith15-9b-ornith-q5-k-m`, `exp-qwen38-4b-distill-empero-q6-k`,
`exp-granite42-3b-ibm-q6-k`, `exp-granite42-8b-ibm-q5-k-m`, and
`exp-ling30-tiny-bloomer-q5-k-m`; they are benchmark challengers, not silent
replacements for the defaults above.

These are starting points, not a fixed production set. Packaged and
operator-added `.Modelfile` definitions remain easy to replace for hardware,
quality and quantization comparisons. The Jina embedding model uses a
non-commercial license; review every model's current license before use.

## Daily commands

```bash
# Models
sudo bc250-model list production
sudo bc250-model install production
sudo bc250-model install experiments
sudo bc250-model install embedding
sudo bc250-model install task
sudo bc250-model install agentic   # temporarily switches to agent mode, then restores normal
bc250-ocr list
sudo bc250-rag-import plan /srv/bc250-documents
sudo bc250-openwebui-setup init
sudo bc250-agent-mode enter         # use the registered coding model exclusively
sudo bc250-agent-mode leave

# Profiles and hardware
sudo bc250-memory-profile status
sudo bc250-swap-profile status
sudo bc250-ollama-profile status
sudo bc250-40cu status

# Optional maintenance / storage
sudo bc250-status
sudo bc250-maintenance setup --defaults
# Check/apply package-owned Open WebUI state when needed:
bc250-openwebui-setup status
sudo bc250-maintenance clean-cache
sudo bc250-revalidate status          # opt-in appliance revalidation state

# Compare models and specialized model categories
bc250-benchmark
bc250-benchmark embeddings
bc250-benchmark ocr
bc250-benchmark task
bc250-benchmark agent
bc250-benchmark usecase
bc250-benchmark rag
bc250-benchmark translation
bc250-benchmark rag-quality
```

The complete installed interface and its exact syntax are in
[`docs/COMMANDS.md`](docs/COMMANDS.md).

## Components

| Component | Purpose |
|---|---|
| Cyan Skillfish governor v0.4.12 | BC-250 SMU governor; fresh-install range 350–1850 MHz |
| Ollama v0.33.2 | Vulkan runtime with normal main/task/embedding lanes and exclusive agent mode |
| Open WebUI v0.11.3 and Tika | Digest-pinned local UI, API-driven baseline setup and document extraction |
| nginx | Trusted-LAN HTTP entry point |
| Model manager | Strict Modelfile discovery, GGUF download/registration, OCR experiments and cleanup |
| RAG import | Metadata-aware sync of operator-owned Markdown into Open WebUI Knowledge |
| Operations | Status, verification, benchmark, maintenance and diagnostics |
| CU tools | Default-off replacement-module helper and live WGP manager |

Ollama 0.33.2 is the tested runtime baseline for this release. The relevant
headless change is the 0.33.0 prompt-cache/prefill reliability work; 0.33.1/0.33.2
also contain MLX/desktop changes that are not enabled on the BC-250 Vulkan path.
See [`docs/OLLAMA.md`](docs/OLLAMA.md) for upgrade, rollback and Granite-context notes.

Normal mode uses main `11434`, task `11435` and dedicated embedding `11437`.
Coding/agent mode uses `11436` exclusively and stops the normal lanes. Keep all
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
- `packaging/` and `scripts/`: RPM policy and build tooling;
- `docs/`: operator references.

## Documentation

- [`TLDR.md`](TLDR.md): short installation and operations sheet.
- [`docs/COMMANDS.md`](docs/COMMANDS.md): complete public command reference.
- [`MODELS.md`](MODELS.md): operator model roles, swapping, overrides and cleanup.
- [`models/README.md`](models/README.md): detailed Modelfile discovery/storage contract.
- [`docs/CU-UNLOCK.md`](docs/CU-UNLOCK.md): CU commands, testing and recovery.
- [`docs/RAG.md`](docs/RAG.md): German/French/English office-document and knowledge-base pilot.
- [`docs/MAINTENANCE.md`](docs/MAINTENANCE.md): backups, retention and power.
- [`docs/openwebui-settings.md`](docs/openwebui-settings.md): current UI connections and model roles.
- [`docs/FILESTRUCTURE.md`](docs/FILESTRUCTURE.md): package, configuration and state paths.
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): services, ports and persistent data.
- [`docs/UNINSTALL.md`](docs/UNINSTALL.md): RPM removal versus full purge.

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
