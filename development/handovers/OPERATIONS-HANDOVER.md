# BC-250 support / operations handover — current source release 0.12.1-0.2

This handover is for the real-device support/operations lane: service topology, model lifecycle
operations, storage, maintenance/backups, power/WOL, Open WebUI operational integration and bounded
hardware regression. Semantic model promotion remains a main/quality decision.

## Authority and evidence boundary

Use newest source/package first, then exact installed device evidence. Current source:

```text
VERSION:      0.12.1
RPM Release:  0.2
NVR:          bc250-llm-server-0.12.1-0.2
```

0.12.1-0.2 is the current source release target. It carries the narrow Open WebUI ACL, Deep
Reasoning residency and verifier fixes plus release-provenance/patch-applicability hardening. It does
not change the already-qualified non-OWUI topology, maintenance, CU, power, storage, backup/restore or
supported-reboot behavior. Exact installed `0.11.3-2.4.fc44.x86_64` remains the latest broad
operations acceptance baseline; do not transfer that hardware qualification to 0.12.1-0.2.

The required post-build device work for 0.12.1-0.2 is the small Open WebUI/revalidation regression pass documented in `development/patchnotes/PATCHNOTE-0.12.1-0.2.md`, unless later source changes touch additional operations boundaries.

Newest full device qualification is exact installed `0.11.3-1.7.fc44.x86_64`:

```text
core verify          54 / 0 / 0
infrastructure       PASS
quality              8/8 PASS
restoration          PASS
coverage             FULL
```

Exact installed `0.11.3-2.3.fc44.x86_64` has passed the targeted 2.3 operations acceptance:

```text
rpm -V / swap 0750                 PASS
status/verifier/degraded recovery   PASS
agent-mode normal                   PASS / idempotent
maintenance DRY_RUN/timer UX        PASS
Tika routine restart                PASS / Result=success
identity restore                    PASS; baseline FK=142, new FK=0
supported sudo reboot               PASS; appliance reconstructed
live 40-CU routing                  40/40 healthy
failed units                        0
final authenticated verifier        54 / 0 / 0
```

The 2.4 package corrected the package-owned live-manager interactive CPU-core-unlock reboot path to
`/usr/sbin/reboot`, and exact-installed 2.4 subsequently passed complete reconstruction through the
supported `sudo reboot` path. The separate `systemctl reboot` anomaly remains intentionally deferred;
do not rerun the known-bad invocation merely to prove it.

Exact installed `0.11.3-2.2.fc44.x86_64` has now closed the two highest-priority inherited
operations boundaries and accumulated further bounded support evidence:

```text
bc250-install convergence          PASS
live 40-CU routing                 40/40 healthy
persistent activation              intentionally disabled
active admin SSH request-shutdown  DEFER PASS; no session loss
normal -> agent -> normal           PASS
deliberate degraded topology       detected and recovered
config/users backup creation        PASS; checksums/privacy/retention verified
config restore + rollback point     PASS; HTTP/topology/54-0-0 recovered
identity rollback on validation     PASS
production use cases                4/4 PASS
task suite                          6/6 PASS
bounded generation-edge infra      17/17 PASS
individual/grouped service restart  PASS; final failed units 0
external LAN isolation              PASS; only SSH :22 and office HTTP :80 exposed as intended
reboot persistence via sudo reboot  PASS; normal services/timers/firewall/40-CU restored
systemctl reboot compatibility path DEVICE DEFECT; do not use for package-controlled reboot
final authenticated bc250-verify   54 ok / 0 warn / 0 fail
```

The exact-2.2 identity restore attempt exposed one real validation defect: the live Open WebUI DB
already had 142 unrelated `foreign_key_check` rows while still passing `integrity_check`; the old
validator rejected those unchanged baseline rows and rolled back. Exact installed 2.3 proves the
corrected canonical pre/post FK-set comparison in real use: baseline=142, new=0, strict integrity OK,
restore RC=0 and final appliance health clean. Real idle S5/WOL, Pi forced-command shutdown and live
prune remain conditional acceptance work.

Evidence files:

```text
development/model-runs/2026-09-20-installed-0.11.3-1.7-revalidation.md
development/model-runs/2026-09-20-installed-0.11.3-1.7-support-maintenance.md
development/model-runs/2026-09-20-installed-0.11.3-2.2-operations-batches-04-06.md
development/model-runs/2026-09-20-installed-0.11.3-2.2-operations-batches-07-09.md
development/model-runs/2026-09-20-installed-0.11.3-2.3-operations-acceptance.md
development/model-runs/2026-09-20-installed-0.11.3-2.3-openwebui-investigation.md
development/model-runs/2026-09-21-installed-0.11.3-2.4-operations-batches-19-20.md
development/model-runs/2026-09-21-installed-0.11.3-2.4-openwebui-final.md
```

