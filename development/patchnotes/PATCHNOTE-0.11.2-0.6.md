# Patch note — 0.11.2-0.6

Release `0.11.2-0.6` is a quality-diagnostics and coding-agent safety update. It keeps
`VERSION=0.11.2`, preserves the production office/task/translation model roles and
runtime topology, and bumps only the RPM release from `0.5` to `0.6` because shipped
runtime/model/evaluator behavior changes.

## Fixed

- **Task failure attribution:** malformed/structurally invalid task output remains a
  quality failure, but language/relevance are no longer reported as independent failures
  when parsing prevents those checks from being meaningful. The observed `tags-de`
  double-JSON response therefore remains a strict `format-contract` failure.
- **Actionable quality summaries:** canonical benchmark summaries retain failed case IDs,
  and revalidation quality output can show the case-level causes plus the relative
  `results.jsonl` evidence path instead of only aggregate counters.
- **Agent evaluator accuracy:** literal reasoning markers are rejected as output-format
  contamination. NUL-safe `xargs -0 -r -n1 basename` is recognized as valid basename
  extraction; omitting `-r` remains a robustness failure for empty directories.
- **`bc250-code` completion integrity:** the helper now uses Ollama `/api/chat` with
  `think:true`, writes only `message.content`, requires a terminal response, refuses
  `done_reason=length`, rejects literal reasoning markers in final content, preserves
  the exact final-content bytes, and continues to replace destination files atomically.
  `CODING_AGENT_NUM_PREDICT` may override the positive output-token budget; the default
  remains 3072 until BC-250 route/budget evidence justifies a different default.

## Added

- `agentic-qwen35-4b-khazarai-q6-k` — compact Qwen3.5 agentic-coding challenger at
  Q6_K, 32K context, and the supplied precise-coding sampling profile.
- `agentic-gemma4-e4b-sol-fable-q4-k-m` — compact Gemma 4 E4B challenger at Q4_K_M,
  conservative 16K context, and deterministic BC-250 qualification sampling.

Both are opt-in comparison models. Ornith remains the default agent/coding baseline;
this release does not promote, retire, or delete any agent model.

## Historical device evidence carried forward

Installed `bc250-llm-server-0.11.2-0.5.fc44.x86_64` completed revalidation harness v4.1
with infrastructure PASS, restoration PASS and full coverage. Open WebUI translation
passed, agent qualification passed 3/3, and task qualification was 5/6 because `tags-de`
returned two valid JSON objects back-to-back instead of one object. That is a real
quality miss; `0.6` changes its diagnosis, not its acceptance.

## Validation scope

On the final corrected `0.11.2-0.6` source, `make validate` passed RPM/source
preflight, packaged shell syntax checks, and **348/348** deterministic unit/regression
tests. The documentation regression suite separately passed **9/9**. The GitHub runner
had exposed one test-only host dependency: a redundant coding-helper subprocess
simulation required `jq` from the runner image. That simulation was removed in favor of
the existing direct helper-contract assertions and the repository shell-syntax gate;
shipped runtime behavior is unchanged.

Ruff and ShellCheck were **not run locally because they are unavailable in this
environment**. No GitHub RPM build and no `0.11.2-0.6` BC-250 runtime/model execution has
run yet. GitHub owns the RPM/package build gate, the developer workstation owns Ruff and
ShellCheck, and the BC-250 owns Ollama/GPU/model/product-path qualification. Do not
interpret source tests as proof that the new `/api/chat` coding route or challenger
models have run successfully on the appliance.

## Device follow-up

After GitHub builds and the BC-250 installs `0.11.2-0.6`, first capture the exact installed
NEVRA and run the normal verifier. Then run one bounded `bc250-code` route/completion
check with Ornith before the four-model comparative agent funnel. A `done_reason=length`
result is an explicit truncation failure and must not be converted into a partial file.
