# BC-250 testing handover — 0.13.1-1.17

## Purpose

This is the current next-release testing handover after the clean 1.16 Fedora release build and the first exact-device GFX1013 prepare attempt exposed a missing Fedora RPM-macro capability in the device-side prepare dependency gate. It is intentionally detailed. The complete 1.16 testing handover, including its retained 1.13 history, remains below this current section verbatim so future integration work can reconstruct why the current gates exist rather than seeing only the latest symptom.

1.17 is a corrective release candidate. It does not inherit device qualification from 1.16. The accepted 1.16 build is the immediate package/build baseline; the 1.16 device attempt is authoritative failure evidence that defines the new dependency and failure-reporting requirements.

## Release identity

```text
VERSION              0.13.1
RPM Release          1.17
NVR target           bc250-llm-server-0.13.1-1.17.fc44
Fedora               44
Ollama pin           0.40.4
GFX1013 profile      v0.2.5-alpha
GFX upstream         0.2.0-alpha / d3e6dc062c34d2523db0abe5741d1f5b0dea00d9
Mesa baseline        mesa-26.2.4-1.fc44.src
```

`release-contract.json` is the machine-readable package/build identity authority. Exact-kernel source authority, stock-first boot authority, rollback behavior, private-RADV activation rules, production model/context/memory/swap policy and default-off GFX lifecycle are unchanged from 1.16.

## Accepted 1.16 build authority — predecessor evidence

The clean Fedora 44 full build remains the accepted immediate predecessor for build-pipeline behavior:

```text
source commit       56e8abf2e1702d02b0e5bab177f91f29e7b2d214 (clean)
kernel              7.2.9-201.fc44.x86_64
jobs                16/16
binary               bc250-llm-server-0.13.1-1.16.fc44.x86_64
binary SHA-256       ad50e5fb4f49d55b1dcf5c45e7f58338ae03a6952864a11ef18a789fbf08f072
SRPM SHA-256         566459d2d13a0792c62533836370697cb1c98e5391450d29f2a974ab1c0d0d2b
frozen Source0       57188efd7ef505fe83b325f9e5afe90a259ec6a9fc1a71e756d6f4e42a1aeff3
frozen spec          52fdcce35bab5ee2f7b622884e1aca5a5c67eda8f03b88aa25493a8e420a55ec
full release gate    PASS
total elapsed        10m47s
```

That run proved the layered/frozen release pipeline, exact Fedora kernel build/ABI check, private headless RADV build, RPM package checks, transformed-payload integrity, rpmlint execution, closed artifact manifests and isolated self-contained SRPM rebuild. It did not qualify GFX1013 on the device.

## Device failure that defines 1.17

Package exercised:

```text
bc250-llm-server-0.13.1-1.16.fc44.x86_64
```

The device had advanced to:

```text
7.2.10-200.fc44.x86_64
```

`bc250 gfx1013 prepare` successfully downloaded and verified:

```text
kernel-7.2.10-200.fc44.src.rpm
```

It then failed immediately during Fedora kernel `%prep`. The first real error in `kernel-prep.log` was:

```text
kernel.spec:2216: Fixing Python shebangs...
+ %py3_shebang_fix tools/kvm/kvm_stat/kvm_stat ...
/var/tmp/rpm-tmp...: line 171: fg: no job control
error: Bad exit status ... (%prep)
```

The RPM macro was not expanded. The shell therefore received the literal `%py3_shebang_fix`; `%...` was interpreted as shell job-control syntax and produced `fg: no job control`.

Fedora 44 exposes the requirement as the RPM capability:

```text
rpm_macro(py3_shebang_fix)
```

The normal installed provider is `python3-rpm-macros`. The 1.16 build-workstation dependency provisioning already guarded this macro before its own kernel `%prep`, but the installed/device `gfx1013 prepare` dependency model did not. This was an asymmetry in dependency qualification, not a kernel patch, exact-kernel, Mesa, rollback or lifecycle failure.

## Safety outcome of the 1.16 device failure

The failure remained safely bounded. Preserve these properties:

