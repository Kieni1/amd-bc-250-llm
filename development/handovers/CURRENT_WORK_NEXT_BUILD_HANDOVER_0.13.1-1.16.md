# BC-250 current work / next-build handover — 0.13.1-1.16

## Scope

This handover is limited to the current Fedora 44 release/build pipeline. Runtime/model/GFX policy is unchanged unless explicitly noted elsewhere.

## Release identity

```text
VERSION       0.13.1
RPM Release   1.16
NVR target    bc250-llm-server-0.13.1-1.16.fc44
Ollama pin    0.40.3
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

## Next Fedora evidence

Run:

```bash
./build-local.sh --full
```

For an intentionally dirty engineering run only:

```bash
./build-local.sh --full --allow-dirty
```

Preserve the complete log. Confirm in particular:

- the sudo prompt occurs at the beginning;
- timestamped checkpoints surround preflight, provisioning and heavy release gates;
- Ruff/ShellCheck and release-pipeline preflight pass before GFX compilation;
- exact-kernel and private RADV gates pass;
- RPM `%check`, transformed-payload validation and configured rpmlint pass;
- clean SRPM self-contained rebuild passes;
- only a clean, snapshot-verified full run prints release qualification.
