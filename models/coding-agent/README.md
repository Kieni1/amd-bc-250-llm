# Isolated coding and agentic models

## Setup

```bash
sudo bc250-setup-coding-agent

# Current recommended model
sudo bc250-setup-coding-agent agentic-ornith15-9b-ornith-q5-k-m
```

The helper creates `ollama-agent.service` on port `11436` with its own model
store. Current choices are:

- `agentic-ornith15-9b-ornith-q5-k-m` — recommended starting point;
- `agentic-qwable9b-empero-q6-k` — comparison model.

With no selection, the helper lists the current choices and prompts. Keep port
`11436` blocked from untrusted networks. Add
`http://host.containers.internal:11436` to Open WebUI only when interactive
agent access is wanted.

## Local coding helper

```bash
bc250-code review src/app.py review.md
bc250-code refactor src/app.py src/app.refactored.py \
  "Keep the public API stable"
CODING_AGENT_MODEL=agentic-qwable9b-empero-q6-k \
  bc250-code document src/app.py docs.md
```

Modes are `generate`, `refactor`, `review`, `document`, `test` and `commit`.
Generated output is never applied automatically; review it and run the real
test suite. Main, task and agent services share one GPU, so avoid overlapping
large requests when predictable memory use matters.

## Local commits and Gitea review

```bash
bc250-code-commit

mkdir -p ~/.config/bc250-coding-agent
cp /usr/share/bc250-llm-server/examples/coding-agent/gitea.env.example \
  ~/.config/bc250-coding-agent/gitea.env
chmod 0600 ~/.config/bc250-coding-agent/gitea.env
$EDITOR ~/.config/bc250-coding-agent/gitea.env

bc250-gitea-review OWNER/REPOSITORY 42
bc250-gitea-review OWNER/REPOSITORY 42 --output review.md
bc250-gitea-review OWNER/REPOSITORY 42 --post
```

The commit helper never stages or pushes. Gitea posting shows the complete
comment and asks for confirmation; it never approves or merges. Treat source,
diffs and issue text as untrusted model input.
