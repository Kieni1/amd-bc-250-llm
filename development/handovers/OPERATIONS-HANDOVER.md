# BC-250 operations boundary handover — 0.13.1-1.0

## Status

Maintenance/companion remains frozen for routine work.

RAG/Tika is no longer in this frozen set; it is active product scope.

This handover preserves operations interfaces that current greenfield/package work must not accidentally break.

## Current canonical command style

Operations documentation should use:

```text
bc250 maintenance ...
bc250 status
bc250 verify
bc250 support-bundle
bc250 storage
bc250 reset
```

Do not restore removed per-command `bc250-*` compatibility aliases.

## Protected Open WebUI credential

```text
/var/lib/bc250-llm-server/secrets/openwebui-admin.key

parent 0700 root:root
file   0600 root:root
content verified real Open WebUI sk-... API key
```

No token contents in logs/evidence/support bundles.

Temporary JWTs are bootstrap/convergence credentials, not the durable maintenance authority.

## Normal topology boundary

```text
main       11434 active
task       11435 active
embedding  11437 active
agent      11436 inactive unless optional Agent mode entered
```

Agent missing is optional coverage unavailable, not normal-topology damage.

## CU operations boundary

Current normal product workflow:

```bash
sudo bc250-cu-live-manager
sudo bc250-40cu status
```

The replacement-module/kernel-patch workflow was removed.

Operations/maintenance should not depend on:

```text
bc250-40cu prepare
enable
disable
restore
module patch state
```

Live routing and saved profile are the current authority.

## Safe-power boundary

The BC-250 owns the shutdown decision.

A companion/Pi may request safe shutdown but should not infer idleness and issue raw remote poweroff as the normal product contract.

Protected activity uncertainty must fail safe.

## Backup/restore boundary

Stable principles:

- package backups are local and private;
- backup creation is not enough; integrity/retention matter;
- restore validates data and preserves rollback material;
- Open WebUI state ownership must remain correct;
- secrets must not be exposed.

Do not rerun destructive restore campaigns unless a current change crosses this boundary.

## Storage/model lifecycle

Canonical model lifecycle is through:

```text
bc250 model ...
```

Prefer unregister/reapply with verified source reuse for support testing.

Do not manually delete Ollama blobs just because temporary storage looks large.

Destructive removal/purge needs explicit selection.

## Public/private helpers

Private memory/swap/Ollama/CU helpers moved to libexec.

Operations should call supported product commands, not treat those helpers as user API.

## Thaw conditions

Reopen maintenance/companion only when one of these changes:

- durable credential path/format;
- Open WebUI DB/backup path;
- maintenance-owned service names;
- backup/restore semantics;
- shutdown/power policy;
- user explicitly resumes maintenance work.

Do not thaw it merely because source documentation or command dispatch was cleaned up, unless an actual maintenance invocation changed.

## Current release smoke

Final exact RPM closure should confirm that existing maintenance status commands still work through the canonical dispatcher, but broad Pi/WOL/S5/restore/prune campaigns are not required unless the smoke exposes a regression.

## 0.12.2-0.8 exact-RPM note

Exact 0.12.2-0.7 fresh installation proved the smaller public API, live-CU-only package footprint, 53/53 core verification and 40/40 saved-profile reboot restoration. 0.8 keeps the topology unchanged and corrects operator semantics: completed revalidation remains completed with optional PARTIAL Agent coverage, successful translation withholding is a product-integrity PASS, CU state uses live-routing/profile/boot-restore terminology, and optional Agent is described as inactive in normal mode.

## 0.13.1-1.0 operations note

The release adds no new service topology or maintenance behavior. Normal dispatcher-launched Python helpers must not write bytecode under package-owned `/usr`; guided install/upgrade convergence removes stale BC-250 package-tree bytecode left by older releases. Optional models are not maintenance failures merely because they are absent/cached, and retired model residue is lifecycle cleanup rather than Open WebUI configuration drift.