- kernel SRPM acquisition and verification worked;
- cache preservation worked;
- explicit seven-stage progress worked;
- failure occurred before patched amdgpu/module build and before Mesa/private RADV build;
- boot state remained unchanged;
- runtime/service state remained unchanged;
- GFX1013 remained `DISABLED`;
- stock/default boot authority was not changed.

Do not modify exact-kernel provenance, one-shot patched boot, rollback, enable/disable/reset or default-off policy as part of the macro repair.

## 1.17 dependency contract

The device-side prepare requirement set now includes the capability itself:

```text
rpm_macro(py3_shebang_fix)
```

Provider resolution is capability-aware and RPM-exit-status-authoritative. Do not treat non-empty `rpm -q` failure text as an installed provider.

Required behavior:

1. if all ordinary GFX1013 build dependencies are installed but `rpm_macro(py3_shebang_fix)` has no installed provider, `prepare --check` must report it as `NOT INSTALLED`, mark the dependency layer `BLOCKED`, emit one remediation command and return blocked;
2. actual `prepare` must perform the same requirement gate and refuse before kernel/Mesa source acquisition or build when the macro capability is absent;
3. when `python3-rpm-macros`, or another valid installed provider, provides the capability, the requirement is satisfied;
4. compatibility-provider behavior such as `zlib-devel` satisfied by `zlib-ng-compat-devel` remains valid;
5. the exact-kernel and lifecycle code after this dependency boundary is unchanged.

The deterministic GFX suite contains negative and positive behavioral provider tests, including a source-acquisition marker proving that the missing-macro case exits before source work.

## 1.17 failure classification contract

The 1.16 evidence archive contained a clear failure but recorded:

```text
reason=unknown
```

and the CLI emitted:

```text
First authoritative failure: unknown
```

That is no longer acceptable. 1.17 uses the exact active prepare stage and classifies known `%py3_shebang_fix` plus `fg: no job control` evidence as:

```text
Result: FAILED
Stage: Fedora kernel %prep
Cause: required RPM macro unavailable: py3_shebang_fix
```

For an otherwise unclassified stage failure, preserve/surface the first meaningful error line as:

```text
Cause: unclassified — <first meaningful error>
```

Only when no meaningful stage-log error exists may the fallback be:

```text
Cause: unclassified — see evidence
```

Do not return the opaque word `unknown` when evidence contains the cause. Do not collapse the exact stage back to the broader internal phase `kernel-source-and-module-build` in the normal operator summary.

## Evidence archive format contract

The 1.16 device evidence file used a `.tar.gz` suffix but contained an uncompressed POSIX tar stream. 1.17 fixes the producer rather than changing the public filename: prepare failure evidence is actually gzip-compressed and is verified before publication with both `gzip -t` and `tar -tzf`.

The published evidence filename and its bytes must agree. The regression suite verifies the gzip magic and opens the produced archive as gzip-compressed tar.

## GFX1013 CLI information hierarchy

The next-release CLI keeps the information added during 1.16 but makes normal output operational rather than forensic.

### Default `prepare --check`

Default output should prioritize:

- host/tooling aggregate state;
- dependency aggregate state and only missing requirements;
- source and installed-payload integrity;
- exact running-kernel target/reference relationship;
- source-cache readiness;
- final result;
- one fix command and rerun action when blocked;
- explicit statement that preflight changed no files/boot/services where appropriate.

Do not print every satisfied dependency/provider by default. The complete table remains available with:

```bash
sudo bc250 gfx1013 prepare --check --verbose
```

### Normal `prepare`

Keep by default:

- stage number and exact stage name;
- artifact filename;
- approximate artifact size;
- cache `HIT`/`MISS`/partial state;
- download/resume progress;
- elapsed-time heartbeat/result;
- validation outcome.

Move full Koji/source URLs, redundant expected identity strings, hashes already preserved in evidence and detailed provenance to verbose/evidence output.

### Failure output

Use one structured failure summary instead of repeating the same failure in several forms. Expected shape:

```text
[2/7] Fedora kernel %prep — FAILED after 00:08

Result: FAILED
Stage: Fedora kernel %prep
Cause: required RPM macro unavailable: py3_shebang_fix
Evidence: /var/lib/bc250-llm-server/gfx1013/prepare-evidence/...tar.gz
Boot state changed: no
Runtime/service state changed: no
Source cache preserved: yes
```

