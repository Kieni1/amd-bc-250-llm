# BC-250 patch note — 0.11.3-0.3

Expected NVR: `bc250-llm-server-0.11.3-0.3`

## Why this release exists

Installed `0.11.3-0.2.fc44` qualified the new model-manager/revalidation line on the
BC-250, but the real-device run exposed three UX/quality follow-ups worth closing before
continuing broader campaigns:

1. the installer picker lost useful downloaded/registration/current-state context when
   `bc250-model list` was intentionally made catalog-only;
2. the task `tags-de` case repeated the same double-JSON format miss seen on an older
   installed release, indicating prompt ambiguity rather than an evaluator defect;
3. the new bounded GPT-OSS/Jina context diagnostic was useful but unnecessarily verbose.

## Changes

### State-rich installer model picker

The installer now uses:

```bash
sudo bc250-model status all --include-disabled --compact
```

for the optional model-selection display. This consumes the same shared state inspector
as normal `status`/`apply`, so the picker can show verified source state, runtime
Modelfile state and registration state without turning `bc250-model list` back into a
protected runtime operation.

`bc250-model status` also improves operator auditability:

- `Upstream: not checked` points to `--online`;
- `--verbose` adds source repository, catalog revision and verified local SHA-256 when
  available, plus the existing resolved paths;
- `--compact` provides the one-line state-rich view used by the installer.

### Task tag prompt clarification

The package-owned Open WebUI tag prompt now explicitly requires:

- broad themes and specific subtopics in the same single `tags` array;
- exactly one raw JSON object;
- no second JSON object, prose or Markdown.

The production task model, 128-token tag budget, strict parser/evaluator and quality
thresholds are unchanged. If `tags-de` still fails after install, retain that result as a
real quality miss rather than weakening the contract.

### Revalidation diagnostic presentation

Non-severe GPT-OSS/Jina context truncation remains informational and uses the same
existing severe-truncation policy. The terminal summary now reports the previous and
current prompt-evaluated token counts once and labels the policy result explicitly as
PASS/not-severe.

## Real-device evidence carried forward

Installed `bc250-llm-server-0.11.3-0.2.fc44.x86_64` completed installer verification at
`54 ok / 0 warn / 0 fail` and revalidation v4.2 with infrastructure/restoration PASS and
full coverage. Task remained 5/6 on `tags-de`; direct/Open WebUI translation and RAG,
embeddings, production use cases and agent qualification otherwise passed. The exact run
is recorded under `development/model-runs/2026-09-18-installed-0.11.3-0.2-revalidation.md`.

## Validation boundary

On the final source tree, the deterministic source gate is expected to cover repository/RPM
preflight, packaged shell syntax and 370 unit/regression tests. Ruff and ShellCheck are
workstation-owned and were not run in this environment. GitHub RPM/SRPM build and
`0.11.3-0.3` BC-250 installation/revalidation remain external gates.

## Deliberate non-changes

This release does not change production model identities, Ollama/service topology,
Open WebUI role assignments, CU/governor policy, model retirement decisions, task
request budget or benchmark acceptance thresholds.

## Real-device follow-up

After installing the GitHub-built `0.11.3-0.3` RPM:

1. capture exact installed NEVRA;
2. verify the installer picker/state output and one `bc250-model status ... --verbose`;
3. apply the package Open WebUI desired state and rerun the six-case task qualification;
4. run one full v4.2 revalidation to confirm restoration and the concise diagnostic UX.
