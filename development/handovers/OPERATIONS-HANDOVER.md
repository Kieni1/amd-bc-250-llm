# BC-250 support / operations handover — current source-validated 0.11.3-1.4

You own real-device health, service topology, model lifecycle operations, storage,
maintenance/power, Open WebUI operational integration and bounded hardware regression.
Semantic model promotion belongs to the relevant quality lane/main integration.

## Authority and current source

Newest supplied source is authoritative over this handover. At the time of this refresh:

```text
VERSION:      0.11.3
RPM Release:  1.4
source base:  release-closed 0.11.3-0.4 + carried 0.5 installer/diagnostic work + bounded RAG integration/safety refinement
```

Current 0.11.3-1.4 is source-validated but not yet RPM/device-qualified. It carries the optional
maintenance/Pi UX, post-configuration verification, tight-resource/output-budget diagnostics,
deterministic RAG/Open WebUI qualification and safe MTP cleanup forward. RAG residency restoration
now guarantees the starting model set while allowing each Ollama service to apply its normal
keep-alive policy, and canonical RAG summaries use `swap_peak_delta_mib` rather than calling
peak-minus-start swap cumulative growth. Model/runtime defaults and whole-appliance hard acceptance
thresholds remain unchanged.

Newest complete device evidence is exact refined
`bc250-llm-server-0.11.3-0.4.fc44.x86_64`. Guided install completed with normal topology,
concise model reconciliation and verifier 54/0/0. v4.2 revalidation then completed with
infrastructure/restoration PASS, full coverage and quality 8/8. Task was 6/6, agent 3/3,
direct/OWUI translation and RAG paths passed. GPT-OSS/Jina remained within policy but
reached 193.36 MiB minimum MemAvailable and recorded non-severe 8662 -> 8320 context
truncation; one accepted office-draft case reached its output budget. Exact evidence is in
`development/model-runs/2026-09-19-installed-0.11.3-0.4-revalidation.md`.

## Validation ownership

GitHub owns RPM/package builds. Workstation owns Ruff/ShellCheck. BC-250 owns
runtime/hardware qualification. Current `0.11.3-1.4` completes the deterministic source gate with
401/401 tests PASS. Ruff/ShellCheck are workstation-owned and are not claimed here; GitHub RPM/SRPM
build and exact 0.11.3-1.4 BC-250 execution are also not yet claimed.

## Normal service topology

```text
ollama.service            main       11434
ollama-task.service       task       11435
ollama-agent.service      agent      11436; inactive in normal mode
ollama-embedding.service  embedding  11437
open-webui.service        active
nginx.service             office-facing HTTP :80
tika.service              private document extraction
```

Normal lane policy remains one loaded model / one parallel request per Ollama lane.
Main keepalive is 20m, task 0, embedding 10m and agent 5m. Agent mode is exclusive and
must restore the full normal topology on leave.

Internal 3000/11434-11437 ports are not Pi readiness endpoints. Office readiness is the
nginx/Open WebUI path on HTTP :80; SSH :22 is administration/restricted maintenance.

## Current runtime pins

Read `config/runtime.env` as authority. Current source pins:

```text
Ollama       0.34.0
Open WebUI   0.11.3
Tika         4.0.0-full
```

Ollama installer commit:
`d8ab4b4f0ca24b51d3a46b3bf4f462e58ce66b1f`.

## Current promoted roles

```text
standard office     prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl
RAG answer          prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl
translation         prod-translate-gemma4-sub-e4b-17s-q4-k-xl
translation roles:
  bc250-office-translation-de-fr -> prod-translate-gemma4-sub-e4b-17s-q4-k-xl
  bc250-office-translation-fr-de -> prod-translate-gemma4-sub-e4b-17s-q4-k-xl
higher-quality      prod-qwen35-9b-unsloth-q6-k
deep/warm main      prod-gpt-oss20b-ggml-org-mxfp4
embedding           embed-jina-v5-small-retrieval-q4-k-m
task default        task-lfm25-1.2b-instruct-liquidai-q6-k
task retired        task-gemma3-1b-unsloth-ud-q4-k-xl (graveyard)
agent default       agentic-ornith15-9b-ornith-q5-k-m
```

Do not revive graveyard models merely because an old handover names them.

## Hardware facts that affect operations

- 16 GB shared GDDR6 is one physical CPU/GPU pool; never add RAM/VRAM/GTT/Vulkan heaps.
- Stock exposure is roughly 24 CUs / 12 WGPs; physical GPU has up to 40 CUs / 20 WGPs.
- Live 40-CU routing is operator-controlled. Do not require a generic driver CU counter
  to show 40 when the package live routing table proves dispatch state.
