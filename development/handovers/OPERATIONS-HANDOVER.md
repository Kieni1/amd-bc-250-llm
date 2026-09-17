# BC-250 support / operations handover — current unpublished 0.11.1-0.11 source

You own real-device health, service topology, model lifecycle operations, storage,
maintenance/power, Open WebUI operational integration and bounded hardware regression.
Semantic model promotion belongs to the relevant quality lane/main integration.

## Authority and current source

Newest supplied source is authoritative over this handover. At the time of this refresh:

```text
VERSION:      0.11.1
RPM Release:  0.11
source base:  amd-bc-250-llm-current-0.11.1-0.11.zip
```

This handover does **not** assert that the unpublished 0.11.1-0.11 RPM has already
been built, installed or hardware-qualified. Capture installed NEVRA before interpreting
machine evidence. Task/translation campaign evidence from 2026-09-17 was gathered on
installed 0.11.1-0.10 and remains role evidence, not 0.11 package qualification.

## Validation ownership

GitHub owns RPM/package builds. Workstation owns Ruff. BC-250 owns runtime/hardware
qualification. Do not attempt unavailable tools locally and do not claim checks that did
not run.

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
translation         prod-lfm25-8b-a1b-liquidai-q6-k
higher-quality      prod-qwen35-9b-unsloth-q6-k
deep/warm main      prod-gpt-oss20b-ggml-org-mxfp4
embedding           embed-jina-v5-small-retrieval-q4-k-m
task default        task-lfm25-1.2b-instruct-liquidai-q6-k
task control        task-gemma3-1b-unsloth-ud-q4-k-xl
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

Latest retained real-device evidence is from installed `0.11.1-0.6` after a completed
`bc250-install`: Fedora kernel 7.2.4-200.fc44, healthy 40/40 live routing, normal
main/task/embedding service topology, office HTTP :80 ready, and `bc250-verify` at
48 ok / 0 warn / 0 fail when authenticated Open WebUI verification was skipped. Local
config/users backups were enabled, pruning remained DRY_RUN=1, warm-up and automatic
night shutdown were disabled, and Pi companion/export were skipped. The same run exposed
the stale installed path used by `bc250-maintenance contract`; current source contains
that fix plus retained-key validation, independent SSH preparation for backup export and
the fail-closed MTP comparison integrity follow-up. Separate task/translation campaign
evidence is current through installed 0.11.1-0.10, but the 0.6 operations/power evidence
remains historical until the current package is rechecked on-device.

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

After GitHub builds and the appliance installs `0.11.1-0.11`, run one bounded re-check of:

```text
installed RPM NEVRA
bc250-maintenance contract
bc250-maintenance status
bc250-maintenance companion status
bc250-verify
```

If that is clean, configure/confirm the intended WOL interface and power policy, then run
one real S5 Wake-on-LAN cycle. Only after S5 WOL succeeds should the safe-shutdown
busy/defer and later idle/allow cases be tested. Keep optional backup export and dedupe
performance separate.

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