### `status`

Normal `gfx1013 status` is operator-focused. `status --brief` stays intentionally small for handovers/harness checks. `status --verbose` owns complete dependency/provider, hashes, URLs, build-tree paths, detailed boot internals and provenance. `status --json` remains the machine-readable lifecycle surface.

The governing output rule is:

**Default:** current state, exceptions/blockers, safety impact, next action.

**Verbose/evidence:** every provider, hashes, URLs, paths, boot internals, provenance and detailed diagnostics.

## Ollama 0.40.4 package pin

1.17 advances the package-standard runtime from 0.40.3 to 0.40.4:

```text
version   0.40.4
asset     https://github.com/ollama/ollama/releases/download/v0.40.4/ollama-linux-amd64.tar.zst
sha256    15f31e9576d15a481e099b4145dba6e9f8c1f295927d6b8895300ae30ed3740a
```

This is a package/source pin only. It requires fresh exact-device runtime acceptance. Do not inherit 0.40.3 performance/service qualification simply because the GFX corrective change is otherwise narrow. Open WebUI 0.11.4, Tika 4.1.0-full, governor 0.4.13, production model roles, context policy, TTM/swap and governor settings remain unchanged.

## Build-driver operator output

On a successful local build, the last stdout line from `build-local.sh` must be the full path to the generated main non-debug RPM, ending in a filename such as:

```text
bc250-llm-server-0.13.1-1.17.fc44.x86_64.rpm
```

No informational line is printed after that path. This is an operator/automation handoff contract and has a release-pipeline regression test.

## Source validation completed before the Fedora 1.17 build

The exact generated Source0 archive was extracted and validated rather than relying only on the mutable checkout. Current source-level evidence is:

- shell syntax PASS for `cmd/system/gfx1013.sh` and `build-local.sh`;
- `python3 scripts/validate.py --preflight` PASS;
- `python3 development/scope.py check` PASS;
- release-pipeline preflight PASS, 19/19 tests;
- 42/42 GFX1013 lifecycle/dependency/failure/evidence tests PASS, including the missing and positive macro-capability cases, precise `%prep` classification, real gzip evidence archive, concise/verbose output split, and brief-status output contract;
- 54/54 packaging tests PASS;
- 20/20 documentation tests PASS;
- an additional 194/194 source/install/runtime/Open WebUI/operations/GFX provenance/qualification/state tests PASS;
- all 329 changed/high-risk deterministic tests above also PASS from the extracted exact Source0 archive.

A one-shot `scripts/validate.sh --package` attempt in the assistant container was stopped by the environment while `test_benchmark.py` was still running. Do not turn that into a complete package-wrapper PASS claim. Ruff and ShellCheck are also unavailable in this assistant container. No Fedora 44 RPM/exact-kernel/private-RADV build for 1.17 has been run here. The authoritative next step remains a clean Fedora `./build-local.sh --full`.

## Required Fedora 1.17 full build

From a clean 1.17 checkout on Fedora 44:

```bash
./build-local.sh --full
```

Preserve:

- complete timestamped build log;
- clean source commit;
- frozen Source0 and spec SHA-256;
- binary main RPM NEVRA and SHA-256;
- SRPM SHA-256;
- `result.json` qualification state;
- final stdout RPM path.

Expected release identity:

```text
bc250-llm-server-0.13.1-1.17.fc44.x86_64
```

The full gate must prove lint/release contracts, frozen-source package validation, exact Fedora kernel build/ABI, private headless RADV, RPM package checks, transformed payload integrity, rpmlint and clean self-contained SRPM rebuild. A dirty `--allow-dirty` engineering pass is useful evidence but is never release qualification.

## Required exact-device sequence after the clean 1.17 build

Install only the exact main RPM from the successful clean 1.17 gate. Then:

1. record `rpm -q bc250-llm-server` and `rpm -V bc250-llm-server`;
2. run `sudo bc250 install` and verify desired/observed Ollama 0.40.4;
3. perform short stock acceptance (`bc250 version`, `sudo bc250 status`, `sudo bc250 verify`, failed units, CU routing, basic model/service smoke);
4. run:

