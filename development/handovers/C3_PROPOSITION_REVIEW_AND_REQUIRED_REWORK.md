# BC-250 clean-core C3 proposition review — required rework before acceptance

## 1. Reviewed artifacts

Frozen reconstruction baseline remains:

```text
amd-bc-250-llm(10).zip
SHA-256: 79b1a9e60e15764b49d67982d9dd689a338766dc50f21dac2cdb4c1139cd32d6
bc250-llm-server-0.13.1-1.9
```

Reviewed C3 proposition:

```text
amd-bc-250-llm-clean-core-C3(1).zip
SHA-256: 08b7c19104a1c29a6fd6c54e7df1fc4688d741420180b78a054e33d11f240d1b

BC250_clean-core_C3(1).patch
SHA-256: e1b13f315d386ecb1a15be625708b15b23c8bcc74abef57c3e9d66b32f83ce0a
```

The ZIP matches the patch-applied 1.9 source used for review.

## 2. Review verdict

```text
C1 ownership inventory:       substantially complete
C2 structural GFX removal:    substantially complete / KEEP
C3 regression baseline:       REWORK — NOT ACCEPTED YET
Donor forward-port (C4/C5):   DO NOT START YET
```

Do not restart the removal. The structural approach is sound and should be preserved.

Do not accept the candidate's own `WORKBENCH-STATE.json` statement that C3 is complete until the blockers below are corrected and rerun.

## 3. What is already good and should be kept

Independent review confirmed that the proposal cleanly removes the main GFX-owned surfaces while preserving the intended stock core:

- `gfx1013/` payload removed;
- `cmd/system/gfx1013.sh` removed;
- GFX A/B benchmark helper/campaign removed;
- public CLI dispatch/completion removed;
- GFX install manifest and RPM ownership removed;
- GFX transaction scriptlets removed;
- GFX qualification inventory/state fields removed;
- private-RADV/package-owned experimental surfaces removed;
- dedicated GFX docs/tests removed;
- stock AMDGPU/Mesa/Vulkan diagnostics retained;
- live CU routing retained;
- normal appliance/runtime/model/RAG code remains present.

The patch applies cleanly to the frozen 1.9 baseline.

Source-side checks reproduced during review:

```text
scripts/validate.sh --preflight: PASS
development/scope.py check: PASS
shell/Python syntax: PASS
19 deterministic unittest modules: PASS
573 tests total: PASS
```

Those passes are useful evidence, but they do not override the runtime defect below.

## 4. Blocking defect 1 — `bc250 version` is broken

`cmd/monitoring/version.py` still puts `runtime_identity` into its output payload and reads it for human output, but the initialization of that variable was removed with the GFX cleanup.

Observed result:

```text
NameError: name 'runtime_identity' is not defined
rc=1
```

This affects normal, `--json`, and `--short` invocation because the payload is built before the short-output branch.

Required repair:

```python
runtime_identity = status.get("runtime_identity") if isinstance(status, dict) else None
if not isinstance(runtime_identity, dict):
    runtime_identity = {}
```

or an equivalent generic implementation that does not reintroduce GFX state.

Required proof:

- execute the command, not just source-string tests;
- test normal output;
- test `--json`;
- test `--short`;
- prove expected rc behavior with and without installed RPM identity as appropriate to the existing contract.

This finding demonstrates that a passing source suite is not sufficient when a public command path is not executed by tests.

## 5. Blocking defect 2 — `kmod` dependency was removed while `lsmod` is still required

The proposal removes the RPM `Requires: kmod`, but generic core verification still executes:

```text
cmd/monitoring/verify-server.sh
  lsmod ...
```

This is stock/core functionality, not GFX-specific functionality.

Required action:

- restore `Requires: kmod`, unless the generic verifier is deliberately redesigned to operate correctly without it;
- do not remove dependencies solely because they were also useful to GFX.

Removing `grub2-tools-minimal` may remain valid if no remaining core path requires it; keep that decision evidence-based.

## 6. Required secondary-file reconciliation

### `development/TESTING-STRATEGY.md`

The current proposal adds clean-core language but still contains active-looking instructions from older GFX device campaigns, including references to:

