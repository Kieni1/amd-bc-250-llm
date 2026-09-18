# Isolated coding and agentic models

## Setup

```bash
sudo bc250-model apply agentic

# Current measured coding-helper starting point
sudo bc250-model apply agentic agentic-ornith15-9b-ornith-q5-k-m
```

The package ships static `ollama-agent.service` on port `11436` with its own model
store. It has no boot enablement and is intentionally exclusive with the
main/task/embedding lanes. Current choices are:

- `agentic-ornith15-9b-ornith-q5-k-m` — current default. Temperature 0 with a
  3072-token Bash/Python budget passed all 3 agent fixtures in three consecutive
  real BC-250 runs with identical final answers;
- `agentic-qwen25-coder7b-unsloth-q5-k-m` — retained as an alternative coding
  model, but no longer the package default;
- `agentic-qwable9b-empero-q6-k` — active 9B native-reasoning challenger;
- `agentic-qwen35-4b-khazarai-q6-k` — compact Qwen3.5 Q6_K agentic-coding
  challenger with the supplied precise-coding sampling profile;
- `agentic-gemma4-e4b-sol-fable-q4-k-m` — compact Gemma 4 E4B Q4_K_M
  challenger using a conservative 16K deterministic BC-250 test profile;
- `agentic-gemma4-12b-fable5-tau2-q4-k-m` — retained 12B Gemma 4 comparison
  until the E4B challenger establishes whether another 12B round is useful.

With no selection, `bc250-model apply agentic` lists the choices and prompts. Registration temporarily switches to agent mode and restores normal mode afterwards. Keep port `11436`
blocked from untrusted networks. Add `http://host.containers.internal:11436` to
Open WebUI only when interactive agent access is wanted. Use this service
exclusively rather than alongside a large main-model workload.

## Local coding helper

```bash
bc250-code review src/app.py review.md
bc250-code refactor src/app.py src/app.refactored.py \
  "Keep the public API stable"
CODING_AGENT_MODEL=agentic-ornith15-9b-ornith-q5-k-m \
  bc250-code document src/app.py docs.md
```

Modes are `generate`, `refactor`, `review`, `document`, `test` and `commit`.
`bc250-code` uses Ollama `/api/chat` with `think:true` so native reasoning remains
separate from the final file content. It writes only terminal non-empty
`message.content`, refuses `done_reason=length` and literal reasoning markers, and
uses an atomic replacement when an output path is supplied. The default request
budget is 3072 tokens; set `CODING_AGENT_NUM_PREDICT` to another positive integer
for a deliberate comparison. A truncation failure is evidence to adjust/test the
budget, not permission to keep a partial file.

Generated output is never applied automatically; review it and run the real test
suite. `bc250-benchmark agent` checks Bash/Python syntax and small static semantic
requirements without executing model-generated code, including raw-output
format/reasoning contamination, space-safe Bash patterns, explicit Python range
rejection and JSON key shapes. It records native thinking separately when the runtime
exposes it.

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
