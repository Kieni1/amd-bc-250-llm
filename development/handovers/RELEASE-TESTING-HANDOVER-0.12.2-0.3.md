# BC-250 0.12.2-0.3 release testing handover

## Scope

Build and test the exact `bc250-llm-server-0.12.2-0.3` candidate. This is a new functional/runtime
candidate, not a narrow replay of 0.12.1-0.6. Source-side changes were intentionally made directly
from the previous device evidence; model/runtime acceptance belongs to this new installed build.

Target identity:

```text
VERSION        0.12.2
RPM Release    0.3
NVR            bc250-llm-server-0.12.2-0.3
Ollama         0.34.4
Open WebUI     0.11.4
Tika           4.0.0-full / TIKA_SERVER_VERSION=4
Governor       0.4.13
Revalidation   v4.6
```

Do not relabel 0.12.1-0.6 device evidence as 0.12.2 qualification. Use it as the comparison baseline.

0.12.2-0.3 closes the remaining pre-device logic review: complete French modality conjugations,
clause-local modality association, conservative handling of ambiguous single-separator three-decimal
numbers, one production translation prompt/wrapper/literal-integrity authority across direct and OWUI
qualification, neutral integrity-withholding UX, fail-closed `ordinary_user_visible` typing, and an RPM
`%pre` runtime/boot hold before the new OWUI Quadlet can become restart-eligible. ACL/xattr-preserving
migration rollback archives and the documented restore path remain mandatory. Include focused checks
of those repaired boundaries in the source/build evidence.

## Candidate decisions to qualify

1. Advanced/Qwen3.5 uses request-scoped `think=true` for this candidate, with the existing sampler
   policy retained.
2. Qwen3.6 35B and Qwen3.8 27B Unsloth large experimental profiles use 8K context instead of 16K.
3. Qwen3.8 ISTA IQ3_S remains the 8K quality profile; IQ3_XXS remains the 8K deployability profile.
4. Translation prompts/wrappers explicitly protect recommendation versus obligation semantics.
5. Open WebUI upgrades are migration-gated by a verified stopped-state full rollback snapshot.
6. Ollama/Open WebUI/governor pins move to 0.34.4/0.11.4/0.4.13 respectively.
7. Tika 4 behavior is explicit and must be proven with meaningful Markdown structure.
8. Independent read-only Ollama inventory probes may run concurrently; all mutation/topology work
   stays serial.
9. Gemma4 26B and the LFM 8B comparison translator are retired from active discovery after corrected
   long-run quality evidence; do not reinstall them merely to replay the campaign.
10. Qwen3.6 35B, Qwen3.8 27B Unsloth and ISTA IQ3_S are admin/testing-only OWUI surfaces; IQ3_XXS
    remains the ordinary-user 27B deployability comparison.

## Phase 0 — build/source identity

Before device work record:

- source ZIP SHA-256;
- RPM and SRPM SHA-256;
- exact installed NEVRA;
- `rpm -V` baseline;
- boot ID, kernel, Mesa/Vulkan packages;
- package runtime metadata and installed governor revision.

The source/build gate and device gate are separate. Do not substitute one for the other.

## Phase 1 — Open WebUI migration/rollback safety

Exercise a real upgrade from an existing 0.12.1-0.6 OWUI state where practical.

Acceptance sequence:

```text
install new RPM
-> RPM %pre stops any active OWUI service before the new Quadlet payload / daemon-reload can make it restart-eligible
-> existing OWUI boot enablement is removed and remains held
-> bc250-install confirms the stopped state before migration
-> SQLite integrity check passes
-> full /var/lib/open-webui rollback archive is produced with ACL/xattr/numeric-owner preservation
-> archive member/path validation passes
-> SHA-256 sidecar verifies
-> boot enablement is restored only after backup success
-> OWUI 0.11.4 starts/migrates
-> HTTP readiness returns
-> package desired state converges
-> authenticated verifier/status are clean
```

Record the rollback archive name and SHA-256. Confirm it contains database plus representative
package-owned persistent subtrees, not only `webui.db`. A failed backup must leave the new OWUI image
unstarted, the service stopped and package boot enablement held.

Do not prove rollback by intentionally corrupting production state. If restoration is exercised, use
a controlled copy/snapshot and verify the pre-upgrade state can be recovered.

## Phase 2 — runtime/topology regression

Confirm normal topology:

```text
11434 main       Ollama 0.34.4
11435 task       Ollama 0.34.4
11437 embedding  Ollama 0.34.4
11436 agent      inactive in normal mode
Open WebUI       0.11.4
Tika             4.0.0-full
```

