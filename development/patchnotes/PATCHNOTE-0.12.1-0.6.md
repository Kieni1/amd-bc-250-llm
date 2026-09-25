# BC-250 0.12.1-0.6 development patch note

## Release identity

```text
VERSION      0.12.1
RPM Release  0.6%{?dist}
NVR          bc250-llm-server-0.12.1-0.6
```

## Why 0.6 exists

0.5 testing showed that the runtime architecture itself remained sound, but two declared application-plane policies were not yet fully represented by the effective user experience: unrestricted main/task providers did not by themselves make every installed comparison model visible to an ordinary Open WebUI user, and DE→FR legal-modality wording could still strengthen `sollte` into `doit`. Qwen qualification also produced model-specific request-policy evidence that belongs in one existing declarative authority rather than in duplicated prompts, Modelfiles or ad-hoc benchmark flags.

0.6 therefore closes effective-user policy gaps and improves observability. It does not retune the proven topology, memory thresholds, production RAG model, task/embedding choices, live 40-CU policy or Deep residency mitigation.

## Ordinary-user testing-model synchronization

Open WebUI setup now discovers the actual Ollama inventories on normal main `11434` and task `11435`. Static package-owned role/base records remain authoritative where present; additional discovered models receive lightweight package-managed testing records, `user:*:read`, testing/lane tags and optional model-specific qualification metadata. Embedding `11437` and exclusive agent `11436` remain outside normal chat selection.

Stale cleanup is deliberately narrow: only records marked `bc250_managed=testing-discovery` may be removed, and only for a provider lane whose `/api/tags` inventory was successfully inspected during that run. A transient lane/API failure therefore cannot make the package interpret the lane as empty and mass-delete its comparison records. Administrator-created records and unrelated grants remain untouched.

For v1 the ordinary-user selector can return to curated Office roles behind an explicit operator/developer comparison switch, but pre-v1 0.6 continues to expose normal-lane comparison models intentionally.

## Qwen request policy

Do not repack Qwen GGUF chat templates with froggeric v22.5. Corrected GPU-backed paired testing found no meaningful content/reasoning or timing benefit for Qwen3.6 or Qwen3.8 Unsloth, so embedded templates remain authoritative until a real product template defect is reproduced.

The existing `config/openwebui/models.json` is extended instead of adding another model-policy subsystem. It owns qualified request-only policy where applicable:

- production Qwen3.5 / Advanced: `think=false`, temperature `0.7`, `top_p=0.8`, `top_k=20`, `min_p=0`, `presence_penalty=0`, `repeat_penalty=1`;
- Qwen3.6 35B: experimental/memory-edge, non-thinking default for integrated use, named reasoning effort unsupported by its embedded template, model-only deployment experimentally viable but not productized;
- Qwen3.8 ISTA IQ3_S: experimental, predictable non-thinking default, `low` versus `medium` remains the next reasoning experiment;
- Qwen3.8 Unsloth IQ3_S: experimental, `medium` is the preferred reasoning experiment, production RAG remains unqualified on the 16 GiB integrated appliance;
- Qwen3.8 ISTA IQ3_XXS: comparison-only after the basic arithmetic probe returned the wrong result despite comfortable memory fit.

`think` remains request-level and is never written as a Modelfile parameter. Open WebUI status shows effective nested custom parameters, and production-mode generation benchmarking consumes the same policy for `think` and supported sampler values. Setup validates the package model schema fail-closed: only the package's explicit native `params` fields may sit directly under `params`; request-specific values belong under `params.custom_params`, while discovered-model policies use `custom_params`. Focused regressions verify that Advanced/raw-Qwen import payloads retain the exact nested policy and reject both known and previously unknown misplaced request parameters.

## Translation integrity

The existing Translate-Gemma model remains production. Prompts continue to demand source-faithful modality, and the package translation filter now adds bounded post-generation integrity checks rather than attempting to rewrite legal prose automatically. It withholds output for high-confidence recommendation/obligation or permission/obligation drift, apparent loss of an explicit prohibition, or loss of source-critical literal tokens such as dates, currency amounts, IBAN-like values and unique alphanumeric identifiers. Currency and percentage comparison is value-based so equivalent locale separators or currency-code order do not create false positives.

This is intentionally a review/fail-closed layer, not a semantic translation engine. Translation benchmark fixtures add paired `sollte/muss` and `devrait/doit` cases so the reproduced modality defect remains visible in future qualification.

## Diagnostics and evidence UX

`bc250-status` now reports resident model identities from `/api/ps` for each active Ollama lane. If the optional `needs-restarting` helper is unavailable it reports the reboot recommendation as `not checked`, not `unknown` appliance health.

`bc250-revalidate` advances to harness v4.5 and reports exact installed NEVRA separately from target source version and harness version. This is evidence identity, not a premature mismatch abort gate.

`bc250-support-bundle` bounds command captures with a configurable timeout, records TIMEOUT distinctly, validates its internal checksum list before archiving, reopens the finished archive, and verifies the checksum set again before declaring success.

Authenticated Open WebUI verbose status reports effective multi-model-chat permission when the pinned API exposes it, but this administrator-owned permission is informational and is not package-converged.

## Deliberate non-changes / deferred work

- Deep `keep_alive=0`, `OLLAMA_MAX_LOADED_MODELS=1`, normal/task/embed/agent topology, TTM thresholds and live 40-CU behavior are unchanged.
- No generic memory admission controller is introduced; tested compare behavior and explicit Deep unload remain the current safety model.
- No new `bc250-smoke`/acceptance framework is introduced. Existing revalidation remains the evidence authority; a short profile can be added later only if it stays materially smaller than a duplicate harness.
- The two-host/model-only deployment profile is not productized in 0.6. It has capacity value, especially for Qwen3.6 35B, but it creates network authentication/firewall, backup and cross-host lifecycle responsibilities that deserve a separate release.
- Open WebUI remains pinned to 0.11.3.
