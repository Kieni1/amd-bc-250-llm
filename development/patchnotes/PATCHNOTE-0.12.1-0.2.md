# BC-250 LLM server 0.12.1-0.2

Expected NVR: `bc250-llm-server-0.12.1-0.2`

## Release intent

This is a targeted corrective release built on the exact-installed `0.11.3-2.4` acceptance
baseline. It implements three Open WebUI fixes that were reproduced and temporarily validated on
the real BC-250, plus release-provenance/build hardening. It does not transfer hardware
qualification from 2.4 to this new NVR.

## 0.12.1-0.2 follow-up fix

- `bc250-revalidate` no longer hard-codes the historical `0.11.3` package target. It reads the
  package-owned installed `/usr/share/bc250-llm-server/VERSION` file, which is the repository's
  existing `VERSION` authority installed by the RPM manifest.
- Revalidation fails closed when that version file is missing or malformed, and still checks the
  installed RPM's `%{VERSION}` before starting qualification.
- No Open WebUI, model, topology, memory, CU, maintenance, backup, or other runtime policy changes
  are introduced relative to 0.12.1-0.1.

## Product changes

- Converge authenticated-read (`user:*:read`) access on exactly twelve active package-owned model
  records: six curated office presets, five hidden production base-model overrides, and the hidden
  task-model override. Existing unrelated ACL grants are preserved; package ACL desired state is a
  minimum-required contract, not an exact replacement policy. The inactive legacy
  `bc250-office-translation` record is not a required production role and is not proactively
  stripped of historical grants.
- Set `bc250-office-deep-reasoning.params.keep_alive=0`. This unloads GPT-OSS after the Deep
  response so title/tag generation can cold-load the dedicated task model with safe memory
  headroom. Standard and Advanced residency are unchanged.
- Inspect curated presets through `/api/v1/models/export` and base-model overrides through
  `/api/v1/models/base`. Validate the basic API shape before interpreting absence as desired-state
  drift, and use record-appropriate diagnostics.

## Release-quality changes

- Correct `licenses/THIRD_PARTY_NOTICES.md` to the pinned live-manager revision
  `a929085d791f126ce76a60eb609610820fb08066`.
- Add a source-cache patch gate that dry-runs and applies the carried live-manager RPM patch against
  the exact pinned archive and then checks the intended patched semantics. Both `make sources` and
  `make sources-check` run this validation.
- Keep the Open WebUI model API assumptions explicitly tied to the packaged Open WebUI v0.11.3 pin.
- Fold durable regression coverage into `tests/test_openwebui.py`; do not create a release-numbered
  Open WebUI test module.

## Deterministic regression contract

The source suite must cover:

- exact twelve active production model IDs and exact six hidden implementation/task IDs;
- required `user:*:read` access on all twelve production records;
- preservation of unrelated grants and no forced revocation on the inactive legacy translation row;
- active-state and hidden-state drift;
- Deep Reasoning `keep_alive=0` and drift detection;
- preset/base-override two-view status behavior and malformed API-shape handling;
- unrelated operator-owned model rows ignored by package drift checks;
- no API token material emitted by status diagnostics;
- pinned-source notice consistency and real patch applicability.

## Build path

The authoritative RPM build remains Fedora 44 in GitHub CI. The release pipeline is:

```bash
make validate
make sources
make sources-check
make rpm
```

`make rpm` creates Source0, reruns deterministic validation in `%check`, builds both source and
binary RPMs, verifies the installable payload contains `bc250-install-ollama`, and writes RPM
checksums under `dist/`. A developer environment may run only the gates it actually provides; it
must not report an RPM build or hardware qualification that did not occur.

## Exact-device acceptance required after build

A bounded pass is sufficient because the release does not touch the already-qualified broad
runtime surfaces:

1. install the exact new NEVRA and run package convergence;
2. verify all six production office roles are visible and usable by an ordinary user;
3. verify all five production base models and the task model remain hidden;
4. run one ordinary-user Standard request and one Documents request;
5. run Deep Reasoning followed immediately by title and tag generation, verifying GPT-OSS is no
   longer resident before the task-model cold load;
6. confirm no new OOM/kernel allocation/GPU failure event;
7. run authenticated Open WebUI status and `bc250-verify`, targeting
   `54 ok / 0 warn / 0 fail / 0 skipped`;
8. finish with healthy normal topology and Open WebUI readiness.

Do not repeat broad model-switching, translation, RAG lifecycle, topology, Tika, MTP or operations
campaigns unless a corresponding implementation changed.

## Development/test ownership cleanup

- Patch notes now live under `development/patchnotes/` rather than the repository root.
- Git-only `development/` material, including handovers, is not part of deterministic release validation.
- Duplicate documentation/version checks were removed where an existing validation gate already owns the same contract.
