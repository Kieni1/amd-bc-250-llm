# Patch note — 0.11.3-0.1

## Summary

`0.11.3-0.1` is the greenfield model-lifecycle interface release. It replaces the
pre-0.11.3 `bc250-model` grammar with explicit catalog/state/action verbs, migrates every
active package caller and current-facing operator/development reference to that contract,
and advances whole-appliance revalidation to harness v4.2.

## Model-manager contract

The public lifecycle is:

```text
bc250-model list [CATEGORY]
sudo bc250-model status [CATEGORY] [SELECTION] [--online]
bc250-model path CATEGORY ID
sudo bc250-model apply CATEGORY [SELECTION]
sudo bc250-model refresh CATEGORY [SELECTION]
sudo bc250-model unregister CATEGORY [SELECTION]
sudo bc250-model remove CATEGORY [SELECTION]
sudo bc250-model purge-retired
```

One read-only model inspector owns catalog origin, manager-owned source/provenance,
checksum validity, rendered runtime Modelfile drift, Ollama registration state and
optional moving-revision update comparison. `status` exposes this state and `apply`
consumes the same state.

`apply` converges to the current definition while reusing verified source bytes;
`refresh` deliberately re-fetches source; `unregister` removes registration/runtime
Modelfile while retaining GGUF/state; `remove` also removes manager-owned source/state.
Destructive `remove` does not infer an implicit `all` selection.

The old `install`, `install --refresh`, `cleanup --keep-gguf`, `cleanup`,
`cleanup-retired` and `resolve` forms are intentionally not aliases. They produce
migration guidance. Historical release/campaign evidence retains the syntax it actually
used.

## Revalidation v4.2

The revalidation harness now targets package version `0.11.3`.

- Non-severe context truncation that remains within the existing qualification policy is
  surfaced under an informational `Diagnostics` section instead of being hidden in the
  bundle. Severe early truncation remains a failure under the existing threshold.
- The dedicated GPT-OSS/Jina coexistence stage remains the authoritative deep GPT-OSS
  resource qualification. GPT-OSS is no longer repeated in the generic production edge
  sweep.
- Successful roles/edge/Open-WebUI phase boundaries now use lightweight checkpoints.
  Full snapshots remain at preflight, agent-mode transitions, final restoration and
  failure finalization.
- Direct/backend and Open WebUI product-path semantic qualification remains separate;
  translation/RAG evidence was not thinned merely to reduce runtime.

During final closure, the harness was also corrected from stale
`TARGET_VERSION=0.11.2` to `TARGET_VERSION=0.11.3`; without that correction an installed
0.11.3 RPM would have been rejected before qualification.

## Caller/document reconciliation

Active installer/model wrappers, OCR/MTP helpers, current quality harnesses,
`scripts/validate.py`, focused tests, operator docs, testing strategy, validation matrix,
durable decisions and both current handovers are aligned with the new lifecycle
contract. A final stale-reference sweep leaves old command forms only in intentional
migration hints/tests or historical evidence.

## Deliberate non-changes

No production model identity, model role, Open WebUI role/preset, Ollama topology,
quality threshold, completion-integrity rule, checksum/provenance rule, governor/CU
policy or retirement decision changed. Ornith remains the agent baseline and the
`bc250-code` default output budget remains 3072. Historical `0.11.2-*` device evidence
retains its exact installed release and harness version.

## Validation actually run

- Contract-phase Python compile checks — PASS.
- Contract-phase `tests.test_state` + `tests.test_catalog` — 61/61 PASS.
- Caller/document migration focused set — 98/98 PASS.
- Revalidation v4.2 focused benchmark suite — 127/127 PASS after the v4.2 changes.
- Final `make validate` on the current source:
  - repository/RPM preflight — PASS;
  - packaged shell syntax — PASS;
  - deterministic unit/regression suite — 358/358 PASS.

## Not run here

- Ruff — unavailable in this environment;
- ShellCheck — unavailable in this environment;
- GitHub RPM/SRPM build;
- installed `0.11.3-0.1` model-manager/revalidation execution;
- BC-250 GPU/model/Open WebUI/WOL/power qualification for this release.

## Residual risk / next gate

The source contract is closed, but the redesigned model lifecycle and revalidation v4.2
still need installed-package evidence. GitHub should build `0.11.3-0.1`; the appliance
should capture the exact installed NEVRA, verify normal health, exercise bounded
model-manager state/reconcile operations, and run revalidation v4.2 before hardware
qualification is attributed to this release.

Status: **source-ready, not yet externally/hardware qualified**.
