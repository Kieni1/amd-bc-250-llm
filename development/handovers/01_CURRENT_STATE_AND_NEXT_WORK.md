# Current state and next work — 0.14.1-1.7

## Current source/release identity

The active line is `bc250-llm-server-0.14.1-1.7`.

RPM naming rule:

- new product version -> `Release: 1`;
- package-only correction may use a dotted numeric release (`1.1`, `1.2`, ...) while the product version stays fixed;
- next product version -> reset Release to `1`.

Never publish changed bytes under an already-used NVR.

## Current architecture

The supported core is:

- Fedora 44 stock kernel/userspace path;
- package-owned Ollama/Open WebUI/Tika/governor stack;
- normal main/task/embedding Ollama lanes and optional exclusive agent mode;
- package model management and public `bc250` commands;
- GitHub Actions/Fedora 44 as primary release-build authority;
- local Fedora execution as secondary reproduction/debugging;
- no package-owned patched kernel boot, private Mesa/RADV or GFX lifecycle.

Current runtime pins in source:

```text
Ollama       0.40.8
Open WebUI   0.12.3
Tika         4.1.0-full
Governor     0.4.14
```

Treat these as current package choices, not permanent architectural commitments.

## 1.4 authoritative-build result

The SRPM-first release architecture is now proven by a successful Fedora 44 GitHub run:

```text
previous 1.3-era total:        8m45s
previous release gate:         7m31s
previous Rust compilations:    ~2m31s + ~2m33s

1.4 total:                     5m58s
1.4 release gate:              4m29s
1.4 Rust compilation:          2m49s once
```

This is the architecture to keep. Do not restore the old `rpmbuild -ba` plus proof-rebuild chain. The binaries distributed by 1.4 are the exact outputs of the isolated rebuild of the published SRPM. Payload validation and blocking rpmlint passed in the successful run.

Release 1.5 keeps this SRPM-first architecture and folds in the queued low-risk observability cleanup: the rebuild summary now identifies the source SRPM and prints the actual rebuilt binary RPM filenames, and the release path emits machine-greppable `BC250_TIMING` records for the major stages. `%check` timing is measured inside the authoritative rebuild; no extra build was added.

Use the new timing data from successful 1.5 authority runs before proposing another build optimization. Do not add sccache, a custom builder image or other caching to authority runs without measured justification and an explicit evidence-policy decision.

## Exact 1.4 device baseline carried forward

Release 1.7 carries Ollama 0.40.8 and governor 0.4.14 unchanged from the 1.6 source baseline and adds managed-RAG lifecycle corrections. Prior exact-device PASS remains regression baseline rather than acceptance for the new package bytes. The existing four-lane Vulkan/context/keep-alive, model and retrieval policy remains intentionally unchanged.

The exact selected `0.14.1-1.4` RPM completed Blocks 1-3 on the real BC-250 with no Block 3 product defect. Device-proven baseline evidence includes guided install/reboot convergence, 40/40 routing/save, healthy status/health/verify, Ollama 0.40.6 lane and registration persistence, Open WebUI 0.12.3 desired-state/idempotence/local-first policy, managed RAG lifecycle, package RAG 3/3, canonical DE↔FR translation 12/12, production use cases 6/6 and raw Advanced `6144 -> options.num_predict=6144`.

Two device-driven package issues are included in 1.5: the pre-convergence status presentation and the guided-installer multiline Ollama version parser. Two earlier test stops were harness defects only (thinking-budget exhaustion and incidental `/api/show` parameter ordering) and must not be encoded as product workarounds.

Block 4 reboot persistence / broader ordinary-user Open WebUI qualification was still pending when 1.5 source scope froze. The 1.4 device PASS set is valuable regression guidance but cannot be transferred to changed 1.5 RPM bytes. See `20_DEVICE_QUALIFICATION_1_4.md` and `21_RELEASE_1_5_SCOPE_AND_ACCEPTANCE.md`.

## Immediate next iteration — authoritative 1.7 build then exact-artifact device testing

The successful 1.4 GitHub build validated the optimized authoritative build path. First run/select the exact 1.7 authority build, then answer:

> Do the exact selected `0.14.1-1.7` bytes preserve the proven stock-core appliance behavior while correctly implementing the carried runtime maintenance and the reviewed managed-RAG integrity/UX corrections?

Use `03_CORE_FUNCTIONALITY_CHECK.md` together with `18_TESTING_SIDECHAT_HANDOVER.md` and `23_RELEASE_1_7_SCOPE_AND_ACCEPTANCE.md`. Focus on carried Ollama/governor surfaces plus the changed RAG lifecycle and reboot/ordinary-user persistence; do not replay already-proven model/tuning campaigns unless a 1.7 observation invalidates them. This is the next **low-cost core functionality** round: changed-surface proof first, then the still-unproven persistence/ordinary-user boundary.

## If the core check passes

Freeze:

- exact RPM filename/NEVRA and SHA-256;
- selected GitHub run identity;
- device/kernel identity;
- short PASS/FAIL evidence for the core smoke.

Then shift directly to the product roadmap: excellent local RAG/document workflows, German–French translation UX and polished ordinary-user assistant operation. Use `08_GREENFIELD_SIMPLIFICATION_PLAN.md` only opportunistically for bounded cleanup that clearly removes concrete ownership or failure risk; cleanup is not a prerequisite phase.

## Bounded simplification target

The next engineering pass should reduce:

- obsolete scripts and dead compatibility paths;
- wrapper chains;
- duplicated state derivation;
- qualification/resilience remnants that are no longer active product needs;
- validation logic that became architecture;
- tests that only preserve implementation detail;
- duplicated docs and handover machinery.

Do not let cleanup become the roadmap. Keep it bounded and stop when the stock baseline is understandable and reliable. Then prioritize office intelligence/product UX rather than starting another infrastructure campaign.

## Deferred until deliberately reopened

- further Ollama/Open WebUI upgrade beyond the 0.40.8/0.12.3 release pins without new evidence;
- context-ceiling changes;
- performance tuning campaigns;
- broad model tournaments;
- experimental GPU/kernel/Mesa work;
- repository signing/SBOM/distribution hardening unless release distribution requires it.
