# BC-250 exact RPM build / device closure specialist handover — 0.12.2-0.8

## Purpose

Own the final package-build and exact-device acceptance of the greenfield-clean, RPM-polished 0.12.2-0.8 source.

This is the highest-priority specialist lane.

Do not use this chat to reopen model tournaments.

## Exact source

```text
bc250-llm-server-0.12.2-0.8
final source/workbench archive hash: record from the delivered artifact or Git revision
predecessor 0.7 checkpoint SHA-256:
9ab3947b73bc4108bb1409feef480f7a894c66dd79e86a34ef6848ea05a25869
```

If a newer Git commit/source archive is supplied, use that exact revision instead and record it.

## Why this lane is needed

Exact 0.12.2-0.7 fresh-device qualification is the immediate baseline. It proved a clean functional appliance: 53/53 core verification, Open WebUI desired-state/authentication success, 40/40 live CU routing with saved-profile reboot restoration, and revalidation Infrastructure/Restoration PASS. Optional Agent coverage was PARTIAL because the add-on was absent.

0.8 is a focused correction over that known-good device baseline. It changes reporting/UX semantics and one safe dependency choice: completed revalidation must remain completed when optional coverage is partial; the Open WebUI translation guard must be reported as PASS when it correctly withholds a raw model integrity defect; installer CU/Agent language must reflect the live-only architecture; completion guidance must not tell operators to repeat setup; and the RPM uses `git-core` instead of the `git` meta-package. Exact acceptance therefore needs a bounded renewal rather than a broad model campaign.

## Build gate

Build in the normal Fedora/GitHub environment.

Record:

```text
Git commit/source SHA
SRPM name/hash
RPM NEVRA/hash
pinned upstream source revisions
build logs/result
```

The final package must not pull the removed replacement-AMDGPU unlock upstream. CI must run `rpmlint -c packaging/rpmlint.toml dist/*.rpm` successfully. The config intentionally filters hardened appliance permissions/ownerships, local prepared-source URLs, known spell/license false positives, missing man-page warnings and narrow scriptlet-command warnings; genuine findings are not filtered.

## Package-content inspection

Verify:

### Must exist

```text
/usr/bin/bc250
/usr/bin/bc250-cu-live-manager
/usr/bin/bc250-40cu
/usr/bin/llm-run-diagnose

/usr/libexec/bc250-llm-server/...
/usr/share/bc250-llm-server/...
/usr/share/doc/bc250-llm-server/...
```

### Must not exist as compatibility API

The RPM must not regenerate a per-route `bc250-*` alias forest. The only `bc250-*` binaries intentionally outside the dispatcher are the two CU tools. Verify this generically from the RPM file list rather than maintaining a second list of dead command names.

### Must not contain

- replacement AMDGPU patch source/assets;
- old 40-CU prepare/enable/restore workflow;
- installed engineering candidate-screen tree;
- active EuroLLM challenger Modelfile;
- obsolete duplicate installed docs;
- GFX1013 compute-queue doc/verifier.

## Install mode

Prefer one deliberate exact-RPM path:

- fresh install for strongest greenfield proof, or
- upgrade only if upgrade preservation is the actual release claim.

Record which one was tested.

## CU acceptance

Normal user setup:

```bash
sudo bc250-cu-live-manager
```

Set/save a known-good 40/40 table through the UI.

Verify:

```bash
sudo bc250-40cu status
```

Required evidence:

- live 40/40;
- saved table recognized;
- boot-restore enabled as intended;
- no unexpected cells;
- no reliance on old kernel-patch preparation.

Then reboot using the supported path and reverify.

Do not fail solely because a kernel/RADV diagnostic counter differs from live routing.

## Core appliance acceptance

Run:

```bash
bc250 status
bc250 verify
bc250 revalidate start
```

Record exact result counts.

Revalidation Agent rule:

```text
Agent absent:
  optional coverage unavailable/skipped/PARTIAL is acceptable

Agent installed:
  actual Agent phase must pass or produce a real staged failure
```

For an absent Agent, a fully executed run must show `Run completion: completed` together with PARTIAL coverage; it must not show `incomplete` merely because optional coverage is unavailable.

For the known DE→FR recommendation-modality fixture, preserve both facts if reproduced: the direct/raw Translate-Gemma result is a quality failure, while an Open WebUI outlet that detects and withholds that unsafe raw result is a passing product-integrity control.

## Open WebUI convergence

Prove:

- private readiness;
- desired-state convergence;
- durable verified `sk-...` admin API key;
- correct Quadlet boot-link behavior;
- nginx publication;
- curated model visibility;
- ordinary user cannot edit curated preset params;
- no stale legacy translation preset.

## RAG smoke

Because RAG is now product-relevant, include a bounded product smoke:

1. verify Tika;
2. verify embedding service;
3. ingest one deterministic small document with `bc250 rag`;
4. retrieve/query via supported product path;
5. confirm answer/citation/known fact as appropriate;
6. clean synthetic data;
7. prove final state.

Do not rerun the old model tournament.

## Structured-output smoke

Only needed if the exact final request-construction path has changed since the focused evidence.

Minimum:

```text
Standard structured
Documents structured
Advanced Structured
ordinary Advanced non-structured control
Deep unchanged control
```

Record effective params rather than inferring them only from output.

## Final state

End with:

```text
normal topology
no failed package units
expected lanes active/inactive
no synthetic chats/files left
no unexpected model registrations
CU 40/40 healthy
bc250 verify clean
```

## Exit interpretation

Separate:

```text
package/build failure
device/runtime failure
optional coverage skip
model-output finding
harness defect
```

Do not make an optional Agent absence fail the release.

Do not make a model-quality result look like package corruption.

## Handover result

Return:

- exact RPM identity/hash;
- exact source identity;
- installation path;
- concise phase table;
- failures/reviews;
- cleanup/restoration state;
- artifact/archive names/hashes;
- whether release freeze/tag is justified.
