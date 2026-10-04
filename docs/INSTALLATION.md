# Installation and deployment

This is the canonical installation/deployment guide for the BC-250 LLM appliance. It combines the service/persistence deployment notes with the reviewed kernel-command-line profile so setup details have one operator-facing home.

## Deployment and service layout

The default deployment is a pre-production service for one trusted office LAN.
It is not suitable for direct Internet exposure.

### Check the stack

```bash
sudo bc250 status
sudo bc250 verify
sudo systemctl status \
  cyan-skillfish-governor-smu.service \
  ollama.service open-webui.service tika.service nginx.service
curl -f http://SERVER_IP/
```

Open `http://SERVER_IP/` from the trusted LAN. The guided installer can initialize the Open WebUI administrator and package-owned API baseline;
it becomes the administrator.

### Services and ports

| Service | Listener | Purpose |
|---|---|---|
| nginx | `SERVER_IP:80` | Trusted-LAN entry point |
| Open WebUI | `127.0.0.1:3000` | Local UI behind nginx |
| Ollama main | `0.0.0.0:11434` | Production chat, experiments and answer models |
| Ollama task | `0.0.0.0:11435` | Background task model |
| Ollama embedding | `0.0.0.0:11437` | Dedicated retrieval embeddings |
| Ollama agent | `0.0.0.0:11436` | Exclusive coding/agentic mode; inactive in normal mode |
| Tika | private container network | Document extraction |

The rootful Open WebUI container requires the host Ollama listeners. The RPM
does not open ports `11434`–`11437` in firewalld; keep them blocked from
untrusted networks. If firewalld is disabled, enabled Ollama instances are
reachable on all configured host interfaces.


### Fresh-install dependency footprint

The BC-250 RPM itself is small, but a minimal Fedora installation can pull a substantial dependency closure on first install. The active product intentionally requires the Mesa/Vulkan stack, `umr` for live CU routing, Poppler for document/RAG handling and the Hugging Face client for reviewed model downloads. The package uses `git-core` rather than the larger `git` meta-package because only the Git CLI is required. Do not remove compute or document dependencies merely to reduce the transaction count; qualify any dependency change against the feature that uses it.

After the guided installer completes, CU status is expressed in the live-only terms used by the product: **CU live routing**, **saved boot profile**, and **boot restore service**. A missing saved profile/service means the optional live-CU boot restore has not yet been configured; it does not mean the `bc250-cu-live-manager` command is missing.

### Persistent data

```text
/var/lib/bc250-llm-server      GGUFs, rendered Modelfiles and Ollama stores
/var/cache/bc250-llm-server    Hugging Face download and package working caches
/var/lib/open-webui            Accounts, chats, uploads and vector state
/var/backups/bc250-llm-server  Verified local backups and rollback copies
```

Local backups contain private office data and share the appliance disk. Copy
them to encrypted office-controlled storage for protection against disk loss.
Take a complete stopped-service snapshot of `/var/lib/open-webui` before an
Open WebUI upgrade.

The Open WebUI Quadlet uses a private `:Z,U` volume mount. Let Podman apply the
container label when the service starts; do not recursively relabel the data as
ordinary host content.

### Preflight for large models

```bash
sudo bc250 status
free -h
swapon --show
df -h / /var/lib/bc250-llm-server
```

See [`HARDWARE.md`](HARDWARE.md) for the reviewed unified-memory profile and
[`SECURITY.md`](SECURITY.md) for network closure options.

## Kernel command line

The reviewed fresh-machine LLM profile is:

```text
ttm.pages_limit=4194304 ttm.page_pool_size=4194304
```

`sudo bc250 install` owns this profile, applies it with `grubby` across installed kernels and pauses for the required reboot when necessary.

The package deliberately no longer adds `amdgpu.gttsize=14750` or
`amdgpu.ppfeaturemask=0xffffffff`. Controlled BC-250 evidence showed the TTM-only
profile preserved the intended large GTT aperture and tested Ollama/Vulkan behavior.
`amdgpu.gttsize` is also deprecated upstream. Applying the package profile removes
those older overrides so upgrades converge on one reviewed state.

BC-250 safety checks:

- IOMMU is not required by the qualified LLM baseline. Do not force `amd_iommu=on` on an unqualified BIOS configuration; a BIOS-enabled SVM/IOMMU setup must be qualified separately;
- `nomodeset` is installation-only and must be removed once Mesa/AMDGPU is ready;
- follow the current supported Fedora kernel; the package no longer carries historical kernel-version warning ranges;
- the community recommends a 512 MiB dynamic UMA framebuffer; this package does
  not rewrite BIOS settings;
- the gaming-oriented `mitigations=off` suggestion is intentionally not applied
  by this office/RAG appliance.

Always verify after reboot with `sudo bc250 status`, `sudo bc250 verify`, and a representative model load.

Community cross-check: [ElektricM BC-250 kernel guide](https://elektricm.github.io/amd-bc250-docs/linux/kernel/)
and [quick reference](https://elektricm.github.io/amd-bc250-docs/reference/quick-reference/).
