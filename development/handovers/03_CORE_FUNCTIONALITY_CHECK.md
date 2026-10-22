# Core functionality check — exact 0.14.1-1.7 RPM


## 1.4 baseline and 1.7 focus

The exact 1.4 RPM already proved the expensive stock-core/runtime/product boundaries through device Block 3. Do not replay that entire campaign merely because the RPM Release changed. The 1.7 round must still bind to exact new bytes and prove the carried runtime changes, changed managed-RAG surfaces and the previously pending reboot/ordinary-user boundary.

Start from a supported install/upgrade state and require:

- exact 1.7 RPM identity/hash and clean `rpm -V`;
- guided installer renders exactly one semantic Ollama observed version (or `unknown`), never connection prose;
- at the intentional publication/convergence hold, `status` reports setup incomplete rather than a false runtime mismatch;
- after convergence, `status`, `health` and `verify` are green and runtime identities still match;
- model catalog remains coherent and no production/recommended role changes unexpectedly;
- one representative Ollama local registration/restart smoke remains stable;
- one managed-RAG replacement path proves atomic activation/provenance plus grounded/unsupported ordinary-user behavior;
- final reboot persistence and ordinary-user Open WebUI paths complete the boundary left pending after 1.4 Block 3.

## Goal

This is a small exact-artifact smoke, not a full qualification campaign.

Before installation record:

```text
selected GitHub run
RPM filename / NEVRA
RPM SHA-256
SRPM SHA-256 if retained
source commit
host/device identity
kernel
```

## Starting-state capture

Keep it short but useful:

- current installed package (if upgrading);
- failed systemd units;
- relevant free memory/swap state;
- package model registrations;
- whether operator-added registrations exist;
- normal service state.

Do not mutate user state just to make the starting state look cleaner.

## Required package/install checks

- install or supported upgrade succeeds;
- `rpm -q bc250-llm-server` reports `0.14.1-1.7` with the expected Fedora dist tag/arch;
- package services/configuration converge without manual repair;
- no experimental GFX/private-RADV/patched-boot requirement appears;
- one ordinary service restart succeeds.

## Required CLI checks

Run:

```text
bc250 version
bc250 status
bc250 health
bc250 verify
```


Confirm output is coherent and does not depend on stale reconstruction-era state. Non-root status must not claim privileged identity was inspected when it was not.

## Runtime/services

Normal topology should be sane:

```text
11434  main Ollama
11435  task Ollama
11437  embedding Ollama
11436  agent Ollama only in explicit agent mode
3000   Open WebUI loopback backend
80     nginx user-facing HTTP when configured
Tika   private application/container network
```

Do not require optional/exclusive agent mode to be active in normal mode.

## Model path

Keep this light:

- catalog/list works;
- Enter/cancel or no-selection path makes no mutation;
- required production model registration is present or can be installed by the supported command;
- run one short normal inference and require a non-empty visible answer.

Hidden thinking is not a substitute for a visible answer.

## Runtime and RAG checks retained for 1.7

Ollama 0.40.6 and Open WebUI 0.12.3 were device-proven on the exact 1.4 artifact through Block 3. Release 1.7 keeps Ollama 0.40.8 and Open WebUI 0.12.3 from the 1.6 source baseline; use the old results as regression baseline, then re-prove representative Vulkan generation, registration/restart persistence and lane identity on the exact 1.7 RPM.

For Ollama 0.40.8:

- all normal lanes (`11434`, `11435`, `11437`) report exactly `0.40.8`;
- a package-owned locally registered GGUF model remains represented by one expected logical model name in `/api/tags`;
- no unexpected `llamacpp:` shadow/duplicate registration is exposed;
- `/api/show` and one generation work before and after an Ollama service restart;
- existing package registrations are not silently deleted or renamed.

For Open WebUI 0.12.3:

- the stopped-state rollback snapshot is created and verified before migration of an existing database;
- login, package model presets, title/tag task lane and document/RAG retrieval still work;
- new tool-server/search, direct-integration, channel, Apps, subagent, realtime-voice, web-search and cloud-drive surfaces remain disabled unless deliberately adopted later;
- the Advanced 6144 path is captured outbound and reaches Ollama as `options.num_predict=6144`; also verify an explicit API `max_tokens` override behaves as documented by Open WebUI 0.12 rather than being confused with the saved preset ceiling.

Do not automatically clean model-store migration artifacts during this smoke. Record unexpected registry state first so rollback remains possible.

For the changed managed-RAG path, use a disposable test collection and require:

- `bc250 rag status` reports review/currentness/fidelity state and lifecycle validation health coherently;
- one reviewed German authoritative revision activates successfully and one French translation points to the exact German `revision_id`;
- an invalid replacement or duplicate same-family/language `--all-ready` set makes no active-corpus mutation;
- a valid replacement supersedes the prior revision while preserving audit evidence;
- Open WebUI sync of the resulting active Markdown succeeds, then one grounded question cites the expected source and one unsupported question does not invent a document fact.

Do not turn this into a document/model tournament. The managed preparation input remains PDF-only for this release.

## Reboot persistence

Perform one supported reboot and confirm:

- stock boot returns normally;
- required services recover;
- `bc250 status` / `health` remain sane;
- selected model remains usable;
- no new failed units or obvious package-state drift appears.

## Optional, only if inexpensive

- browser login/use through the Web interface;
- one short translation request;
- one additional document/RAG extraction/retrieval smoke only if it adds evidence beyond the required managed-RAG replacement check.

These are not required for the first stock-core baseline unless the source delta touched them.

## Result classification

Use one of:

```text
PASS — exact RPM core smoke passed
FAIL — confirmed product/package defect
INCOMPLETE — required evidence could not be obtained safely
HARNESS/ENV — test environment or harness prevented a valid conclusion
```

Stop after the first real product/package blocker has enough evidence for diagnosis. Do not turn a smoke into an unbounded campaign.