```bash
sudo bc250 gfx1013 status --brief
sudo bc250 gfx1013 prepare --check
```

5. if `rpm_macro(py3_shebang_fix)` is absent, the check must now block early and name it; install the reported provider and rerun the check;
6. use `sudo bc250 gfx1013 prepare --check --verbose` only when complete provider/provenance detail is needed;
7. if preflight is clean, capture fresh 1.17 A1 and continue the unchanged lifecycle:

```text
prepare -> stage-boot -> reboot patched -> enable -> B -> disable/reset -> reboot stock -> A2
```

8. preserve exact kernel, boot state, GFX lifecycle state, evidence archive, runtime/service state, output identity/performance and restoration state at every boundary.

## Regressions to watch specifically in 1.17

- `prepare --check` passes while `rpm_macro(py3_shebang_fix)` is unavailable;
- missing capability output is mistaken for an installed provider because `rpm` printed failure text;
- actual `prepare` reaches source acquisition before blocking a missing macro requirement;
- `%prep` failure returns `unknown` despite a meaningful stage-log error;
- failure summary reports only broad `kernel-source-and-module-build` instead of exact `Fedora kernel %prep`;
- evidence file suffix says `.tar.gz` while bytes are plain tar;
- concise default output drops the blocker, integrity result, safety effect or next action;
- verbose output loses the detailed provider/provenance information that was intentionally moved out of default output;
- exact-kernel/rollback/lifecycle behavior changes as collateral damage;
- Ollama runtime remains 0.40.3 or carries a payload hash other than the pinned 0.40.4 hash;
- final successful `build-local.sh` output contains lines after the generated main RPM path.

## Acceptance boundary

1.17 is not release-qualified until the clean Fedora 44 full gate passes for the exact 1.17 source. After that, package progress still does not promote GFX1013: the exact installed 1.17 RPM must receive fresh stock acceptance and fresh A1/B/A2 evidence. GFX1013 remains experimental and default-off until that sequence is complete and convincing.

---

# Historical testing handover retained verbatim — 0.13.1-1.16 and earlier

# BC-250 testing handover — 0.13.1-1.16

## Purpose

This is the current testing continuation after the 1.13–1.16 build/integration repair cycle. The old 1.13 handover is retained verbatim below because it documents the transformed-payload integrity failure that motivated several later gates. Current authority is the clean 1.16 full build described here.

## Exact current build authority

- source commit: `56e8abf2e1702d02b0e5bab177f91f29e7b2d214` (**clean**)
- Fedora: 44
- kernel: `7.2.9-201.fc44.x86_64`
- RPM: `bc250-llm-server-0.13.1-1.16.fc44.x86_64`
- RPM SHA-256: `ad50e5fb4f49d55b1dcf5c45e7f58338ae03a6952864a11ef18a789fbf08f072`
- SRPM SHA-256: `566459d2d13a0792c62533836370697cb1c98e5391450d29f2a974ab1c0d0d2b`
- frozen Source0 SHA-256: `57188efd7ef505fe83b325f9e5afe90a259ec6a9fc1a71e756d6f4e42a1aeff3`
- frozen spec SHA-256: `52fdcce35bab5ee2f7b622884e1aca5a5c67eda8f03b88aa25493a8e420a55ec`
- Ollama pin: `0.40.3`
- GFX1013 profile: `v0.2.5-alpha`
- Mesa baseline: `26.2.4-1.fc44`

The authoritative Fedora `./build-local.sh --full` run passed. Timing: sudo authentication 3s; complete release preflight 40s; dependency provisioning 2s; frozen-source authoritative build 10m02s; total through `FULL LOCAL RELEASE GATE PASSED` 10m47s.

## What the accepted full gate proved

PASS:

