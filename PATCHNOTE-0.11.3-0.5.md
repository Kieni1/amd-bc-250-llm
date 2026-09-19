# BC-250 0.11.3-0.5 patch note — work in progress

## Release identity

VERSION: `0.11.3`  
RPM Release: `0.5`  
Expected NVR: `bc250-llm-server-0.11.3-0.5`

This source iteration focuses on installer/operator UX and diagnostic transparency. It is **not release-closed yet**; packaging/archive tests, GitHub RPM build and exact-source BC-250 qualification are still pending by maintainer direction.

## Current changes

- Add one top-level, default-No installer question before any optional maintenance or Raspberry Pi work. Saying no preserves existing configuration and ends the optional branch immediately.
- Separate local BC-250 maintenance from Pi integration. Existing local maintenance can be left unchanged; Pi power-control SSH and read-only backup export are only offered after an explicit Pi-integration choice.
- Add post-setup checks for selected optional features: root-owned mode-0600 maintenance configuration, enabled timers actually active, newly configured pruning still `DRY_RUN=1`, restricted Pi account/SSH/sudo rule, and read-only export account/rrsync/directories.
- Replace the installer's flat command list with concise blocks for validation/benchmark, models/runtime lanes and further setup. Also print the installed documentation root and important appliance configuration/state/evidence/log paths.
- Revalidation keeps all existing hard thresholds. It now reports MemAvailable below 512 MiB as a non-failing tight-headroom diagnostic while the hard floor remains 128 MiB, and reports accepted `output-budget` cases under `Diagnostics` rather than hiding them behind an overall PASS.

## Deliberate non-changes

- no production model, role or runtime-topology changes;
- no model-quality threshold changes;
- no weakening of the 128 MiB hard MemAvailable floor, context-truncation policy, GPU/device-error handling or restoration checks;
- no MTP-lane changes in this iteration;
- no packaging/archive qualification claimed yet.

## Validation status

Current focused development evidence:

- `tests.test_benchmark`, `tests.test_install`, `tests.test_documentation` and `tests.test_operations`: **190/190 PASS**;
- Bash syntax: installer, revalidation and maintenance entry scripts PASS;
- touched Python test modules compile successfully;
- replaying the new diagnostic logic against the exact installed 0.11.3-0.4 evidence keeps GPT-OSS/Jina policy PASS while surfacing 193 MiB minimum MemAvailable, 8662 -> 8320 non-severe context truncation, and the accepted Gemma office-draft output-budget event.

Final `make validate`, packaging tests, release archives/source-tar equivalence, GitHub RPM build and exact-source BC-250 qualification are intentionally deferred until the 0.5 work is complete.
