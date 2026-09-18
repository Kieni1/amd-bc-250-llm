# BC-250 0.11.3-0.4 patch note

## Release identity

VERSION: `0.11.3`  
RPM Release: `0.4`  
Expected NVR: `bc250-llm-server-0.11.3-0.4`

This release is a bounded MTP-lane hardening release before the first real BC-250
speculative-decoding campaign. It does not promote MTP into normal appliance convergence
or change production office roles.

## What changed

- Replace the old unrelated Ollama-vs-MTP speed probe with a controlled same-target
  comparison. `bc250-compare-mtp ID` runs the same GGUF through the same llama.cpp build,
  context/cache/ubatch and request settings first with MTP disabled and then with
  `draft-mtp` enabled.
- Capture one evidence bundle with package/runtime/model identity, verified manager-state
  SHA, exact server logs/flags, per-request responses and throughput, draft accepted/
  proposed counts, MemAvailable/swap sampling, kernel journal/GPU faults and cleanup state.
- Fail MTP qualification evidence closed on bad completion integrity, server death, failed
  kernel-journal capture, severe GPU/kernel faults or missing draft-acceptance telemetry. Missing acceptance telemetry may
  still be valid inference, but it is not sufficient speculative-decoding evidence.
- Harden `bc250-run-mtp`: exact IDs are first-class, the target must be manager-state
  `CURRENT`, the port must be free, no stale llama-server may exist, MemAvailable must meet
  the launch floor, required llama.cpp flags/access must be present, and the external
  server runs as the `ollama` account rather than root. `--no-mtp` provides the controlled
  baseline path.
- Replace the weak 4B MTP candidate with Qwen3.5 9B; retain Qwen3.6 27B as a control; add
  HauhauCS Qwen3.8 27B IQ2_M and Qwen3.6 35B-A3B. All four remain `enabled = false`,
  download-only and have no Ollama Modelfiles.

## First hardware funnel

Test one candidate at a time and stop when a candidate loses its case:

```text
qwen3.5-9b-mtp
qwen3.6-27b-mtp
qwen3.8-27b-hauhaucs-mtp
qwen3.6-35b-a3b-mtp
```

Prepare and compare the first candidate with:

```bash
bc250-model list mtp --all
sudo bc250-fetch-mtp qwen3.5-9b-mtp
sudo bc250-model status mtp qwen3.5-9b-mtp --include-disabled --verbose
LLAMACPP=/opt/llama.cpp/build/bin/llama-server \
bc250-compare-mtp qwen3.5-9b-mtp
```

The RPM still does not ship llama.cpp. Reviewed baseline remains release `b10964` /
commit `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`; a compatible newer build is allowed when
its exact identity and effective flags are captured.

## Deliberate non-changes

- no production model or Open WebUI role changes;
- no normal Ollama service-topology changes;
- no generic `apply all` inclusion of MTP;
- no quality-threshold, revalidation-acceptance, CU/governor or memory-profile weakening;
- no MTP Ollama Modelfiles or registrations;
- no default `UBATCH=384`; it remains an explicit gfx1013 stability-control A/B only when
  real evidence warrants it.

## Validation

The exact 0.11.3-0.4 source tree and a clean extraction of the release ZIP both passed
RPM/source preflight, packaged shell syntax and 371/371 deterministic tests. Source/archive
closure is complete. Ruff/ShellCheck remain workstation-owned,
GitHub owns RPM/SRPM build, and MTP runtime/GPU/model qualification belongs to the BC-250.

## Real-device next steps

1. GitHub-build and install exact `0.11.3-0.4`; capture installed NEVRA.
2. Keep the MTP campaign and support/power campaign as separate bounded hardware batches.
3. Run the Qwen3.5 9B MTP comparison first; inspect answer usefulness, acceptance, speedup,
   memory/swap and GPU/kernel evidence before deciding whether to advance.
4. Restore/confirm normal appliance health before the next candidate.
5. After MTP evidence, continue the support-operations sequence (S5 WOL, busy defer,
   idle allow + wake, then bounded recovery/lifecycle UX).
