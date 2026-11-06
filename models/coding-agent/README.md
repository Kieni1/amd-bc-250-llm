# Isolated coding and agentic models

## Setup and normal lifecycle

The coding helper uses the exclusive Agent lane on port `11436`. Prepare the model
while the appliance is in normal mode, enter Agent mode only for the work itself,
and restore normal topology afterwards:

```bash
sudo bc250 advanced agent prepare agentic-ornith15-9b-ornith-q5-k-m
bc250 advanced agent topology
sudo bc250 advanced agent enter

# run coding/agent work here

sudo bc250 advanced agent normal
bc250 advanced agent topology
```

The helper checks both that the Agent backend is reachable and that the configured
`CODING_AGENT_MODEL` is actually registered before it sends source text. If Agent
mode is active with the wrong model, it stops with the exact recovery sequence
instead of forwarding a request that cannot succeed.

The package ships static `ollama-agent.service` on port `11436` with its own model
store. It has no boot enablement and is intentionally exclusive with the
main/task/embedding lanes. Current active candidates are:

- `agentic-ornith15-9b-ornith-q5-k-m` — current measured default and the canonical
  package Agent qualification target;
- `agentic-qwen25-coder7b-unsloth-q5-k-m` — **retired** legacy coding alternative; no longer in active discovery;
- `agentic-qwable9b-empero-q6-k` — active 9B native-reasoning challenger;
- `agentic-gemma4-e4b-sol-fable-q4-k-m` — compact Gemma 4 E4B challenger;
- `agentic-gemma4-12b-fable5-tau2-q4-k-m` — larger Gemma comparison candidate;
- `agentic-lfm25-24b-a2b-unsloth-q3-k-xl` — larger MoE/A2B agent comparison;
- `agentic-neohorse1-9b-tokenrhythm-q4-k-m` and
  `agentic-neohorse1-9b-uncensored-mradermacher-q4-k-m` — NeoHorse 9B candidates
  kept for explicit agent comparison.

The previously tested `agentic-qwen35-4b-khazarai-q6-k` is retired from active
discovery after the 2026-10-31 DEVICE comparison: it was much faster than Ornith
but showed broader Bash/Python/JSON instruction and output-format regressions.
Historical evidence remains in the retired/provenance material rather than the
active candidate list.

With no model selection, `sudo bc250 model apply agentic` lists active choices and
prompts. Agent model reconciliation may temporarily switch topology and restores
normal mode afterwards. In the 0.20.0-5 OPEN WIP, the scheduled office warmup no longer starts the main Ollama lane while Agent mode is active, and changing the main-lane profile does not terminate that Agent session. Safe-power likewise defers while the Agent lane is active. These are SOURCE changes requiring DEVICE verification; an ordinary `bc250 model apply` against a normal lane can still intentionally leave Agent mode, with an operator notice.

Keep port `11436` blocked from untrusted networks. Add
`http://host.containers.internal:11436` to Open WebUI only for a deliberate
interactive Agent experiment; ordinary office use should leave the Agent lane inactive.

## Local coding helper

```bash
bc250 advanced code run review src/app.py review.md
bc250 advanced code run refactor src/app.py src/app.refactored.py \
  "Keep the public API stable"
CODING_AGENT_MODEL=agentic-ornith15-9b-ornith-q5-k-m \
  bc250 advanced code run document src/app.py docs.md
```

Modes are `generate`, `refactor`, `review`, `document`, `test` and `commit`.
`bc250 advanced code run` uses Ollama `/api/chat` with `think:true` so native reasoning remains
separate from the final file content. It writes only terminal non-empty
`message.content`, refuses `done_reason=length` and literal reasoning markers, and
rejects an outer Markdown code fence for the raw-output `generate`, `refactor`, `test` and
`commit` contracts rather than stripping/guessing. It uses an atomic replacement when an
output path is supplied. The default request
budget is 3072 tokens; set `CODING_AGENT_NUM_PREDICT` to another positive integer
for a deliberate comparison. A truncation failure is evidence to adjust/test the
budget, not permission to keep a partial file.

Generated output is never applied automatically. Treat it like a patch from an
untrusted contributor: inspect the full file/diff, run the real project tests, and
only then copy or commit it. `bc250 advanced benchmark agent` checks Bash/Python syntax and small static semantic
requirements without executing model-generated code, including raw-output
format/reasoning contamination, space-safe Bash patterns, explicit Python range
rejection and JSON key shapes. Agent qualification profiles therefore use
`agent_validation=static-output-contract`; this does not claim native Ollama `tool_calls`
protocol compatibility. It records native thinking separately when the runtime exposes it.

## Local commits and Gitea review

```bash
bc250 advanced code commit

mkdir -p ~/.config/bc250-coding-agent
cp /usr/share/bc250-llm-server/examples/coding-agent/gitea.env.example \
  ~/.config/bc250-coding-agent/gitea.env
chmod 0600 ~/.config/bc250-coding-agent/gitea.env
$EDITOR ~/.config/bc250-coding-agent/gitea.env

bc250 advanced code review OWNER/REPOSITORY 42
bc250 advanced code review OWNER/REPOSITORY 42 --output review.md
bc250 advanced code review OWNER/REPOSITORY 42 --post
```

The commit helper never stages or pushes. Gitea posting shows the complete
comment and asks for confirmation; it never approves or merges. Treat source,
diffs and issue text as untrusted model input.
