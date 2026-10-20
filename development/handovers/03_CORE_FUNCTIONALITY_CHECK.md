# Core functionality check — exact 0.14.1-1.4 RPM

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
- `rpm -q bc250-llm-server` reports `0.14.1-1.4` with the expected Fedora dist tag/arch;
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

## Runtime upgrade checks for 1.3

This RPM changes both Ollama and Open WebUI, so the normally-small smoke must include the changed boundaries.

For Ollama 0.40.6:

- all normal lanes (`11434`, `11435`, `11437`) report exactly `0.40.6`;
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
- one tiny document/RAG extraction/retrieval smoke if the environment is already prepared.

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
