# Quality checks and release validation

Installed appliances expose product validation through the canonical commands below. Engineering candidate-screen scripts remain in the source repository under `quality-checks/` and are intentionally not installed on production appliances.

## Routine appliance verification

```bash
sudo bc250 status
sudo bc250 verify
sudo bc250 support-bundle
```

`bc250 verify` distinguishes failures from warnings and checks the packaged runtime, services, CU live-routing state, memory/swap policy, model infrastructure and Open WebUI state. Model-quality findings remain test evidence and must not automatically be relabeled as infrastructure failures. `support-bundle` collects bounded, redacted evidence without including prompts, chats, uploaded document contents or credentials; its mode-0600 archive is exported to the invoking operator's current directory by default, or to an existing `--output-dir`, without changing that directory's permissions. Published JSON evidence is parsed before archiving and after archive extraction; unavailable endpoints are recorded as `.error.txt` rather than malformed or empty `.json` files.

## Full qualification

```bash
sudo bc250 advanced revalidate start
sudo bc250 advanced revalidate status
```

Revalidation exercises packaged defaults, including production model roles, RAG/embedding, translation, structured-output paths, resource safety and restoration. Exact 1.13 DEVICE evidence accepted infrastructure, product integrity and topology restoration while model quality remained MIXED; those model-quality findings remain qualification inputs, not infrastructure defects or automatic production-setting changes. Run completion, infrastructure, quality, restoration and coverage are independent result dimensions: a fully executed run is `completed` even when optional Agent coverage is `partial` because the add-on model is not installed. `incomplete` is reserved for execution/evidence that did not finish.

Translation evidence also separates the underlying model from the delivered product path. A direct Translate-Gemma case may remain `quality-fail` for the documented DE→FR recommendation-strengthening limitation. If the Open WebUI integrity outlet detects that raw defect and withholds it, the product integrity section reports **Translation delivery integrity: PASS** and states that the raw model failure was detected and incorrect delivery withheld, while the raw-model quality failure remains visible in the evidence. A guard false positive remains a product quality failure.

The accepted 1.13 full revalidation carried model-quality investigation inputs that are now being followed through the 0.20 DEVICE work. Qwen3.5 Advanced closed the simple `think=true` versus `think=false` question: production `think=true` passed 15/15 strict cases at about 32.65 s median, while `think=false` was about 3.3× faster at 9.83 s median but failed the same constraint-scheduling task 3/3. The later `presence_penalty=1.5` intervention remains the current control, but repeated DEVICE use has reproduced a broader reasoning-tail/latency family in Advanced while Structured stays short/clean. Keep that as `REVIEW`. The completed focused sampler A/B did not produce a clear overall reliability win, so 0.20.0-3 retains the current Advanced sampler; do not present speed independently from correctness or reopen tuning without a new concrete hypothesis.

Translation selection history is also not open-ended. The earlier tournament selected Translate-Gemma and retired EuroLLM after its Round-1 `muss nicht` case reproducibly switched to English. Current direct qualification still shows model-quality edge cases around modality/recommendation language. The Open WebUI delivery path correctly withheld known raw semantic failures in the interim DEVICE run. A separate `18:00` → `18h00` failure was an evaluator false negative, not evidence of weakened time semantics; 0.20.0-3 gives clock preservation its own locale-aware semantic check instead of treating an hour as a generic numeric token. Keep raw model quality, preservation-oracle quality and fail-closed product delivery as separate result dimensions.

Agent selection is no longer open on the earlier Qwen3.5 4B comparison. Ornith remains the package default, the Qwen3.5 4B challenger is retired after broader Bash/Python/JSON instruction/format regressions, and interim 0.20 DEVICE testing passed the canonical `prepare → normal → enter → readiness → Bash/Python/JSON → normal` lifecycle with restoration. Repeat Agent coverage only when a changed Agent surface or final acceptance scope gives a concrete reason.

## Focused benchmarks

```bash
bc250 advanced benchmark --help
bc250 advanced benchmark generation --profile compare
bc250 advanced benchmark embeddings
bc250 advanced benchmark rag-quality
bc250 advanced benchmark translation
```

Use focused benchmarks for explicit comparison work rather than changing production defaults. Candidate selection and hardware A/B work remain engineering activities.

## Source-only engineering screens

The repository keeps `quality-checks/main/`, `quality-checks/task/`, `quality-checks/translation/`, `quality-checks/package/`, `quality-checks/utils/` and historical evidence recipes for reproducibility. They are not part of the installed appliance interface.


## 2026-10-31 model refresh

The finalized 0.20.0-3 SOURCE retains the package-managed role-specific candidates without transferring DEVICE acceptance from the accepted predecessor or interim 0.20 DEVICE work.
The campaign manifest is the authority for comparison intent. In particular, Office - Generalist
(`prod-nemotron35-bolt-e4b-atomicchat-uncensored-q6-k`) must be compared as a behavior-modified community
candidate, not treated as equivalent to official NVIDIA Bolt. Test DE/FR office quality and instruction
fidelity together with latency/load/memory and benign false-refusal behavior. Official/community pairs
for LFM3, Spark and NeoHorse should use identical task evidence where practical; Index-Translate uses the
shared clause-local translation integrity evaluator; LFM3-VL uses the existing OCR evaluator. Do not
retune production Qwen3.5 from this source refresh alone.