Retain `OLLAMA_MAX_LOADED_MODELS=1` and serial large-model behavior. Run a focused Vulkan/UMA
regression covering Standard, Advanced, Deep, embedding, model switching, Deep unload -> task
cold-load and Advanced+Deep compare. Capture MemAvailable, swap/zram/PSI and kernel/AMDGPU/Vulkan
fault evidence. No broad tournament is required.

Record `/api/show` metadata for production models, including `thinking` when present. Interpretation
priority is package policy -> Ollama `thinking` metadata -> known-model fallback -> capabilities.
Missing thinking metadata is diagnostic only; it must not become an automatic non-reasoning verdict.

## Phase 3 — complete Open WebUI stored-contract audit

For every package-owned curated workspace/derived preset verify the stored record against source:

- preset/model ID;
- expected `base_model_id`;
- complete package-owned `params`;
- `custom_params`;
- relevant `meta`;
- filter/function attachment;
- knowledge/retrieval attachment where applicable;
- active/hidden state;
- minimum-required access grants while preserving unrelated grants.

Terminology:

```text
workspace/derived record       base_model_id != null
direct/base-model override     base_model_id == null
```

Do not use “curated preset” as a synonym for every upstream workspace/derived record.

## Phase 4 — intended OWUI config -> effective Ollama request

For production settings that matter, prove three stages separately:

1. stored OWUI record;
2. OWUI merge/adapter result;
3. effective outbound Ollama request/runtime behavior.

At minimum capture Advanced and Deep. Advanced must show root `think=true` for this candidate and
samplers under Ollama `options`:

```text
temperature=0.7
top_p=0.8
top_k=20
min_p=0
presence_penalty=0
repeat_penalty=1
```

Deep must prove effective `keep_alive=0`. Include `num_predict` or other caller-owned controls where
the preset/path defines them. Never infer the effective sampler from answer quality.

## Phase 5 — canonical browser journey / reasoning persistence / tasks

Capture one real supported browser request sequence from Open WebUI 0.11.4 and use it as the
canonical journey contract. Record the exact shape for chat creation, message tree, `chat_id`,
`parent_id`, message IDs, top-level messages, `user_message`, streaming, `message_ids`, file
references, background-task fields and a multi-turn continuation.

If a direct API harness differs from the browser sequence, classify that as a harness/contract
question before blaming model history/completion behavior.

For Deep/reasoning models verify both live and reloaded-chat behavior:

- final visible content has no raw reasoning leakage;
- reasoning is available where OWUI expects it;
- persisted reasoning/output survives completion and reload;
- structured response/output fields are interpreted before legacy `<details type="reasoning">` fallback.

For title/tag/follow-up qualification, explicitly establish and record enabled state for the test
identity. Verify persisted title/tags/follow-ups when enabled. Mark disabled functions `NOT_COVERED`,
not PASS. This must genuinely exercise the task lane.

## Phase 6 — production role quality

### Standard / Documents

Repeat compact product-faithful probes only. Ensure the OWUI 0.11.4/Tika change has not regressed
normal office or RAG behavior.

### Translation DE -> FR and FR -> DE

Test recommendation, obligation, permission, prohibition/negation, date, CHF amount and stable
identifier. Required semantic examples include:

```text
sollte  -> devrait   (not doit)
devrait -> sollte    (not muss)
muss/doit remain obligations
```

Correct locale-equivalent unambiguous CHF/date formatting is not a semantic failure. Explicitly verify that ambiguous `1,234` / `1.234` percentage and currency forms cannot collapse to `1234`, and that two adjacent modal clauses cannot swap recommendation/obligation or permission/obligation without being withheld. If the underlying model
still strengthens modality, record a translation quality defect even if the package filter correctly
withholds the bad output. Verify the benchmark reports this as `modality`, not `source-leakage`.

### Advanced

The candidate default is `think=true`. Use deterministic arithmetic, constraints, structured
extraction, history and visible-answer probes plus latency/memory. Run a small `think=false`
reference on the same probes if needed for the release decision. The result should decide whether
`think=true` stays, `think=false` returns, or sampler/model policy needs another candidate. Do not
change the default mid-run without recording it.

### Deep

Repeat normal chat plus the Advanced+Deep compare flow. Verify completion, visible output, reasoning
persistence, `keep_alive=0` automatic unload and subsequent task-lane cold-load.

## Phase 7 — Tika 4 / Documents structure

Use a representative document containing at least:

- a heading;
- a list;
- a table;
- a unique retrieval marker.

Prove that OWUI 0.11.4 with `TIKA_SERVER_VERSION=4` extracts meaningful Markdown structure into the
indexed content and that Documents retrieves the marker/content. “Upload succeeded” alone is not
acceptance.

## Phase 8 — large experimental memory profiles

### Qwen3.6 35B

