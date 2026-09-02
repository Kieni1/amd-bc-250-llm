# Isolated coding and agentic models

## Setup

```bash
sudo bc250-setup-coding-agent

# Current measured coding-helper starting point
sudo bc250-setup-coding-agent agentic-qwen25-coder7b-unsloth-q5-k-m
```

The helper creates `ollama-agent.service` on port `11436` with its own model
store. The service is disabled at boot and is intentionally exclusive with the
main/task/embedding lanes. Current choices are:

- `agentic-qwen25-coder7b-unsloth-q5-k-m` — current coding-helper starting
  point because it consistently reaches a final answer without reasoning-token
  starvation. The 2026-08-31 run exposed that the old static benchmark was too
  permissive: its Bash answer used whitespace-splitting `xargs` despite the
  space-safe requirement and its Python answer silently ignored out-of-range
  ports. The tightened fixture now checks those requirements explicitly;
- `agentic-ornith15-9b-ornith-q5-k-m` — native-reasoning agent/coding candidate;
- `agentic-qwable9b-empero-q6-k` — native-reasoning comparison candidate.

With no selection, the helper lists the choices and prompts. Keep port `11436`
blocked from untrusted networks. Add `http://host.containers.internal:11436` to
Open WebUI only when interactive agent access is wanted. Use this service
exclusively rather than alongside a large main-model workload.

## Local coding helper

```bash
bc250-code review src/app.py review.md
bc250-code refactor src/app.py src/app.refactored.py \
  "Keep the public API stable"
CODING_AGENT_MODEL=agentic-qwen25-coder7b-unsloth-q5-k-m \
  bc250-code document src/app.py docs.md
```

Modes are `generate`, `refactor`, `review`, `document`, `test` and `commit`.
Generated output is never applied automatically; review it and run the real test
suite. `bc250-benchmark agent` checks Bash/Python syntax and small static semantic
requirements without executing model-generated code, including raw-output
format, space-safe Bash patterns, explicit Python range rejection and JSON key
shapes. It records native thinking separately when the runtime exposes it.

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
