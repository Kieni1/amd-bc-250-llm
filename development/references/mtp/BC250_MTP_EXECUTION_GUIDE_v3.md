# BC-250 MTP execution guide

This document maps each script/command to the experimental question it answers. Do not run every
script merely because it exists; broad qualification is already complete enough for package work.

## 1. Validate the reference kit

No model inference is performed.

```bash
cd "$HOME/bc250-mtp-reference-kit-v3"
./mtp-kit.sh validate
VALIDATE_RC=$?
printf 'validation_rc=%s\n' "$VALIDATE_RC"
```

Expected success: `KIT VALIDATION PASS`, RC 0.

The validator checks executable bits, shell/Python syntax, corrected override preservation,
actual-depth verification, no broad cleanup/checksum constructs, sourced-caller behavior, and mock
Phase-1/Phase-2 resume integrations. ShellCheck is not claimed when unavailable.

## 2. Capture the current environment

Read-only package/runtime/catalog/model-state snapshot:

```bash
./mtp-kit.sh env
ENV_RC=$?
printf 'environment_rc=%s\n' "$ENV_RC"
```

Implementation: `operator/show-mtp-environment.sh`.

Use this before a release-critical comparison when you want the package NVR, kernel, llama.cpp
version and current MTP manager state visible in the operator console.

## 3. Full Phase-1 qualification for one model

```bash
./mtp-kit.sh phase1 MODEL_ID
PHASE1_RC=$?
printf 'phase1_rc=%s\n' "$PHASE1_RC"
```

Examples:

```bash
./mtp-kit.sh phase1 qwen3.5-9b-mtp
./mtp-kit.sh phase1 qwen3.6-27b-mtp
./mtp-kit.sh phase1 qwen3.8-27b-hauhaucs-mtp
./mtp-kit.sh phase1 qwen3.8-27b-ymq-xs-ti-mtp
```

Core: `phase1/mtp-phase1-reviewed-v5.sh`.

Default workload:
- 128, 256, 400, 768, 1024 generated-token budgets;
- 3 performance repeats per arm;
- 2 deterministic quality repeats;
- same GGUF and llama.cpp build baseline vs MTP;
- active Ollama residency drain;
- live MemAvailable/swap/temperature/kernel safety monitoring;
- exact speculative telemetry and completeness checks;
- final appliance verification and evidence tarball.

Do not use the retired 35B-A3B model with the stock 8K/full-GPU setup.

## 4. Current active-catalog Phase-1 funnel

```bash
./mtp-kit.sh phase1-funnel
FUNNEL_RC=$?
printf 'phase1_funnel_rc=%s\n' "$FUNNEL_RC"
```

Current default order:
1. qwen3.5-9b-mtp
2. qwen3.6-27b-mtp
3. qwen3.8-27b-hauhaucs-mtp
4. qwen3.8-27b-ymq-xs-ti-mtp

Resume after interruption:

```bash
./mtp-kit.sh phase1-funnel --resume "$HOME/bc250-mtp-phase1-funnel-YYYYMMDD-HHMMSS"
RC=$?
printf 'resume_rc=%s\n' "$RC"
```

Use this only when a complete current-package requalification of all active MTP candidates is
actually required. It is intentionally not the normal next step.

## 5. Corrected draft-depth canary

```bash
./mtp-kit.sh phase2-canary
CANARY_RC=$?
printf 'canary_rc=%s\n' "$CANARY_RC"
```

This verifies that requested `DRAFT_N_MAX` reaches both `run-info.txt` and every emitted MTP
`server-config.txt`. It is plumbing evidence, not optimization evidence.

The existing reviewed canary already passed with requested/effective depth 1.

## 6. Corrected original Phase-2 sweep

```bash
./mtp-kit.sh phase2
PHASE2_RC=$?
printf 'phase2_rc=%s\n' "$PHASE2_RC"
```

Runner: `phase2/mtp-phase2-draft-sweep-v5.sh`.

Default models are the original three passers and depths 1,2,3,4. The corrected reviewed sweep is
already complete, so rerun only for a new runtime/package hypothesis.

Current corrected conclusions:
- Qwen3.5 9B: depth 2 was the exploratory balanced winner, +4.0% vs catalog depth 3.
- Qwen3.6 27B: keep depth 2.
- Qwen3.8 HauhauCS: keep depth 2; depth 1's balanced advantage was only ~0.2%.

