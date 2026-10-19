# BC-250 current work / next-build handover — 0.13.1-1.17

## Scope

This handover carries the complete current Fedora 44 release/build boundary plus the
device-found GFX1013 `%prep` failure that defines the 1.17 corrective release. It
preserves the accepted 1.16 build evidence and the exact-kernel/default-off lifecycle
rules; 1.17 changes only the identified dependency/failure-reporting/CLI-information
boundary plus the package-standard Ollama pin.

## Release identity

```text
VERSION       0.13.1
RPM Release   1.17
NVR target    bc250-llm-server-0.13.1-1.17.fc44
Ollama pin    0.40.4
Fedora        44
```

`release-contract.json` is the machine-readable authority for release identity and full/fast stage ordering.

## Current full-build order

`./build-local.sh --full` now follows this order:

1. authenticate sudo once immediately at build startup;
2. run non-root release preflight;
3. freeze/checksum Source0 + spec and validate the exact extracted frozen source;
4. verify a clean Git snapshot did not change during preflight;
5. provision exact Fedora kernel/Mesa build dependencies with `sudo -n`;
6. execute exact-kernel amdgpu, private RADV, RPM/package, rpmlint and clean-SRPM rebuild gates from the frozen source snapshot.

The sudo ticket is refreshed non-interactively throughout the full run. No later stage should display a second password prompt. `--plan` never authenticates or changes the system. `--allow-dirty` remains engineering-only and cannot produce release qualification.

## Timing visibility

`build-local.sh` prints checkpoint records at major stage starts/completions using:

```text
[ISO-8601 timestamp] +HH:MM:SS START <stage>
[ISO-8601 timestamp] +HH:MM:SS DONE  <stage> (stage elapsed Xm Ys)
```

Additional checkpoints identify frozen-source verification and completion of the heavy release gates. Use these timestamps together with the existing GFX heartbeat and before/after `sccache` statistics to identify expensive phases.

## Validation layering

- Host/release-orchestrator contracts run in preflight, before expensive GFX work.
- RPM `%check` runs package/SRPM contracts only.
- Heavy post-provision checks run from the exact frozen source snapshot, not the mutable checkout.
- `result.json` records qualification, Git snapshot verification, release-contract digest and frozen RPM-input digests.

The Ruff import-order defect in `tests/test_release_pipeline.py` is corrected; imports are stdlib-sorted (`json`, `os`, `re`, ...).

## Accepted 1.16 build evidence — historical baseline for 1.17

The second post-hardening Fedora 44 run is the accepted 1.16 release-build baseline.
Do not replace this with the earlier pre-patch run when reasoning about pipeline state.

```text
source commit     56e8abf2e1702d02b0e5bab177f91f29e7b2d214 (clean)
Fedora            44
kernel            7.2.9-201.fc44.x86_64
jobs              16/16
host pipeline     18/18 PASS
preflight         PASS, frozen source validated before heavy work
kernel gate       PASS, exact patched-amdgpu build/ABI
Mesa gate         PASS, private headless RADV
RPM %check        PASS
payload gate      PASS
rpmlint           0 errors, 2 changelog-macro warnings
SRPM rebuild      PASS
full release gate PASS
total gate time   10m47s
```

1.16 accepted artifact identity:

```text
binary NEVRA
  bc250-llm-server-0.13.1-1.16.fc44.x86_64

binary SHA-256
  ad50e5fb4f49d55b1dcf5c45e7f58338ae03a6952864a11ef18a789fbf08f072

SRPM SHA-256
  566459d2d13a0792c62533836370697cb1c98e5391450d29f2a974ab1c0d0d2b
```

The timestamped build showed that release preflight/frozen-source validation cost
about 40 seconds, privileged dependency provisioning about 2 seconds, and the heavy
authoritative build about 10m02s. Patched-amdgpu compilation was about 1m46s. C/C++
sccache reuse was effectively complete in that second run while Rust reuse remained
very low; that is a later optimization topic, not a 1.17 correctness requirement.

## Device failure that defines 1.17

The exact 1.16 RPM was then exercised on the BC-250 after the running Fedora kernel
advanced to `7.2.10-200.fc44.x86_64`.

`bc250 gfx1013 prepare` successfully acquired and verified:

```text
kernel-7.2.10-200.fc44.src.rpm
```

It then failed immediately in Fedora kernel `%prep`, before patched module or Mesa
build work. The first meaningful error preserved by `kernel-prep.log` was:

```text
kernel.spec:2216: Fixing Python shebangs...
+ %py3_shebang_fix tools/kvm/kvm_stat/kvm_stat ...
/var/tmp/rpm-tmp...: line 171: fg: no job control
error: Bad exit status ... (%prep)
```

The shell received literal `%py3_shebang_fix` because RPM had not expanded that
macro. Shell job-control parsing then produced `fg: no job control`.

Fedora 44 exposes the requirement through the RPM capability:

```text
rpm_macro(py3_shebang_fix)
```

The normal provider is `python3-rpm-macros`. The runtime/device GFX1013 dependency
contract in 1.16 did not check this capability even though the Fedora build-host
provisioning path already knew to require the macro before its own kernel `%prep`.
That asymmetry allowed `prepare --check` to pass the dependency layer on the device
and let the failure appear only after source acquisition.

### Safety result from the device failure

The failure was bounded correctly and these properties must remain unchanged:

- exact kernel SRPM acquisition and verification worked;
- source cache preservation worked;
- numbered seven-stage progress worked;
- the failure occurred before patched module/Mesa build;
- boot state remained unchanged;
- runtime/service state remained unchanged;
- GFX1013 remained `DISABLED`.

No exact-kernel, rollback, boot-authority or lifecycle policy change is justified by
this failure.

