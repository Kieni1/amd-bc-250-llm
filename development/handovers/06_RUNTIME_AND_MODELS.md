# Runtime and models

## Current package baseline

```text
Ollama       0.40.6
Open WebUI   0.12.3
Tika         4.1.0-full
Governor     0.4.13
```

Do not upgrade these incidentally during unrelated cleanup or product-roadmap work. Runtime/model upgrades require their own reason and evidence.

Ollama 0.40.6 and Open WebUI 0.12.3 were extensively device-proven on the exact 1.4 RPM through Blocks 1–3, including lane/registration restart persistence, Open WebUI desired-state/idempotence/local-first policy, managed RAG, translation/use-case benchmarks and raw Advanced 6144 forwarding. That evidence is the regression baseline, not transferable acceptance for changed 1.5 bytes. The exact selected 1.5 RPM must re-establish the changed-surface smoke and reboot/ordinary-user boundary before DEVICE-VALIDATED status. See `18_TESTING_SIDECHAT_HANDOVER.md` and `20_DEVICE_QUALIFICATION_1_4.md`.

## Normal topology

```text
11434  ollama.service            main/product lane
11435  ollama-task.service       task lane
11437  ollama-embedding.service  embedding lane
11436  ollama-agent.service      optional/exclusive agent mode
3000   Open WebUI loopback backend
80     nginx user-facing HTTP when configured
```

Tika remains private to the application/container network. Open WebUI should not be treated as the policy authority for every backend invariant; package/source configuration owns package policy.

## Current default model identities

The source currently carries these active defaults/roles:

```text
prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl
prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl
prod-translate-gemma4-sub-e4b-17s-q4-k-xl
prod-qwen35-9b-unsloth-q6-k
prod-gpt-oss20b-ggml-org-mxfp4
task-lfm25-1.2b-instruct-liquidai-q6-k
embed-jina-v5-small-retrieval-q4-k-m
agentic-ornith15-9b-ornith-q5-k-m
```

Tests should assert required defaults by identity where necessary, not exact catalog length. Operator-added registrations are valid supported state.

## Optional 1.5 challenger catalog additions

Release 1.5 adds reviewed **optional** challengers without changing production/default/recommended model selection:

```text
exp-lfm25-8b-a1b-unsloth-q6-k-xl
agentic-lfm25-24b-a2b-unsloth-q3-k-xl
exp-gemma4-12b-hauhaucs-uncensored-q4-k-m   (existing entry hardened)
exp-minicpm-v47-1b-openbmb-q4-k-m
```

Boundaries to preserve:

- the LFM 8B and Gemma challengers are experimental, not production defaults;
- the LFM 24B challenger belongs only to the explicit exclusive agent lane and uses the package's agent GGUF ownership path;
- MiniCPM-V is an experimental Ollama-managed multimodal helper, not a replacement for Tika or the production document path;
- local package-managed challenger GGUFs remain checksum-pinned;
- none of these additions belongs in `RECOMMENDED_MODELS` without separate quality/device evidence.

The 1.5 device smoke should prove catalog/registration integrity and one bounded usable generation where practical; it should not turn acceptance into a broad model tournament.

## Model management UX

Preserve:

- production/experimental/task/agentic/embedding grouping;
- explicit optional/experimental choices;
- no-mutation Enter/cancel behavior;
- no silent replacement of production defaults;
- one clear next action in human output.

## Thinking-capable output semantics

Visible answer and hidden reasoning are different data.

For visible-output determinism:

- hash only a non-empty visible response;
- thinking-only output is not visible-response proof;
- never substitute hidden thinking for the user's answer;
- visible answer absent after a completed generation is `INCOMPLETE` for visible-answer acceptance unless the specific contract says otherwise.

Repetition/degeneration remains a quality signal; it should not be normalized away merely because a reasoning budget was exhausted.

## Runtime identity reporting

Privileged verification may inspect exact runtime/container identity. Non-root status must say privileged identity was not inspected rather than inventing a mismatch or claiming a check it could not perform.

## Upgrade policy

Runtime upgrades, context changes and model-policy changes should be their own iterations with explicit evidence. Keep them separate from repository simplification so regressions remain attributable.
