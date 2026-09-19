# BC-250 0.11.3-1.6 patch note

## Release identity

VERSION: `0.11.3`  
RPM Release: `1.6`  
Expected NVR: `bc250-llm-server-0.11.3-1.6`

This is a focused MTP evidence/state-closure release on top of 1.5. It intentionally does **not**
change MTP runtime defaults, production model roles, RAG policy, service topology, resource thresholds
or support/maintenance behavior.

## MTP evidence consolidated in 1.6

The current BC-250 evidence now supports treating broad MTP qualification as complete enough for
package use under the reviewed external llama.cpp Vulkan runtime:

- `qwen3.5-9b-mtp`: qualified; fastest absolute candidate and strongest short-generation MTP benefit.
  Corrected Phase-2 depth 2 materially outperformed packaged depth 3, but the package keeps depth 3
  until optional confirmation-grade repeats justify a default change.
- `qwen3.6-27b-mtp`: qualified; strongest sustained long-generation gain of the original set with the
  tightest passing memory margin. Keep draft depth 2.
- `qwen3.8-27b-hauhaucs-mtp`: qualified; more memory headroom and excellent deterministic/parity
  behavior. Keep draft depth 2.
- `qwen3.8-27b-ymq-xs-ti-mtp`: qualified at depth 2; faster baseline decode and stronger absolute
  long-generation MTP throughput than the earlier HauhauCS evidence, but lower observed memory
  headroom and weaker short-token speculative behavior.
- retired `qwen3.6-35b-a3b-mtp`: stock 8K/full-GPU baseline remains a confirmed memory-fit failure
  before MTP inference; do not rerun unchanged.

The first long Phase-2 depth sweep remains invalid for depth selection because it repeated catalog
defaults. It is preserved as repeatability/noise-floor evidence (about 0.01–0.19% throughput CV).
The corrected canary proved requested draft depth reaches the emitted llama-server configuration, and
the corrected 1/2/3/4 sweep completed cleanly on the original three passers.

## Deliberate non-changes

- no packaged MTP draft-depth change;
- no new MTP model candidate;
- no MTP promotion into generic installer/model convergence;
- no change to llama.cpp ownership/version policy;
- no change to production RAG/general/task/translation/agent roles;
- no support/maintenance behavior change;
- no pre-v1 code refactor in this release.

## Optional MTP follow-up only

Further MTP work is not a release prerequisite. Run only when a concrete decision requires it:

1. Qwen3.5 depth-2 confirmation at 256/1024 with 3 performance and 2 quality repeats if changing the
   package default matters;
2. same-current-package HauhauCS comparator if rigorous YMQ/HauhauCS memory comparison matters;
3. YMQ depth optimization only if YMQ is being considered for preferred status.

## Next product/device focus

After exact-source verification/revalidation, move to support and maintenance qualification: local
maintenance/timers/backups, S5 WOL, busy shutdown deferral, idle shutdown/allow + wake, and restricted
Pi/export paths only where configured. Keep disruptive power tests separate from ordinary model
qualification and restore normal topology between batches.

## Evidence references

Current consolidated MTP evidence:
`development/model-runs/2026-09-19-mtp-final-qualification.md`.

External reference kit supplied with the final MTP handoff:
`bc250-mtp-reference-kit-v3.tar.gz`, SHA-256
`16251f8f5bd6a753921f593897fcee3be7cbade26d0a1b83c4b8c2d9f5b7469b`.
The reference kit is not installed by the RPM. Its compact execution guide and validation transcript
are retained source-only under `development/references/mtp/`. The supplied kit validator reports
`KIT VALIDATION PASS` for executable modes, syntax/compile checks, explicit override preservation,
effective-depth verification, exact process-cleanup constraints, mock resume flows and synthetic scorer
RC behavior. The validator performs no BC-250 inference, and ShellCheck was unavailable/not claimed.

Reviewed evidence identities now include:

- corrected Phase-2: `bc250-mtp-phase2-draft-20260919-185429.tar.gz`;
- YMQ Phase-1: `bc250-mtp-reviewed-qwen3.8-27b-ymq-xs-ti-mtp-20260919-204422.tar.gz`.

## Source validation

Current source closure completed:

```text
make validate: PASS
deterministic tests: 403/403 PASS
repository preflight: PASS
```

The source-only specialist reference-kit transcript independently records `KIT VALIDATION PASS` for
its static/mock validator and explicitly states that no BC-250 inference is performed. Ruff, ShellCheck,
RPM/SRPM build and exact installed 1.6 BC-250 qualification are not claimed here.
