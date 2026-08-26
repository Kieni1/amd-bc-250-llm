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

Download the Fedora 44 binary RPM artifact built by the repository's GitHub
Actions workflow and keep it beside the repository's `install` script on the
BC-250. Then run:

```bash
sudo ./install
```

The guided installer:

1. grows the root filesystem when possible;
2. updates Fedora and installs the local binary RPM;
3. installs the official Ollama build;
4. applies the reviewed memory and swap profiles;
5. prepares, but does not enable, optional 40-CU support;
6. offers production, task, agentic, embedding, experiment and explicitly
   selected MTP models; and
7. verifies the result.

Rerun it after the requested reboot. To resume only model selection, use:

```bash
sudo ./install --models-only
```

After installation, start the guided CU/live-manager workflow with
`sudo bc250-40cu`. The package does not choose a stable CU count: test 40, 38,
36 or another available configuration on the individual board. Maintenance
schedules and HTTPS also remain explicit operator decisions.

## First checks

```bash
sudo bc250-status
sudo bc250-verify
bc250-verify-lan SERVER_IP
```

Open `http://SERVER_IP/` only from the trusted LAN and register the first Open
WebUI administrator immediately. The default endpoint is unencrypted HTTP; see
[`docs/HARDENING.md`](docs/HARDENING.md) before using a less trusted network.

## Recommended starting models

| Role | Model |
|---|---|
| Standard office work | `prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl` |
| Documents and RAG | `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` |
| German–French translation | `prod-lfm25-8b-a1b-liquidai-q6-k` |
| Deep reasoning | `prod-gpt-oss20b-ggml-org-mxfp4` |
| Retrieval embedding | `embed-jina-v5-small-retrieval-q4-k-m` |
| Open WebUI task model | `task-gemma3-1b-unsloth-ud-q4-k-xl` |
| Coding and agentic work | `agentic-ornith15-9b-ornith-q5-k-m` |

These are starting points, not a fixed production set. Packaged and
operator-added `.Modelfile` definitions remain easy to replace for hardware,
quality and quantization comparisons. The Jina embedding model uses a
non-commercial license; review every model's current license before use.

## Daily commands

```bash
# Models
bc250-model list production
sudo bc250-fetch-models
sudo bc250-fetch-experiments
sudo bc250-fetch-embeddings
bc250-ocr list
bc250-rag-import plan /srv/bc250-documents
sudo bc250-setup-task-model
sudo bc250-setup-coding-agent

# Profiles and hardware
sudo bc250-memory-profile status
sudo bc250-swap-profile status
sudo bc250-ollama-profile status
sudo bc250-40cu status

# Optional maintenance / storage
sudo bc250-status
sudo bc250-maintenance setup --defaults
sudo bc250-maintenance clean-cache
```

The complete installed interface and its exact syntax are in
[`docs/COMMANDS.md`](docs/COMMANDS.md).

## Components

| Component | Purpose |
|---|---|
| Cyan Skillfish governor v0.4.12 | BC-250 SMU governor; fresh-install range 350–1850 MHz |
| Ollama | Official install, Vulkan-oriented service defaults and three isolated stores |
| Open WebUI v0.11.0 and Tika | Digest-pinned local UI and document extraction |
| nginx | Trusted-LAN HTTP entry point |
| Model manager | Strict Modelfile discovery, GGUF download/registration, OCR experiments and cleanup |
| RAG import | Metadata-aware sync of operator-owned Markdown into Open WebUI Knowledge |
| Operations | Status, verification, benchmark, maintenance and diagnostics |
| CU tools | Default-off replacement-module helper and live WGP manager |

The main Ollama instance uses port `11434`; optional task and agent instances
use `11435` and `11436`. Keep all three unauthenticated APIs blocked from
untrusted networks.

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
- [`models/README.md`](models/README.md): model discovery, addition and storage.
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
