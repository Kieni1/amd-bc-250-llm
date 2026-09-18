# BC-250 support / operations handover — current source-ready 0.11.3-0.4

You own real-device health, service topology, model lifecycle operations, storage,
maintenance/power, Open WebUI operational integration and bounded hardware regression.
Semantic model promotion belongs to the relevant quality lane/main integration.

## Authority and current source

Newest supplied source is authoritative over this handover. At the time of this refresh:

```text
VERSION:      0.11.3
RPM Release:  0.4
source base:  0.11.3-0.3 UX/task-diagnostic line + 0.11.3-0.4 MTP hardening + final installer/model-pass refinements
```

The exact `0.11.3-0.4` source tree and a clean extraction of the release ZIP both passed
`make validate` with RPM/source preflight, packaged shell syntax and 378/378 deterministic
tests. Source/archive closure is complete. A pre-refinement same-NVR
`bc250-llm-server-0.11.3-0.4.fc44.x86_64` guided install has already completed on hardware
with normal topology and verifier 54/0/0; that run exposed the slow/noisy model-pass UX now
fixed in source. Because the final 0.4 source bytes changed without an RPM Release bump by
explicit maintainer direction, rebuild/reinstall is required before interpreting later hardware
evidence as qualification of this exact source. The newest full appliance revalidation remains
historical `bc250-llm-server-0.11.3-0.2.fc44.x86_64`: v4.2 completed with infrastructure/
restoration PASS and full coverage, task 5/6 on `tags-de`, and the bounded GPT-OSS/Jina
context diagnostic under `Diagnostics` without changing PASS. Exact 0.2 evidence is recorded
in `development/model-runs/2026-09-18-installed-0.11.3-0.2-revalidation.md`.

## Validation ownership

GitHub owns RPM/package builds. Workstation owns Ruff/ShellCheck. BC-250 owns
runtime/hardware qualification. Current `0.11.3-0.4` must pass the local source gate before release: repository/RPM
preflight, packaged shell syntax and the deterministic test suite. Ruff/ShellCheck were not run
here; GitHub RPM build and BC-250 execution are not yet claimed.

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

Latest **full** general appliance evidence is from installed `0.11.2-0.5.fc44`: Fedora kernel
7.2.5-200.fc44, healthy 40/40 live routing, normal main/task/embedding service topology,
authenticated Open WebUI desired-state drift none, and install verification at 54 ok /
0 warn / 0 fail. Local
config/users backups were enabled, pruning remained DRY_RUN=1, warm-up and automatic
night shutdown were disabled, and Pi companion/export were skipped. The `bc250-maintenance contract` installed-documentation path defect had already been
fixed in the 0.11.1-0.7 line; the 0.11.2-0.5 transcript successfully printed that
contract, so it is not a current 0.5 finding. Current source also retains the later
retained-key validation, independent SSH preparation for backup export and fail-closed
MTP comparison-integrity work. Installed 0.11.2-0.5 completed whole-appliance
revalidation v4.1 with full coverage,
infrastructure/restoration PASS, canonical Open WebUI translation PASS, agent 3/3 and one
task quality miss at 5/6 because `tags-de` emitted two JSON objects. The 0.11.2-0.6 source
changes the diagnosis of that task miss but not its acceptance. Power/WOL evidence remains
older and still needs qualification.

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

GitHub rebuilds and the appliance reinstalls the final refined `0.11.3-0.4`; capture the
exact NEVRA plus RPM/source artifact SHA and run one bounded source-change check:

```text
sudo bc250-verify --owui-token-file FILE
model phase has no redundant initial catalog
required-current models are summarized
optional picker appears promptly, uses compact current/deferred rows and excludes MTP
sudo bc250-model status production MODEL --verbose
one full v4.2 revalidation
```

The model-status check should show packaged/current verified state and explicit `--online`
guidance. v4.2 already exercises the strict six-case task contract, including the repeated
`tags-de` case, so do not duplicate it unless a failure needs isolation and do not weaken the
evaluator. The full revalidation should preserve the same infrastructure/restoration semantics
and concise bounded GPT-OSS/Jina diagnostic. After that exact-source gate, run MTP and support
operations as separate bounded hardware batches: MTP starts with qwen3.5-9b-mtp; support starts
with S5 WOL, then busy defer and idle allow+wake.

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
