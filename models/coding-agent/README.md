# Isolated local coding agent

`bc250-setup-coding-agent` creates `ollama-agent.service` on port `11436` with a
separate model store. The current agentic choices are:

- `agentic-ornith15-9b-ornith-q5-k-m` (recommended)
- `agentic-qwable9b-empero-q6-k`

Nothing is downloaded and no agent service is created during RPM installation.

```bash
sudo bc250-setup-coding-agent agentic-ornith15-9b-ornith-q5-k-m
```

From a source checkout:

```bash
sudo ./models/coding-agent/setup-ollama.sh
```

If the selection is omitted, the helper displays the current choices and
prompts. `CODING_AGENT_SELECTION` accepts the same name/index/range selection
for unattended setup. Revision or checksum overrides require one selected model:

```bash
sudo CODING_AGENT_SELECTION=agentic-ornith15-9b-ornith-q5-k-m \
  CODING_AGENT_REVISION=main \
  bc250-setup-coding-agent
```

Other setup overrides are `CODING_AGENT_BIND` (`0.0.0.0`),
`CODING_AGENT_PORT` (`11436`), `CODING_AGENT_SHA256`,
`CODING_AGENT_GGUF_DIR`, `CODING_AGENT_MIN_FREE_BYTES`, `HF_TOKEN` and
`HF_HOME`. Keep port `11436` blocked from the LAN. Add
`http://host.containers.internal:11436` to Open WebUI when interactive access is
wanted.

## Generate, refactor and review

The client defaults to Ornith 1.5 and port `11436`. Set `CODING_AGENT_MODEL` to
another installed agentic name to compare it. `OLLAMA_URL` or `OLLAMA_HOST`
can override the endpoint.

```bash
bc250-code review src/app.py review.md
bc250-code refactor src/app.py src/app.refactored.py \
  "Keep the public API stable"
CODING_AGENT_MODEL=agentic-qwable9b-empero-q6-k \
  bc250-code document src/app.py docs.md
```

Generated code is never applied automatically. Review it and run the real test
suite. The primary, task and agent Ollama services share one GPU; avoid
simultaneous heavy requests when predictable memory use matters.

## Local commits

Stage only the intended changes, then run `bc250-code-commit`. The command shows
the proposed message and asks before creating a local commit. It never stages or
pushes files.

## Gitea pull-request review

Create a limited Gitea token and protect its configuration:

```bash
mkdir -p ~/.config/bc250-coding-agent
cp /usr/share/bc250-llm-server/examples/coding-agent/gitea.env.example \
  ~/.config/bc250-coding-agent/gitea.env
chmod 0600 ~/.config/bc250-coding-agent/gitea.env
$EDITOR ~/.config/bc250-coding-agent/gitea.env

bc250-gitea-review OWNER/REPOSITORY 42
bc250-gitea-review OWNER/REPOSITORY 42 --output review.md
bc250-gitea-review OWNER/REPOSITORY 42 --post
```

Posting displays the complete comment and asks for confirmation. It never
approves or merges. Treat source, diffs and issue text as untrusted model input.

## Remove

```bash
sudo systemctl disable --now ollama-agent.service
sudo rm -f /etc/systemd/system/ollama-agent.service
sudo systemctl daemon-reload
sudo rm -rf /var/lib/bc250-llm-server/ollama/agent \
  /var/lib/bc250-llm-server/gguf/agent \
  /var/lib/bc250-llm-server/modelfiles/agent
```