## 7. Qwen3.5 depth-2 confirmation

This is the only outstanding confirmation needed if package-default promotion from depth 3 to 2
must be confirmation-grade.

```bash
./mtp-kit.sh confirm-qwen35-depth2
CONFIRM_RC=$?
printf 'qwen35_depth2_confirm_rc=%s\n' "$CONFIRM_RC"
```

Implementation: `operator/run-qwen35-depth2-confirm.sh`.

Defaults:
- depth 2 only;
- 256 and 1024 tokens;
- 3 performance repeats;
- 2 quality repeats.

This is deliberately not another four-depth sweep.

## 8. YMQ XS-TI full Phase-1 reference run

```bash
./mtp-kit.sh qualify-ymq
YMQ_RC=$?
printf 'ymq_phase1_rc=%s\n' "$YMQ_RC"
```

Implementation: `operator/run-ymq-phase1.sh`.

The reviewed 2026-09-19 run already passed at:
- context 8192;
- depth 2;
- 128/256/400/768/1024;
- 3 performance repeats;
- 2 quality repeats.

Rerun only if exact installed-package qualification is required after a material runtime change.

## 9. Current-package HauhauCS comparator

Optional control for a rigorous same-current-package YMQ-vs-HauhauCS memory/performance statement:

```bash
./mtp-kit.sh compare-hauhaucs-current
HAU_RC=$?
printf 'hauhaucs_current_rc=%s\n' "$HAU_RC"
```

Implementation: `operator/run-hauhaucs-current-comparator.sh`.

Defaults are 8K/depth 2, budgets 256/1024, 3 performance repeats and 2 quality repeats.

This is not required to establish that either model supports MTP; both already passed qualification.

## 10. Optional YMQ draft-depth optimization

YMQ is already qualified. This command answers only whether depth 1/2/3/4 changes its quality-per-
throughput tradeoff:

```bash
./mtp-kit.sh ymq-depth-sweep
YMQ_P2_RC=$?
printf 'ymq_depth_sweep_rc=%s\n' "$YMQ_P2_RC"
```

Implementation: `operator/run-ymq-depth-sweep.sh`.

Do not run unless YMQ is likely to become a preferred package model and optimization is worth the
time. Apply the same >=1% balanced-improvement threshold before changing its catalog default.

## 11. Package-native comparison harness

For package-smoke/reference evidence rather than campaign-grade qualification:

```bash
./mtp-kit.sh package-compare qwen3.8-27b-ymq-xs-ti-mtp
PACKAGE_COMPARE_RC=$?
printf 'package_compare_rc=%s\n' "$PACKAGE_COMPARE_RC"
```

This invokes installed `bc250-compare-mtp` with the external llama.cpp runtime. The package-native
harness is useful because it exercises the shipped workflow. The bundled Phase-1 v5 harness remains
the reference campaign harness used for the qualification results in this kit.

## 12. Inspect an evidence artifact

```bash
./mtp-kit.sh inspect "$HOME/bc250-mtp-reviewed-qwen3.8-27b-ymq-xs-ti-mtp-*.tar.gz"
INSPECT_RC=$?
printf 'inspect_rc=%s\n' "$INSPECT_RC"
```

`operator/inspect-evidence.sh` is read-only and can inspect either an extracted Phase-1 result root
or a `.tar.gz` archive. It prints run identity, status, performance, quality and completeness when
available.

## Return-code interpretation

The Phase-1 core gives precedence to restoration, then safety, then infrastructure, then archive,
then quality:

- `0`: complete PASS;
- `3`: complete evidence but quality/parity gate failed;
- `70`: archive creation/verification failure;
- safety failures are normally in the 60-class, for example the retired 35B stock-fit run returned 60;
- restoration/infrastructure codes preserve their specific nonzero values.

Always inspect the emitted status file rather than interpreting a nonzero RC as merely "benchmark
failed". Safety/restoration/infrastructure failures answer a different question than quality misses.

## Evidence transfer

Every campaign-grade Phase-1 run prints its exact transfer command. The original campaign used rsync to a separate workstation. The reusable source-tree pattern is:

```bash
sudo rsync -avz --progress "$TARBALL" <user>@<workstation>:/path/to/evidence/
```

No checksum sidecar is generated by the harness.
