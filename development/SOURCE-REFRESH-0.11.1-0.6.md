# Source-only coordination refresh — 0.11.1-0.6

This refresh deliberately keeps:

```text
VERSION=0.11.1
RPM Release=0.6
```

Base source archive reviewed:

```text
amd-bc-250-llm-0.11.1-0.6.zip
SHA-256 a9ca4c3967afc71cbf73ca72e57673253b7077a9f9e65a780afb314dca7b2ebb
```

No installed appliance behavior, install manifest, model definition, service unit,
runtime pin or RPM metadata was changed by this refresh. The changes are intentionally
confined to the Git/source-only `development/` tree.

Added/refreshed development material:

- `VALIDATION-MATRIX.md` — test ownership/state and impact-based requalification map;
- `TESTING-STRATEGY.md` — shared promotion funnel and lane-specific testing order;
- `handovers/DEVELOPMENT-WORKFLOW.md` — versionless workflow rules;
- `handovers/MAIN-INTEGRATION-HANDOVER.md` — durable technical state;
- `handovers/OPERATIONS-HANDOVER.md` — current support/hardware priorities;
- `handovers/SPECIALIST-TESTING-HANDOVER.md` — lightweight temporary specialist template;
- `handovers/README.md` — handover lifecycle/authority rules.

The old strategy of maintaining many parallel specialist handovers is retired. Historical
handover bundles remain useful evidence, but new specialist chats should be generated
from current source and the shared testing strategy when their lane is active.

The durable main handover remains intentionally detailed about hardware/software facts,
resource constraints, role decisions and disproven approaches. It is less strict about
copying release-by-release historical narration because that history now has dedicated
homes in `docs/CHANGELOG.md`, `development/DECISIONS.md` and `development/model-runs/`.