- GFX disabled/prepared/enabled rollback;
- `prepare --check`;
- one-shot patched boot;
- exact BC-250 RADV identity;
- GFX stale/new-stock-kernel guards;
- disable/reset.

These must no longer be presented as current clean-core testing work.

Historical sections may remain if clearly labeled historical/archive-only.

### In-repository handovers

`development/handovers/README.md` still presents the old 0.13.1-1.3 handovers as current, and current-looking handover files still identify 1.3 as the release target.

Required action:

- replace current pointers with the clean-core reconstruction state;
- preserve old 1.3 handovers as historical/archive evidence rather than rewriting their original claims.

### Current product documentation

Current docs should primarily describe what the stock core is, rather than repeatedly explaining the removed experiment.

Historical explanation belongs in CHANGELOG/decision/archive material.

Examples to review include wording around:

- replacement/patched kernel modules;
- package-built replacement module;
- removed experimental compute-queue lifecycle.

Do not remove legitimate stock AMDGPU/Vulkan/live-CU documentation.

## 7. Clean-core absence gate correction

The first handover absence checker was too broad.

It incorrectly treated legitimate history/removal evidence as active ownership, especially:

- RPM spec `%changelog` entries;
- `WORKBENCH-STATE.json` `changed_files` entries naming files that were deleted.

The clean-core absence gate must distinguish:

```text
ACTIVE runtime/package/current-doc reference     -> forbidden
CURRENT operator/testing instruction             -> forbidden
HISTORICAL changelog/archive record              -> allowed
REMOVAL/transition evidence                      -> allowed
```

Do not delete historical evidence merely to make grep green.

The updated `check-clean-core-absence.sh` implements this narrower structural rule and now correctly passes the reviewed proposal. A separate `check-current-guidance.sh` checks stale current testing/handover instructions and correctly fails the reviewed proposal until those files are reconciled. Both concepts should be ported into the source repository when C3 is corrected.

## 8. Workbench predecessor identity cleanup

The proposal records:

```text
predecessor_artifact: amd-bc-250-llm(20261019-080542).zip
predecessor_sha256:   79b1a9e60e15764b49d67982d9dd689a338766dc50f21dac2cdb4c1139cd32d6
```

The frozen operator authority is named:

```text
amd-bc-250-llm(10).zip
```

The SHA matches, so this appears to be a byte-identical alias rather than a source mismatch.

Required action:

- either use the agreed frozen filename;
- or explicitly state that the timestamped predecessor is a byte-identical alias of the frozen authority.

Do not leave ambiguous artifact naming in the current workbench record.

## 9. First clean-core upgrade boundary

The future clean-core package should remain ignorant of GFX rollback logic.

Therefore the first device-upgrade acceptance has a hard precondition:

```text
old GFX-capable predecessor
-> GFX fully returned to verified stock / disabled
-> no active private RADV or patched boot state
-> install clean-core RPM
```

Do not test or promise an upgrade directly from an active/prepared GFX state unless the product direction is explicitly reopened.

This is an operational migration precondition, not a reason to reintroduce GFX compatibility code into the clean core.

## 10. Required C3-R1 correction pass

Make one narrow correction pass on the current proposal:

1. fix `bc250 version` and add real execution coverage;
2. restore `Requires: kmod` or provide deliberate generic replacement behavior;
3. reconcile current testing strategy/current handovers/current docs;
4. use the refined clean-core absence gate and place an equivalent deterministic gate in the source repo;
5. align/clarify predecessor artifact naming;
6. rerun all 573 existing tests plus the new execution/absence tests;
7. run source preflight, scope, syntax/static checks and secondary-file audit again.

Expected result:

```text
C3-R1 source candidate
C1: PASS
C2: PASS
C3: PASS
C4/C5: still not started
```

Only after that may donor forward-porting begin.

## 11. Main-chat instruction

The next main chat must not redo the GFX removal from scratch and must not begin 2.2 donor work yet.

Its immediate job is:

> repair the reviewed C3 proposition narrowly, prove the public core commands and package dependencies, reconcile the secondary files, turn the refined absence gate green, and freeze a corrected C3 checkpoint.

Preserve the reviewed proposition and its first failure evidence until the corrected checkpoint exists.