- Package governor policy is 350–1850 MHz. Do not import >2 GHz community settings into
  production without dedicated stability/thermal evidence.
- Stock CPU operation exposes 6C/12T even though 8C/16T silicon exists; CPU unlock is
  separate and not required for the appliance.

Newest **full** general appliance evidence is exact installed
`bc250-llm-server-0.11.3-0.4.fc44.x86_64`: normal main/task/embedding/Open WebUI topology,
installer verification 54 ok / 0 warn / 0 fail, and v4.2 revalidation with
infrastructure/restoration/full coverage PASS and quality 8/8. Task passed 6/6, direct and
Open WebUI translation/RAG paths passed, production use cases passed and agent passed 3/3.
That evidence remains historical for exact 0.4 and does not qualify current 1.3 bytes.

Older installed `0.11.2-0.5.fc44` remains useful **maintenance-specific** evidence: local
config/users backups were enabled, pruning remained `DRY_RUN=1`, warm-up and automatic night
shutdown were disabled, and Pi companion/export were skipped. Its transcript also confirmed
the already-fixed `bc250-maintenance contract` documentation path. Current source retains the
later retained-key validation, independent SSH preparation for backup export and fail-closed
MTP comparison-integrity work. Power/WOL evidence remains older and still needs qualification.

## Storage lessons to preserve

During four large-model imports, Ollama 0.34.0 temporarily created source-hash blobs in
addition to retained package GGUFs and converted/live blobs. Four unreferenced import
blobs totaling roughly 46.3 GiB were removed by a normal `ollama.service` restart with
Ollama reporting exactly four unused blobs removed. Do not manually delete blobs merely
because onboarding temporarily looks ~3x amplified.

For byte-identical retained GGUF/live Ollama blobs, XFS dedupe is preferred over deleting
GGUFs. The current implementation keeps 16 MiB ranges but batches all ranges for a pair
into one `xfs_io` invocation. Do not regress to process-per-range behavior. Preserve
dedupe state across model reconciliation.

Known model-reconciliation gap: arbitrary out-of-band same-name Ollama registration
mutation may not be detected when source/template state is unchanged. Do not claim full
live-manifest drift proof until explicitly implemented.

## Maintenance / Pi contract

The Pi is an availability/power companion first; backup is optional.

Stable BC-250 interfaces include:

```bash
sudo bc250-maintenance contract
sudo bc250-maintenance companion status
sudo bc250-maintenance companion enable
sudo bc250-maintenance request-shutdown
sudo bc250-maintenance backup-export status
sudo bc250-maintenance backup-export enable
```

Safe shutdown delegates to BC-250 policy and may defer for active SSH/UI/Ollama or
maintenance. Never replace it with Pi-side raw `systemctl poweroff`.

WOL must be proven from real powered-off/S5 state before automatic after-hours poweroff
is relied upon.

## Immediate operations priority

The next hardware campaign should no longer start with storage dedupe. Product priority
is office availability and electricity saving.

Finish the current `0.11.3-1.4` source iteration first; do not spend hardware time on an
intermediate package. Once 1.3 is frozen, GitHub-build/install the exact RPM, capture NEVRA plus
RPM/source SHA, and run one bounded source-change check:

```text
sudo bc250-verify --owui-token-file FILE
optional maintenance/Pi top gate defaults to No and preserves existing state
local maintenance and Pi integration are independent choices
selected optional setup reports PASS/UNCHANGED/SKIPPED truthfully
post-install footer shows concise command groups plus installed docs/important paths
one full v4.2 revalidation
```

The full revalidation should preserve all existing infrastructure/restoration semantics and
hard thresholds while additionally surfacing tight MemAvailable and accepted output-budget
observations under `Diagnostics`. After that exact-source gate, run MTP and support operations
as separate bounded hardware batches: MTP starts with qwen3.5-9b-mtp; support starts with S5
WOL, then busy defer and idle allow+wake.

## Other operations work after power qualification

1. establish one current benchmark-operations control run before large quality campaigns;
2. eventually qualify batched XFS dedupe performance while preserving all retained GGUFs;
3. verify backup export only when off-device backup becomes operationally useful;
4. run whole-appliance `bc250-revalidate` at milestones rather than after every source-
   documentation/test-only patch.

## Handoff to main integration

Return:

```text
SUPPORT / OPERATIONS -> MAIN INTEGRATION
source release / SHA:
installed NEVRA:
scope:
commands actually run:
result / rc:
verifier before/after:
service topology before/after:
observed facts:
interpretation:
restoration/integrity:
proposed minimal change, if any:
next bounded test:
evidence files + SHA-256:
credentials/private data included: no/yes
```

Keep observed facts, interpretation and proposed changes separate.