- Ruff/lint and release-pipeline contract layer (18 host tests);
- source provenance and upstream patch validation;
- frozen Source0/spec checksums;
- complete package validation against the extracted frozen source (641 tests);
- exact Fedora running-kernel amdgpu external-module build/ABI;
- private headless RADV build from Mesa `26.2.4-1.fc44`;
- primary RPM `%check` package validation;
- transformed RPM payload integrity, including GFX manifests and Ollama pin;
- artifact checksum manifests;
- rpmlint execution (0 errors, 2 non-blocking `%changelog` macro warnings);
- isolated SRPM self-contained rebuild including package `%check`;
- clean-source release qualification.

This is build/package evidence only. It does not promote GFX1013 or replace device testing.

## Required device sequence

Use only the exact main RPM hash above.

1. Install 1.16 and record `rpm -q bc250-llm-server` plus `rpm -V bc250-llm-server`.
2. Run `sudo bc250 install`; capture desired and observed Ollama versions and ensure 0.40.3.
3. Run stock acceptance: `bc250 version`, `sudo bc250 status`, `sudo bc250 verify`, failed units, CU routing, basic service/model smoke.
4. Run:

```bash
sudo bc250 gfx1013 status --brief
sudo bc250 gfx1013 prepare --check
```

5. Preserve the complete output. Both carried source integrity and installed RPM payload integrity must pass.
6. Dependency-provider reporting must be trustworthy: genuinely missing requirements show `<none>` / `NOT INSTALLED` and BLOCKED; do not treat `package X is not installed` stdout as an installed provider.
7. If preflight is blocked, stop and return the first authoritative blocker. Do not edit package-owned files or manifests.
8. Only if stock acceptance and GFX preflight are clean continue:

```text
prepare -> status -> stage-boot -> reboot patched -> status -> enable -> B -> disable/reset -> reboot stock -> A2
```

9. Preserve exact kernel, boot entry/state, GFX lifecycle state, journal evidence, model/runtime evidence, and restoration state at each boundary.

## Production-context policy during testing

External context-ceiling experiments are allocation-limit evidence, not production-context recommendations. Do not raise service/model defaults during device qualification. Balanced remains 32,768 with q8_0; max-context 65,536/q4_0 remains an explicit operator experiment/profile. TTM, swap and governor policy remain unchanged unless a separate bounded service-like qualification justifies a change.

## Current regressions to watch

- source/RPM identity mismatch or installation of an RPM other than the accepted hash;
- RPM/BRP rewriting of integrity-covered GFX source bytes;
- Ollama pin/service environment drifting from 0.40.3/Vulkan/iGPU/device-selection contract;
- dependency-provider false positives;
- GFX lifecycle mutation during `prepare --check`;
- rollback that does not return to the stock boot/runtime state;
- interpreting benchmark allocation ceiling as safe service context;
- carrying old 1.12/1.13 device PASS across the 1.16 RPM boundary.

## Non-blocking build backlog — do not invalidate 1.16 for this

The accepted build showed C/C++ sccache at 100% but Rust at 0.94% (2 hits, 210 misses), so Rust cache-key reuse is the main build-time optimization candidate. Also queued for a later release: remove two rpmlint `%changelog` warnings, regenerate the pinned live-manager patch to zero-offset hunks, and append the final result/qualification summary to the logfile. These are not reasons to modify the accepted 1.16 source before device qualification.

## Acceptance boundary

A clean 1.16 build gate is now proven. The next promotion boundary is exact-RPM stock device acceptance. GFX1013 remains experimental/default-off until fresh A1/B/A2 evidence for this exact RPM and device state is complete and convincing.

---

# Historical testing handover retained verbatim — 0.13.1-1.13

# BC-250 testing handover — 0.13.1-1.13

## Purpose

This is the first repair batch after the 1.12 device pass found that the locally available 1.12 RPM was not the exact-current source build and that GFX1013 `prepare --check` was permanently blocked by RPM Python shebang normalization changing a file covered by `SOURCE-SHA256SUMS`.

Treat 1.13 as a greenfield qualification candidate. Do not inherit qualification from the previously installed 1.12 RPM.

## What changed

