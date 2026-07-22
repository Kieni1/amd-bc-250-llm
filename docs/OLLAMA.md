# Ollama installation and service behavior

Ollama is deliberately not bundled in the RPM. The helper defaults to the
latest official release and can also install a specifically requested version:

```bash
sudo bc250-install-ollama
sudo OLLAMA_VERSION=0.32.1 bc250-install-ollama
```

When Ollama is missing, outdated, or explicitly selected for reinstall, the
helper downloads the official installer and prints its SHA-256 for the
operator's audit record. On every run it also:

- ensures the `ollama` service account and required groups exist;
- creates `/var/lib/ollama`, `/var/lib/bc250-llm-server/ollama/main` and model directories;
- reloads systemd;
- enables and restarts `ollama.service`;
- waits for the local API to answer.

The guided `install` workflow excludes Fedora's `ollama` RPM and installs the
official release in `/usr/local`. If a Fedora Ollama package is already present,
it is removed only after `rpm -e --test ollama` confirms that no installed
package requires it. The workflow stops instead of keeping Fedora and official
Ollama copies side by side. Rerunning the workflow reinstalls the selected local
BC-250 RPM, which also supports retesting a corrected build with the same
version-release.

The packaged drop-in sets:

```text
HOME=/var/lib/ollama
OLLAMA_MODELS=/var/lib/bc250-llm-server/ollama/main
OLLAMA_HOST=0.0.0.0:11434
```

The explicit HOME avoids failures on systems where an existing Ollama account
still has `/usr/share/ollama` as its passwd home.

## Verify

```bash
getent passwd ollama
sudo systemctl status ollama.service --no-pager -l
curl -fsS http://127.0.0.1:11434/api/tags
```

## Network exposure

Ollama listens on all interfaces so rootful Open WebUI can reach the host
service. The package does not open port `11434` in firewalld. Confirm it remains
blocked from untrusted networks:

```bash
sudo firewall-cmd --list-all
ss -ltnp | grep 11434
```

A disabled or incorrectly configured firewall can expose the unauthenticated
Ollama API. Restrict the host to a trusted LAN or add an explicit zone/source
policy. The optional task and agent instances use ports `11435` and `11436` and
must remain blocked as well.

## Isolated task and agent instances

`bc250-setup-task-model` and `bc250-setup-coding-agent` create
`ollama-task.service` and `ollama-agent.service` under `/etc/systemd/system`.
They use separate model stores below `/var/lib/bc250-llm-server/ollama/task` and
`/var/lib/bc250-llm-server/ollama/agent`; neither changes the primary service profile. All three
instances share the same GPU, so overlapping model loads can increase memory
pressure.

See [`../models/README.md`](../models/README.md#storage-behavior-in-ollama) for
blob, manifest and retained source-GGUF storage behavior.

## Updates

A newer model architecture may require a newer Ollama release. The helper
reruns the official installer when the requested version differs:

```bash
sudo OLLAMA_VERSION=<reviewed-version> bc250-install-ollama
sudo OLLAMA_REINSTALL=1 OLLAMA_VERSION=<version> bc250-install-ollama
```

Review upstream release notes before changing versions. Unattended installation
requires `BC250_ASSUME_YES=1`.


## Runtime profiles

The packaged default is the balanced profile:

```text
OLLAMA_NUM_PARALLEL=1
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_CONTEXT_LENGTH=32768
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
```

Switch profiles with:

```bash
sudo bc250-ollama-profile status
sudo bc250-ollama-profile balanced
sudo bc250-ollama-profile max-context
sudo bc250-ollama-profile reset
```

`max-context` uses a 65,536-token server context and `q4_0` KV cache. It saves
more memory than q8_0 but may have a more noticeable quality cost. Context
memory also grows with parallel requests, which is why both profiles retain
`OLLAMA_NUM_PARALLEL=1` and one loaded model.

Profile changes create an `/etc/systemd/system/ollama.service.d/` override,
reload systemd and restart Ollama. They do not change any Modelfile.

## Runtime-setting reference

- https://docs.ollama.com/faq