The 2.2 Batch 04–09 records, exact-2.3 targeted acceptance and exact-2.3 Open WebUI investigation are
operator-supplied summarized device evidence; their raw archives were not independently inspected in
the main integration environment. Do not overstate their provenance.

## Validation ownership

```text
GitHub       RPM/SRPM/package builds
workstation  Ruff/developer linting
BC-250       hardware, services, models, Open WebUI, backup/restore, power/WOL
```

Current 0.12.1-0.2 implementation is recorded in `development/patchnotes/PATCHNOTE-0.12.1-0.2.md`. The 0.2 follow-up changes only the revalidation package-version authority plus release-coherence documentation relative to 0.1; focused source tests for that boundary pass. GitHub remains authoritative for the complete deterministic/build gate.

Exact installed 2.4 remains the broad device regression baseline. Exact installed 0.12.1-0.1 reached package convergence and authenticated verification but exposed the stale revalidation version gate; exact 0.12.1-0.2 remains unqualified until built, installed and subjected to the bounded OWUI/revalidation regression.

## Service topology

```text
ollama.service            main       11434
ollama-task.service       task       11435
ollama-agent.service      agent      11436; exclusive and inactive in normal mode
ollama-embedding.service  embedding  11437
open-webui.service        application
nginx.service             office-facing HTTP :80 / readiness path
tika.service              private document extraction
```

Normal mode: main/task/embedding active, agent inactive. Agent mode: 11436 active, normal Ollama
lanes inactive. `bc250-agent-mode status` is the topology authority and must distinguish
`normal / agent / degraded / stopped`.

Internal 3000/11434-11437 are not Pi readiness endpoints. Use nginx/Open WebUI HTTP :80 for office
readiness and SSH :22 only for administration/restricted maintenance.

Current runtime pins come from `config/runtime.env`:

```text
Ollama       0.34.0
Open WebUI   0.11.3
Tika         4.0.0-full
```

## Current production roles relevant to operations

```text
standard office     prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl
RAG answer          prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl
translation         prod-translate-gemma4-sub-e4b-17s-q4-k-xl
higher-quality      prod-qwen35-9b-unsloth-q6-k
deep/memory edge    prod-gpt-oss20b-ggml-org-mxfp4
embedding           embed-jina-v5-small-retrieval-q4-k-m
task                task-lfm25-1.2b-instruct-liquidai-q6-k
agent baseline      agentic-ornith15-9b-ornith-q5-k-m
```

MTP is not another Ollama lane. Installer Stage 7 shows MTP state read-only but never fetches it.
Direct `bc250-run-mtp` drains Ollama residency and restores the captured set; comparison uses
specialist drain-only isolation and leaves Ollama cold.

## Hardware/resource facts for operations

- 16 GB GDDR6 is one shared CPU/GPU pool; do not add RAM/VRAM/GTT/Vulkan views.
- Live routing can be healthy at 40/40 even when kernel/RADV numeric counters show 24.
- Live 40-CU routing is operator-controlled; persistent 40-CU boot activation may intentionally be
  disabled and must not make healthy live status fail.
- Governor policy remains approximately 350–1850 MHz with 85 C throttle target.
- Hard MemAvailable floor is 128 MiB; <512 MiB is tight-headroom diagnostic territory.
- GPT-OSS + Jina is the credible memory edge; exact-1.7 passed with 167 MiB minimum MemAvailable.

## Model lifecycle safety

Use the current grammar:

```text
bc250-model list [CATEGORY]
sudo bc250-model status [CATEGORY] [SELECTION] [--online]
bc250-model path CATEGORY ID
sudo bc250-model apply CATEGORY [SELECTION]
sudo bc250-model refresh CATEGORY [SELECTION]
sudo bc250-model unregister CATEGORY [SELECTION]
sudo bc250-model remove CATEGORY [SELECTION]
sudo bc250-model purge-retired
```

Category `all` does not itself select every model. Explicit all-model convergence is
`sudo bc250-model apply all all`.

For support testing, prefer `unregister -> apply` so the manager reuses the verified GGUF. Avoid
`refresh`, `remove` and source pruning unless source destruction/redownload is the actual test goal.
Manager-owned GGUF paths are protected; shell existence/stat probes from `llm_admin` must use sudo.