Test the new 8K profile. Compare its quality with the prior 16K evidence and require materially
better headroom. If it still repeatedly falls below roughly 512 MiB, prefer a smaller quant/model
rather than adding a generic scheduler.

### Qwen3.8 27B Unsloth

Test the new 8K profile under its intended quality role. Retain it only if headroom materially
improves without materially harming that role.

### ISTA profiles

Keep separate conclusions:

- IQ3_S = experimental quality profile;
- IQ3_XXS = experimental deployability/lower-pressure profile.

Do not collapse them into one winner by default.

Classify memory results explicitly as:

1. leak/unload failure;
2. successful but excessively tight profile;
3. comfortable profile.

Residual zram/swap after a successful unload is not itself a model-memory leak. Repeated automatic
recovery after sub-512 MiB operation is still evidence of an overly aggressive routine profile.

## Phase 9 — role-aware specialized models

Use package `model-profiles.json` to choose probes. Do not reject a translation or OCR implementation
because it performs poorly on an irrelevant generic-office prompt.

OCR models require a dedicated image/document OCR path. Registration/load success is not OCR
qualification. General text-only journeys should report specialized/not-applicable for OCR rather
than PASS/FAIL.

During this pre-v1 test candidate, raw production/task models and ordinary-size experiments remain
ordinary-user comparison surfaces. Verify that Qwen3.6 35B, Qwen3.8 27B Unsloth and ISTA IQ3_S are
not selectable by the temporary ordinary user, while IQ3_XXS remains visible as the lower-pressure
deployability comparison. Admin/native testing must still be able to exercise the hidden profiles.

## Phase 10 — factual calibration and scoring taxonomy

Add a finite-set factual-calibration case with objectively valid/invalid choices and explicit
abstention when uncertain. Use that for deterministic qualification. Keep open-ended Swiss-person
or similar prompts as manual review only.

Report separately:

- semantic/model-quality defect;
- exact-format/instruction-compliance review;
- output/reasoning budget exhaustion;
- no-visible-answer behavior;
- output repetition/degeneration;
- reasoning-loop review;
- manual factual review.

Do not inflate semantic defect counts for localization typography, Markdown emphasis, Unicode
space/hyphen variants, capitalization or physical-line layout. Keep output-loop and reasoning-loop
aggregates separate, and do not call a repetition loop ordinary token-budget exhaustion merely because
it ends at the limit.

## Phase 11 — Ollama 0.34.4 targeted regressions

- Re-run structured JSON/output probes on reasoning models; semantics remain the gate, while latency
  and reasoning-token behavior are observations rather than fixed old performance contracts.
- With a large installed model inventory, repeatedly `/api/show` canonical IDs distributed across the
  library. Generate only with a small representative subset, serially. The purpose is lookup
  reliability, not a load test.
- Capture the new `thinking` metadata where available without treating absence as failure.

## Phase 12 — ordinary-user ACL and compare

Create a temporary real `role=user` identity. Verify:

- all curated roles visible;
- raw production/task and ordinary-size testing surfaces visible;
- Qwen3.6 35B, Qwen3.8 27B Unsloth and ISTA IQ3_S absent from the ordinary-user selector;
- ISTA IQ3_XXS visible as the ordinary-user deployability comparison;
- embedding and agent models absent from normal selector;
- RAG/file access works as intended;
- `chat.multiple_models` effective state is recorded but remains administrator-owned;
- unrelated administrator access grants survive desired-state convergence.

Delete the temporary user, restore user count and prove temporary credentials are absent from the
evidence archive.

## Phase 13 — final restoration and release decision

Required final state:

```text
normal topology
agent intentionally inactive
Open WebUI ready
failed units = 0
no fresh OOM-killer event
no critical AMDGPU reset/device-loss/VM-fault event
main/task/embed residency restored (prefer empty if the run started empty)
Deep unloaded
rpm -V clean
authenticated verifier clean
boot ID stable unless a deliberate reboot phase was recorded
```

A product mismatch is evidence; continue independent safe observations. Stop only the unsafe or
dependent subtest whose prerequisite is not satisfied. Reserve a nonzero overall harness exit for an
unsafe final appliance state or a mechanical harness failure that invalidates the run.

Return to main integration with separate `PRODUCT_DEFECT`, `UX_DEFECT`, `HARNESS_DEFECT`,
`ENVIRONMENT`, `EVIDENCE_GAP` and clean observations. Include the final device evidence archive
SHA-256 and internal checksum-verification result.

## Policies not reopened by this candidate

Do not add a generic memory scheduler, pre-emptively disable multi-model chat, repack embedded Qwen
templates, alter the four-lane topology, remove Deep `keep_alive=0`, or switch to ROCm merely because
upstream versions changed. Any such change requires new evidence from this candidate.
