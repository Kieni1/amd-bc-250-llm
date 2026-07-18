# Open WebUI settings for the BC-250 server

The RPM deliberately keeps application settings user-managed. The Quadlet only
provides the local Ollama connection, private Tika extraction, local embedding
connection and basic privacy flags.

## First boot

Open `http://SERVER_IP/` from the trusted LAN and register immediately. The first
account becomes administrator; subsequent sign-ups are disabled automatically by
Open WebUI. No administrator password or application secret is committed by this
package.

The packaged HTTP endpoint is not encrypted. Complete `docs/HTTPS.md` before using
the service across an untrusted network.

## Connections

```text
Ollama: http://host.containers.internal:11434
Tika:   http://tika:9998
```

Tika is private to the Quadlet network and should never appear as a host/LAN
listener.

## Suggested starting settings

- Authentication: enabled
- OpenAI/API cloud connection: disabled unless explicitly required
- Embedding engine: Ollama
- Embedding model: `nomic-embed-text`
- Content extraction: Tika
- Community sharing and public links: disabled for office use
- Tools, Functions, Pipelines and arbitrary code execution: disabled for ordinary users
- File upload limit: at or below nginx's 256 MiB limit
- One loaded model and one parallel request in Ollama

No default chat model is forced because model installation is operator-selected.

## Container memory limit

The packaged Quadlet allows Open WebUI 2 GiB. For unusually large concurrent
RAG uploads, copy the vendor Quadlet to `/etc/containers/systemd/`, adjust
`Memory=`, then run `sudo systemctl daemon-reload` and restart
`open-webui.service`. A file in `/etc/containers/systemd/` overrides the vendor
definition and remains administrator-owned.

## Suggested model roles

| Example | Use | Context starting point |
|---|---|---:|
| `gemma4-e4b-unsloth-qat-ud-q4-k-xl` | Documents and RAG | 32,768 |
| `gpt-oss20b-ggml-org-mxfp4` | Deeper analysis | 8,192–16,384 |
| `ministral3-8b-unsloth-ud-q5-k-xl` | Translation | 32,768 |
| `qwen3-4b-lmstudio-q6-k` | Fast office work | 8,192 |
| `qwen35-9b-hauhaucs-uncensored-q6-k` | General comparison | 32,768 |

All contexts must be validated for full GPU residency on the particular board.
Model output is not authoritative; verify consequential facts against source
material.
