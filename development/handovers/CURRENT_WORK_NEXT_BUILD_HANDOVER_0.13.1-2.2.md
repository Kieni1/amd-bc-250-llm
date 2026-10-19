# BC-250 0.13.1-2.2 — current stock-reboot-transition corrective handover

## Authority and boundary

1.18 established the clean Fedora 44 build authority and shared exact-kernel GFX module-attestation contract with `srcversion=none` supplemental.

2.0 advanced exact-device GFX qualification through successful `prepare`, repaired dracut `stage-boot`, patched reboot recognition, loaded patched-amdgpu attestation, private RADV activation, BC-250 compute-queue detection and `ENABLED` state.

2.1 then improved the normal operator path substantially. Device evidence confirmed the RPM one-next-action transaction behavior, the fuller installer completion hierarchy, workflow-oriented GFX help, safe stock restoration after reboot and same-package reinstall. Its upgrade from a previously enabled GFX state also proved that the package rollback machinery itself is safe:

```text
old runtime: patched GFX1013
saved/default after upgrade: verified stock
next boot after upgrade: verified stock
private RADV override: disabled
old prepared/package GFX state: removed
```

The currently loaded patched kernel necessarily remained running until reboot. 2.1 misclassified that known transition as generic `ROLLBACK_REQUIRED`, caused `reset` to say "nothing to do; already disabled", allowed `prepare --check` to PASS even though `prepare` correctly rejected the patched current boot, and let `bc250 install` hide the required stock reboot.

After reboot, the exact same 2.1 device converged automatically to clean `DISABLED`, health PASS and core verify PASS. Therefore **do not redesign rollback or the GFX architecture**. 2.2 corrects the intermediate-state semantics and command agreement only.

2.2 remains a source candidate until the exact clean Fedora 44 `./build-local.sh --full` succeeds. Only the exact main RPM from that gate is authoritative for device qualification.

## 2.2 release identity

```text
Version:      0.13.1
RPM Release:  2.2
Ollama:       0.40.4
GFX profile:  v0.2.5-alpha
Fedora:       44
Qualification kernel for this build campaign: 7.2.10-200.fc44.x86_64
```

The qualification kernel is build evidence, not a permanent hardcoded compatibility ceiling.

## Primary lifecycle correction

Introduce explicit observable semantics for:

```text
current runtime      = previously enabled patched GFX1013 boot
saved/default boot   = independently verified stock BLS
next boot            = same verified stock BLS
private RADV override= disabled/absent
package GFX artifacts= cleaned
```

This is **not** an unknown/orphaned recovery state. It is a safe rollback already prepared, with one remaining action:

```text
sudo reboot
```

The implementation uses the state name:

```text
STOCK_REBOOT_REQUIRED
```

Default operator wording should remain human-oriented (`stock reboot required`), while JSON/verbose interfaces retain the exact enum.

## Shared stock authority

The same safe-stock resolver must drive:

- lifecycle classification;
- machine-readable `status --json`;
- `status --verbose` stock-entry reporting;
- `reset --check`;
- `reset` and `disable` no-state handling;
- `prepare --check` runtime readiness;
- actual `prepare` runtime readiness;
- installer completion through the GFX status interface.

Do not teach each command independent boot heuristics.

When the exact stock BLS is proven, `status --json` must populate:

```json
"boot": {
  "stock_entry": "<verified-stock-entry>",
  "saved_entry": "<same-stock-entry>",
  "next_entry": "<same-stock-entry>"
}
```

It must not report `stock_entry: null` while another package command has already proved that same entry.

## Reset / disable contract

For `STOCK_REBOOT_REQUIRED`, `reset --check` is read-only and should prove stock authority, then make the immediate action explicit:

```text
GFX1013 rollback check: PASS
...
Next action: sudo reboot
```

`reset` or an ordinary `disable` invocation in the same state must not say merely "already disabled". Expected semantics:

```text
Reset: PASS (stock rollback prepared; reboot pending)
Current runtime: patched GFX1013
Verified next boot: stock (<entry>)
Boot configuration: already restored
Runtime override: disabled
Boot state changed: no
Runtime/service state changed: no
A reboot is required to complete the return to stock.
Next action: sudo reboot
```

Package-upgrade/package-erase internal disable paths may remain quieter and must not emit a subordinate workflow action.

## Prepare contract

`prepare --check` and actual `prepare` must use the same runtime-readiness guard.

While a patched runtime is still loaded and verified stock is already selected for the next boot:

```text
prepare --check -> BLOCKED
prepare         -> BLOCKED
Next action     -> sudo reboot
```

The preflight remains read-only and must state that no files, boot state or services changed.

After rebooting into stock:

```text
prepare --check -> PASS
```

Do not weaken any dependency, source-integrity, exact-kernel, stock-BLS or payload-integrity checks.

## Installer completion contract

The fuller technical orientation screen remains intentional.

Normal completion hierarchy remains:

```text
OVERVIEW
  Administration
  Storage & cleanup

NEXT STEPS
  System status / validation
  Setup / repair
  Models
  Optional improvements
```

When the shared GFX status says `STOCK_REBOOT_REQUIRED`, `bc250 install` may still report core installation/verification PASS, but it must also expose:

```text
Experimental GFX1013: stock reboot pending
Current GFX runtime: previous patched boot
Verified next GFX boot: stock
GFX1013 reboot required: YES
```

The primary next action must show:

```text
Required reboot
  Complete GFX1013 stock restoration: sudo reboot
```

before the optional GFX preflight guidance. The latter should be phrased as an **after reboot** action.

Do not turn this experimental transition into a core-appliance failure.

## Health / status / verify

Keep the existing separation:

```text
status  -> informational current state; successful report may remain rc=0
health  -> automation health gate; stock reboot pending is ACTION REQUIRED / overall DEGRADED
verify  -> core systematic verifier; experimental transition does not become a core FAIL
```

`status` must treat `STOCK_REBOOT_REQUIRED` as an experimental action-required state so the top-level view does not claim unqualified HEALTHY while a reboot is pending.

Health should retain:

```text
Overall appliance health: DEGRADED
Core appliance health: PASS
Experimental GFX1013: ACTION REQUIRED
```

with a truthful stock-reboot-required reason rather than orphan/recovery language.

## Behavior implemented / covered by prior corrective work — retain

Keep the evidence level explicit rather than calling every item device-proven.

**Device-proven in the 2.1 round:**

- exactly one RPM transaction workflow handoff: `sudo bc250 install`;
- no subordinate `Next action: sudo bc250 gfx1013 ...` from the observed upgrade/reinstall path;
- installer `System status / validation`, `Setup / repair`, `Models`, `Optional improvements` grouping;
- generic installer advertises only safe `gfx1013 prepare --check`;
- workflow-oriented GFX help (`Typical activation`, `Return to stock`, inspection, recovery, qualification);
- safe stock restoration after the upgrade-from-enabled transition and subsequent reboot;
- clean same-package reinstall from stock.

**Source-test-proven / implemented, but still requiring exact-device exercise where noted:**

- `%pre` compatibility filtering covers older installed helper next-action variants and remains free of `mktemp`/`/tmp` usage; Fedora `rpmlint` in the authoritative full gate remains the final packaging proof;
- direct `sudo bc250 model install` combined-catalog workflow;
- empty/cancel model selection makes no state mutation — source-test-proven, still requires the explicit device invocation below;
- benign verified-stock `next_entry` replacement by `stage-boot` — source-test-proven, not yet independently device-confirmed unless that branch actually appears on the device;
- unknown/non-stock one-shot fail-closed behavior — deterministic source-test-proven; do not manufacture an unsafe device state merely to reproduce it;
- post-selection staging failure restores the original verified-stock one-shot — deterministic source-test-proven;
- successful `enable` ends with no mandatory status hop for ordinary users;
- `disable` requires reboot when a patched runtime is loaded;
- TTY emphasis remains supplemental and `NO_COLOR`/non-TTY output remains plain.

## GFX safety invariants — do not reopen

Do not change without direct regression evidence:

- exact-running-kernel targeting;
- exact vermagic and ABI validation;
- module SHA/provenance attestation;
- supplemental `srcversion` policy;
- Fedora kernel SRPM prepared-source authority;
- zero-fuzz package patching;
- private Ollama-only RADV architecture;
- corrected dracut `kmod/lib/modules/<kernel>/` hierarchy;
- one-shot patched boot architecture;
- verified-stock saved/default protection before enable;
- unknown/non-stock `next_entry` fail-closed behavior;
- benign verified-stock `next_entry` replacement by `stage-boot`;
- post-selection rollback restoring the original stock one-shot;
- patched module boot-chain attestation;
- persistent promotion only after `enable`;
- normal Ollama runtime topology.

## Required deterministic coverage

At minimum prove:

1. no-state patched runtime + saved/next verified stock -> `STOCK_REBOOT_REQUIRED`;
2. the same situation still becomes `ROLLBACK_REQUIRED` if stock authority cannot be proven;
3. JSON contains the resolved verified `stock_entry`;
4. `reset --check` points to `sudo reboot` without mutation;
5. `reset` reports rollback already prepared and points to `sudo reboot`;
6. `prepare --check` and `prepare` call the same runtime-readiness guard;
7. the shared guard returns `sudo reboot` for the stock-reboot-pending transition;
8. after simulated stock reboot the state returns to `DISABLED` and prepare preflight can pass;
9. installer consumes GFX `status --json` rather than duplicating boot classification;
10. installer places required reboot before the post-reboot GFX preflight guidance;
11. `status` top-level action-required logic includes `STOCK_REBOOT_REQUIRED`;
12. all 2.1 stage-boot verified-stock/unknown-entry/rollback regressions remain green;
13. `%pre` remains rpmlint-safe and Ruff-clean.

## Main-chat validation policy

Routine 2.2 gate:

- all `tests.test_gfx1013`;
- installer/operations/packaging boundary tests;
- release-pipeline/preflight tests;
- development scope validation;
- shell syntax/static checks;
- important frozen-core sentinels when crossed;
- final checks against extracted frozen Source0.

The authoritative Fedora workstation must still run:

```bash
./build-local.sh --full
```

Preserve exact clean source commit, running/build kernel, Source0/spec hashes, main RPM NEVRA/hash, SRPM hash, rpmlint result, SRPM rebuild result, `result.json`, and the final stdout main-RPM path.

## Exact-device 2.2 sequence

### Mandatory predecessor

The **primary 2.2 device acceptance test must start from a proven 2.1 `ENABLED` state**. The current device being clean `DISABLED` is not sufficient to exercise the repaired transition.

If the device is currently `DISABLED`, first re-establish the normal 2.1 lifecycle with the exact installed 2.1 bytes:

```text
prepare --check
-> prepare
-> stage-boot
-> reboot
-> status
-> enable
-> status
```

Do not install 2.2 until 2.1 reports `ENABLED`. Otherwise the central 2.2 branch — old patched runtime plus package-restored stock saved/next boot — has not been tested.

Before the 2.2 upgrade capture:

```bash
rpm -q bc250-llm-server
sudo bc250 gfx1013 status --verbose
sudo grub2-editenv - list
```

### Install exact authoritative 2.2 RPM

Install only the exact RPM from the clean successful Fedora `./build-local.sh --full` gate and capture the complete DNF transaction.

Require:

```text
%pre safety reporting: allowed
subordinate GFX Next action: absent
sole final package handoff: sudo bc250 install
```

Immediately capture boot authority after the transaction:

```bash
sudo grub2-editenv - list
```

### Prove the stock-reboot-pending transition before reboot

Run:

```bash
sudo bc250 install

sudo bc250 status
echo "status rc=$?"

sudo bc250 health
echo "health rc=$?"

sudo bc250 verify
echo "verify rc=$?"

sudo bc250 gfx1013 status --verbose
sudo bc250 gfx1013 status --json
```

Required contract:

```text
status: Overall DEGRADED / GFX action required, rc=0
health: Core PASS / GFX action required / overall degraded, rc!=0
verify: core appliance PASS, rc=0
GFX lifecycle: STOCK_REBOOT_REQUIRED / stock reboot required
stock_entry: populated with the verified stock BLS
saved/default: same verified stock BLS
next_entry: same verified stock BLS
primary action: sudo reboot
```

The installer must make the required reboot primary. It may retain the GFX preflight reference only as explicitly deferred guidance such as:

```text
GFX1013 check: after reboot: sudo bc250 gfx1013 prepare --check
```

It must not present the normal preflight as if it is actionable before reboot.

### Prove reset/preflight return codes and non-mutation

Capture boot authority before the transition tests:

```bash
sudo grub2-editenv - list > /tmp/grub-before-transition-tests.txt
```

Then run:

```bash
sudo bc250 gfx1013 reset --check
echo "reset-check rc=$?"

sudo bc250 gfx1013 reset
echo "reset rc=$?"

sudo bc250 gfx1013 prepare --check
echo "prepare-check rc=$?"

sudo bc250 gfx1013 prepare
echo "prepare rc=$?"
```

Expected while stock reboot is pending:

```text
reset --check: PASS, rc=0, next action sudo reboot
reset: PASS / rollback already prepared, rc=0, next action sudo reboot
prepare --check: BLOCKED, rc!=0, next action sudo reboot
prepare: BLOCKED, rc!=0, same reason and next action
```

Now prove those checks did not alter the already-safe boot authority:

```bash
sudo grub2-editenv - list > /tmp/grub-after-transition-tests.txt
diff -u /tmp/grub-before-transition-tests.txt /tmp/grub-after-transition-tests.txt
```

Required diff: empty.

For the blocked preparation calls explicitly record:

```text
Boot state changed: no
Runtime/service state changed: no
Prepared artifacts changed: no
```

### Reboot to stock

```bash
sudo reboot
```

After reboot:

```bash
sudo bc250 gfx1013 status --verbose
sudo bc250 status
sudo bc250 health
sudo bc250 verify
```

Require clean `DISABLED`, stock running/saved boot, no stale one-shot, no private RADV override, health PASS, and core verify PASS.

### Standalone model-install device proof

Before the long GFX rebuild, independently exercise the new user-facing workflow:

```bash
sudo bc250 model status > /tmp/bc250-model-before.txt
sudo bc250 model install
```

At the selection prompt press **Enter without selecting anything**. Then:

```bash
sudo bc250 model status > /tmp/bc250-model-after.txt
diff -u /tmp/bc250-model-before.txt /tmp/bc250-model-after.txt
```

Require:

```text
combined catalog displayed
no implicit all-model selection
no model downloaded or registered
empty before/after diff
```

### Fresh 2.2 GFX activation and stage-boot branch reporting

Continue:

```bash
sudo bc250 gfx1013 prepare --check
sudo bc250 gfx1013 prepare
sudo bc250 gfx1013 status --verbose
sudo grub2-editenv - list
sudo bc250 gfx1013 stage-boot
```

Before calling the stage result a specific branch confirmation, record whether pre-stage `next_entry` was:

```text
empty
```

or:

```text
verified stock
```

Report explicitly:

```text
stage-boot branch: empty next_entry
```

or:

```text
stage-boot branch: verified-stock next_entry replacement
```

If it was empty, do **not** claim device confirmation of the benign-stock replacement branch. That branch remains deterministic source-test-proven unless it executes naturally on-device. Do not fabricate an unknown one-shot entry on production hardware.

Then reboot patched, capture status, and enable:

```bash
sudo reboot
sudo bc250 gfx1013 status --verbose
sudo bc250 gfx1013 enable
sudo bc250 gfx1013 status --verbose
```

Run the established B gate with:

```bash
sudo bc250 gfx1013 benchmark gfx
```

using the existing same-package A1/B/A2 qualification contract in `docs/BENCHMARKING.md`.

### Prove disable transition before reboot

Do not reboot immediately after disable. First run:

```bash
sudo bc250 gfx1013 disable
echo "disable rc=$?"
sudo bc250 gfx1013 status --verbose
sudo grub2-editenv - list
```

Require before reboot:

```text
Disable: PASS
rc=0
saved/default restored to verified stock
next boot stock as required
private RADV override disabled
current runtime still patched
Next action: sudo reboot
```

Only then:

```bash
sudo reboot
```

After stock reboot:

```bash
sudo bc250 gfx1013 status --verbose
sudo bc250 status
sudo bc250 health
sudo bc250 verify
sudo bc250 gfx1013 benchmark restored
sudo bc250 gfx1013 benchmark report
```

`benchmark restored` is the established A2 workload/quality/performance capture; a clean stock boot alone is not A2 completion.

Do not claim complete 2.2 GFX qualification until the exact package has completed B -> disable -> inspected reboot-required transition -> stock reboot -> A2.

## Sidechat return contract

For every material finding provide:

```text
Observed:
...

Interpretation:
...

Required action:
...
```

Classify as `BLOCKING`, `NON-BLOCKING`, `UX`, `EVIDENCE/DIAGNOSTICS`, or `FOLLOW-UP`, and identify whether it is a 2.2 regression, 2.2 fix confirmed, retained behavior, environment issue, or uncertain.

At lifecycle failures include:

```text
Boot state changed: yes/no
Runtime/service state changed: yes/no
Prepared artifacts changed: yes/no
Rollback required: yes/no
```

Finish with:

```text
Recommended main-chat action:
<single primary action>

Safe to continue GFX lifecycle testing: yes/no

Requires new RPM before continuing: yes/no
```