`/etc/bc250-llm-server/models.d/` is an operator override directory. Packaged definitions are not
expected to appear there. Visible operator definitions must have a `.Modelfile` suffix and matching
model metadata/name.

## Storage lessons to preserve

Ollama imports can temporarily amplify storage by keeping source GGUFs plus import/live blobs. Normal
Ollama lifecycle may remove unreferenced blobs; do not manually delete them merely because onboarding
looks temporarily large.

For byte-identical retained GGUF/live Ollama blobs on XFS, prefer package dedupe over deleting GGUFs.
Preserve verified source/state so registration can be rebuilt locally.

Known gap: arbitrary out-of-band same-name Ollama registration mutation is not fully detected when
source/template state is unchanged.

## Local maintenance and backup contract

Stable interfaces:

```text
sudo bc250-maintenance status
sudo bc250-maintenance setup
sudo bc250-maintenance run backup
sudo bc250-maintenance run prune
sudo bc250-maintenance request-shutdown
sudo bc250-maintenance companion status
sudo bc250-maintenance companion enable
sudo bc250-maintenance backup-export status
sudo bc250-maintenance backup-export enable
```

Current design:

- config/users backups are local and independent of Pi;
- backups are private and verified, not merely created;
- restore requires Open WebUI stopped, validates archive/database state and preserves rollback
  material;
- pruning starts `DRY_RUN=1` and fails safe on uncertain metadata;
- warm-up/night power are optional; status must distinguish disabled schedules from retained
  configured values;
- backup export is a separate read-only identity and optional;
- active maintenance jobs defer power actions.

## Safe-power / Pi contract

The BC-250 owns the shutdown decision. The Pi may request it but must not execute raw remote
`systemctl poweroff` as the normal interface.

Public operator path:

```text
sudo bc250-maintenance request-shutdown
```

This must defer if the current interactive SSH connection, UI/Ollama protected TCP activity or a
maintenance job is active.

Dedicated companion path:

```text
forced-command SSH identity
  -> sudo bc250-maintenance request-shutdown-companion
  -> safe-power helper with exact SSH_CONNECTION exemption
```

Only that authenticated control tuple may be ignored. Any additional SSH/protected connection must
still block poweroff. Missing/failed TCP inspection must defer.

WOL must be proven from real powered-off/S5 state before automatic after-hours poweroff is enabled.

## Immediate 0.12.1-0.2 source/device follow-up

Do not replay the closed 2.4 broad operations campaign. The new package changes only Open WebUI
model authorization/residency/status behavior plus build provenance validation.

For current 0.12.1-0.2:

```text
1. build binary/source RPMs through the authoritative Fedora 44 path with exact pinned source caches;
2. install the exact new NEVRA and run normal package convergence;
3. verify all six production office roles are visible/usable to an ordinary user while the five
   production bases plus task model remain selector-hidden;
4. verify the ACL policy is minimum-required/additive: required user:*:read grants exist, unrelated
   grants are not destructively stripped, and the inactive legacy translation record is not promoted;
5. run one ordinary-user Standard request and one Documents request;
6. run Deep Reasoning immediately followed by title/tag generation, confirm GPT-OSS has unloaded before
   task cold-load and observe no new OOM/kernel allocation/GPU failure signature;
7. run verbose authenticated Open WebUI status and final bc250-verify, targeting 54/0/0/0;
8. finish with healthy normal topology and Open WebUI readiness.
```

The exact-2.4 operations evidence already covers supported reboot reconstruction, live 40/40,
maintenance, storage hygiene, backup/restore, runtime soak, model switching and service topology.
Repeat those areas only if a corresponding implementation changes.

## UX acceptance during support tests

Do not judge only return codes. Record whether an operator can correctly understand the state:

- protected data should say protected/unavailable, not `0` or absent;
- normal inactive agent should read as intentional, not a scary conflict/failure;
- disabled warm-up/night power should be visibly disabled even if configuration values remain;
- small prune candidates should show meaningful B/KiB/MiB sizes;
- intentional degraded tests should produce a clear degraded summary and recover to normal;
- safe-power defer should return without broadcast/session loss;
- successful power allow should log the guard decision before the connection disappears.

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
operator UX observations:
observed facts:
interpretation:
restoration/integrity:
proposed minimal change, if any:
next bounded test:
evidence files + SHA-256:
credentials/private data included: no/yes
```

Keep observed facts, UX observations, interpretation and proposed changes separate.