- RPM Release bumped from 1.12 to 1.13.
- `gfx1013/upstream/check-kernel-provenance.py` is now true Python data: its unnecessary shebang was removed and it is installed mode 0644. Runtime already invokes it explicitly with `python3`.
- `SOURCE-SHA256SUMS` was updated for that intentional source-byte change.
- The built-RPM payload gate now extracts the final RPM with `rpm2cpio | cpio` and verifies, after RPM/BRP transformations:
  - `PATCH-SHA256SUMS`;
  - `SOURCE-SHA256SUMS`;
  - provenance-helper mode is 0644;
  - packaged `BC250_OLLAMA_VERSION` equals source `config/runtime.env` (0.40.3).
- GFX1013 now reports two distinct integrity layers:
  - carried source integrity;
  - installed RPM payload integrity (RPM database verification of the installed GFX source payload).
- `prepare --check` now surfaces source-integrity detail, uses required-dependency wording, reports installed providers accurately, aggregates dependency remediation, and prints a final fix/rerun summary.
- `gfx1013 status --brief` and lifecycle-derived `Next action:` guidance were added.
- `bc250 install` now prints desired/observed Ollama versions, verifies the post-reconciliation version, and includes GFX1013 readiness/help in completion guidance.
- GitHub is no longer an RPM release-build authority. It performs deterministic source/static validation only. The authoritative release path is local Fedora 44 `./build-local.sh --full`.
- Active build/testing documentation and regression tests were updated to match the local-build model.
- Generated `__pycache__`/`.pyc` files were removed from the delivered source tree.

## Source validation performed in main chat

PASS:

- `python3 scripts/validate.py --preflight`
- `python3 development/scope.py check`
- shell syntax for changed shell entry points
- changed-surface deterministic suite: 172/172 PASS
- every remaining deterministic test module also completed PASS in split batches

The chat execution environment imposed an outer timeout during a single `scripts/validate.sh` wrapper invocation while modules were still passing. Therefore do not record a one-shot wrapper PASS from this environment; all modules were nevertheless exercised successfully across bounded runs.

## Required local build gate

On the Fedora 44 build workstation, from this exact 1.13 source:

```bash
./build-local.sh --full
```

Preserve:

- complete build log;
- binary RPM NEVRA;
- binary RPM SHA-256 / `SHA256SUMS.binary`;
- SRPM SHA-256 / `SHA256SUMS.source`.

The build is a FAIL if the new transformed-RPM payload integrity phase does not pass. Do not bypass or edit the manifest after build.

Before device installation, verify the binary is exactly:

```text
bc250-llm-server-0.13.1-1.13.fc44.x86_64
```

and verify its extracted/package runtime metadata pins:

```text
BC250_OLLAMA_VERSION=0.40.3
```

## Device sequence

Use only the exact RPM from the successful local full gate.

1. Install 1.13 as the greenfield qualification candidate.
2. Record `rpm -q bc250-llm-server` and `rpm -V bc250-llm-server`.
3. Run `sudo bc250 install` and capture the desired/observed Ollama version lines.
4. Run short stock acceptance: `bc250 version`, `sudo bc250 status`, `sudo bc250 verify`, failed units, live CU routing.
5. Run:

```bash
sudo bc250 gfx1013 status --brief
sudo bc250 gfx1013 prepare --check
```

Expected integrity lines are both PASS:

```text
Carried source integrity: PASS
Installed RPM payload integrity: PASS
```

6. If `prepare --check` is blocked, stop and return the complete output; do not mutate package files or manifests.
7. Only if preflight is clean continue:

```text
prepare -> patched reboot -> enable -> B -> disable/reset -> stock reboot -> A2
```

Preserve the first authoritative failure and evidence at every boundary.

## Specific regressions to watch

- Any shebang/content rewrite of `check-kernel-provenance.py` after RPM build.
- Built RPM carrying Ollama 0.34.4 or any pin other than 0.40.3.
- `rpm -V` clean while package-owned installed-payload integrity reports failure.
- Dependency output saying “no package provides” when the actual state is merely “not installed.”
- Duplicate dependency blockers producing multiple remediation counts for the same install action.
- GFX lifecycle mutation occurring during `prepare --check`.

## Acceptance boundary

A successful local 1.13 RPM build plus clean stock device acceptance is package progress, but it does not promote GFX1013. GFX remains experimental/default-off until the exact 1.13 A1/B/A2 sequence is complete and convincing.