## Required 1.17 GFX1013 dependency repair

The prepare requirement set now contains the capability itself:

```text
rpm_macro(py3_shebang_fix)
```

Provider resolution remains RPM-exit-status-authoritative. A successful exact
package lookup may satisfy a normal package requirement; otherwise
`rpm -q --whatprovides` resolves the capability. The implementation must not infer
installation from non-empty failure stdout.

Expected behavior:

1. when `rpm_macro(py3_shebang_fix)` has no installed provider, default
   `prepare --check` reports the capability as `NOT INSTALLED`, reports the overall
   dependency layer `BLOCKED`, gives one remediation command and exits blocked;
2. normal `prepare` performs the same requirement check before any kernel/Mesa
   source acquisition or build activity and refuses when the capability is absent;
3. when `python3-rpm-macros` (or another installed provider) provides the capability,
   the dependency layer treats it as satisfied;
4. the exact-kernel SRPM/rollback/lifecycle code remains unchanged after the gate.

The deterministic suite includes both the negative pre-source-acquisition case and
the positive capability-provider case.

## 1.17 prepare/status information hierarchy

The 1.16 CLI contains the information needed for diagnosis but normal output is too
dense. 1.17 applies the following rule without deleting forensic information:

**Default output:** current state, blockers/exceptions, safety impact and next action.

**Verbose/evidence output:** complete providers, hashes, URLs, paths, boot internals,
provenance and detailed build diagnostics.

### `prepare --check`

Default mode summarizes satisfied dependencies and prints only exceptions. It keeps
the integrity results, kernel/reference policy, source-cache readiness, final result,
fix and rerun action visible. The complete provider table moves to:

```bash
sudo bc250 gfx1013 prepare --check --verbose
```

Normal `prepare` retains stage number/name, artifact identity, useful size/cache and
download/resume state, elapsed progress and validation results. Complete Koji/source
URLs and redundant full identities remain verbose/evidence detail.

### Failure summary

The old overlapping sequence:

```text
Fedora kernel %prep failed...
ERROR: Fedora kernel %prep failed...
GFX1013 prepare: FAILED
Failing stage: kernel-source-and-module-build
First authoritative failure: unknown
```

is replaced by one structured summary, for example:

```text
Result: FAILED
Stage: Fedora kernel %prep
Cause: required RPM macro unavailable: py3_shebang_fix
Evidence: /var/lib/bc250-llm-server/gfx1013/prepare-evidence/...tar.gz
Boot state changed: no
Runtime/service state changed: no
Source cache preserved: yes (...)
```

Known `%py3_shebang_fix` + `fg: no job control` evidence classifies to the explicit
cause above. Otherwise the first meaningful error from the failing stage log is
surfaced as `unclassified — <line>`. Use `unclassified — see evidence` only when the
stage log genuinely contains no meaningful error. Do not emit `unknown`.

### Evidence archive format

Prepare failure evidence is preserved as an actually gzip-compressed `.tar.gz`.
Creation is validated with `gzip -t` and `tar -tzf` before publication. The filename
and produced archive format must always agree.

### `status`

Default `status` is operator-focused. `status --brief` remains suitable for handovers
and harness checks. `status --verbose` owns the upstream/Mesa hashes, detailed boot
state, full dependency/provider and evidence detail. `status --json` remains the
machine-readable lifecycle contract.

## Ollama 0.40.4 pin

1.17 advances only the package-standard Ollama runtime pin; Open WebUI, Tika,
governor, production model/context/memory/swap policy and GFX profile are otherwise
unchanged.

```text
version  0.40.4
asset    ollama-linux-amd64.tar.zst
sha256   15f31e9576d15a481e099b4145dba6e9f8c1f295927d6b8895300ae30ed3740a
```

This is a source/package pin, not inherited device qualification. The exact 1.17 RPM
must receive fresh runtime acceptance after the Fedora full build.

## Additional build-driver operator contract

On a successful local build, the final stdout line from `build-local.sh` is the full
path to the generated main non-debug RPM. Nothing is printed after that path. This
makes the artifact directly usable by shell/operator handoff without parsing the
earlier artifact listing.

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

## Next Fedora evidence for 1.17

Run:

```bash
./build-local.sh --full
```

For an intentionally dirty engineering run only:

```bash
./build-local.sh --full --allow-dirty
```

Preserve the complete log. 1.16 full-gate success does **not** qualify 1.17. Confirm
in particular:

- the sudo prompt occurs at the beginning;
- timestamped checkpoints surround preflight, provisioning and heavy release gates;
- Ruff/ShellCheck and release-pipeline preflight pass before GFX compilation;
- exact-kernel and private RADV gates pass;
- RPM `%check`, transformed-payload validation and configured rpmlint pass;
- clean SRPM self-contained rebuild passes;
- only a clean, snapshot-verified full run prints release qualification.
- the package NEVRA is `bc250-llm-server-0.13.1-1.17.fc44.x86_64`;
- the packaged runtime pin is Ollama 0.40.4 with the exact payload SHA above;
- the final script output line is the generated main RPM path.

After the clean 1.17 Fedora full gate, install that exact binary on the BC-250 and
rerun:

```bash
sudo bc250 gfx1013 status --brief
sudo bc250 gfx1013 prepare --check
```

If the macro capability is absent, this is now an expected early `BLOCKED` result;
install the reported provider, rerun the check and only continue when preflight is
clean. Then resume the existing greenfield lifecycle:

```text
prepare -> stage-boot -> patched reboot -> enable -> B -> disable/reset -> stock reboot -> A2
```

Capture a fresh 1.17 A1 before using B/A2 for qualification. Do not inherit the 1.16
device attempt as a successful GFX qualification.
