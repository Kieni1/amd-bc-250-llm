# Quality checks and release validation

Installed appliances expose product validation through the canonical commands below. Engineering candidate-screen scripts remain in the source repository under `quality-checks/` and are intentionally not installed on production appliances.

## Routine appliance verification

```bash
sudo bc250 status
sudo bc250 verify
sudo bc250 support-bundle
```

`bc250 verify` distinguishes failures from warnings and checks the packaged runtime, services, CU live-routing state, memory/swap policy, model infrastructure and Open WebUI state. Model-quality findings remain test evidence and must not automatically be relabeled as infrastructure failures. `support-bundle` collects bounded, redacted evidence without including prompts, chats, uploaded document contents or credentials.

## Full qualification

```bash
sudo bc250 revalidate start
sudo bc250 revalidate status
```

Revalidation exercises packaged defaults, including production model roles, RAG/embedding, translation, structured-output paths, resource safety and restoration. Run completion, infrastructure, quality, restoration and coverage are independent result dimensions: a fully executed run is `completed` even when optional Agent coverage is `partial` because the add-on model is not installed. `incomplete` is reserved for execution/evidence that did not finish.

Translation evidence also separates the underlying model from the delivered product path. A direct Translate-Gemma case may remain `quality-fail` for the documented DE→FR recommendation-strengthening limitation. If the Open WebUI integrity outlet detects that raw defect and withholds the unsafe translation, the product integrity control is reported as **PASS — detected and withheld** while the raw-model failure remains visible in the evidence. A guard false positive remains a product quality failure.

## Focused benchmarks

```bash
bc250 benchmark --help
bc250 benchmark generation --profile compare
bc250 benchmark embeddings
bc250 benchmark rag-quality
bc250 benchmark translation
```

Use focused benchmarks for explicit comparison work rather than changing production defaults. Candidate selection and hardware A/B work remain engineering activities.

## Source-only engineering screens

The repository keeps `quality-checks/main/`, `quality-checks/task/`, `quality-checks/translation/`, `quality-checks/package/`, `quality-checks/utils/` and historical evidence recipes for reproducibility. They are not part of the installed appliance interface.
