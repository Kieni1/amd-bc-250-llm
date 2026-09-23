# BC-250 0.12.1-0.5 non-RAG release testing handover

## Scope

This is a narrow repair release after exact-installed 0.12.1-0.4 was runtime-clean but release-blocked by RAG preparation contamination and a broken `bc250-revalidate status --raw` CLI contract.

Do not rerun the completed broad 0.4 model/revalidation campaign unless one of these fixes unexpectedly changes runtime behavior.

## Candidate

```text
VERSION       0.12.1
RPM Release   0.5
NVR target    bc250-llm-server-0.12.1-0.5
Ollama        0.34.2
OWUI          0.11.3
```

## Revalidation raw-status repair

0.4 proved the actual packaged revalidation run healthy:

```text
harness 4.3
infrastructure PASS
quality 8/8
restoration PASS
coverage FULL
bundle manifest/checksums PASS
```

The product defect was only argument forwarding: `bc250-revalidate status --raw` returned the same human output as ordinary `status`.

0.5 identifies the command as harness v4.4 and must satisfy:

```bash
sudo bc250-revalidate status
sudo bc250-revalidate status --raw
```

The first is human-formatted. The second must be machine-readable `key=value` output containing the documented state keys, including at least harness/run/version/state/infrastructure/quality/restoration/coverage/bundle information.

Do not rerun the full ~14-minute model qualification merely because the status dispatcher changed.

## 40-CU / installer UX

The proven live state remains authoritative. No 40-CU runtime policy changes in 0.5.

On a healthy live-manager system, installer completion should foreground something equivalent to:

```text
40-CU live routing: 40/40 healthy (live manager enabled/active)
Persistent boot module: disabled (optional; not required for healthy live routing)
```

During preparation, disabled persistence must be neutral state, not a call to action:

```text
Persistent boot activation: disabled (optional).
Live CU routing is managed independently by bc250-cu-live-manager.
```

The CU dashboard must label the kernel `active_cu_number` as a diagnostic/non-authoritative counter and keep the SPI/live-routing result as operational authority.

Do not alter the working live-CU policy just to satisfy wording.

## Installer kernel-plan UX

Before Fedora update evaluation, the setup plan must not simply say `kernel current`.

It should state the running kernel and that repository check/update happens in step 2. If a newer already-installed kernel is pending, report that explicitly.

No historical kernel-version blacklist is to be reintroduced.

## GPT-OSS factual-quality smoke

0.5 changes only the Deep model system instruction. Sampling, `num_ctx=16384`, `num_keep=256`, full GPU offload, model artifact, Open WebUI role and `keep_alive=0` are unchanged.

The prompt now instructs the model that factual accuracy outranks filling a requested list/count. Run one bounded factual-list question where the model may not know enough entries.

Acceptance criterion is behavioral, not exact wording: it should prefer fewer credible items / explicit uncertainty over placeholder initials or plausible invented names when recall is weak.

This is a smoke, not a new broad general-quality tournament. If the behavior remains poor, return evidence to main integration rather than retuning sampling in this release.

## Open WebUI role/tool-policy and model-visibility acceptance

The final 0.5 candidate incorporates direct browser findings from Standard, Advanced, Deep and Translation. This is a product-policy change inside Open WebUI desired state, not a runtime/model-artifact change.

Verify with an ordinary authenticated user:

```text
Standard: ordinary general-knowledge question is answered from model knowledge without automatically querying knowledge files/chats.
Advanced: same general-knowledge behavior; no automatic KB/chat-history search merely because the model is tool-capable.
Deep: factual-list smoke prefers fewer credible entries/uncertainty over fabricated names; no automatic KB requirement.
Documents: knowledge retrieval remains available and is the dedicated RAG role.
Translation DE→FR and FR→DE: no autonomous built-in tools; preserve legal modality (e.g. sollte ≠ doit/muss) while retaining structure/numbers.
Explicit "do not use RAG/documents" on a general role: no knowledge-file retrieval for that turn.
```

Testing visibility is intentional. Main `11434` and task `11435` provider allowlists are empty/unrestricted, so every model installed on those normal lanes should be selectable in Open WebUI. Package-owned raw production/task overrides must be visible and labelled as testing surfaces. Experimental models installed on 11434 should also appear without editing provider allowlists. Embedding `11437` and exclusive agent `11436` remain outside the normal chat selector. Raw GPT-OSS must retain `keep_alive=0`.

Do not interpret raw-model visibility as v1 product policy; it is deliberate pre-v1 comparison behavior.

## Package/final-state compact gate

After installing 0.5:

```text
rpm -V clean
normal main/task/embedding topology
agent intentionally inactive
all normal Ollama lanes 0.34.2
OWUI ready
TTM 4194304/4194304
live CU routing healthy
no failed units
no fresh OOM/AMDGPU/Vulkan/kernel-critical evidence
unintended model residency empty at final state
authenticated verifier clean
```

A full package revalidation is optional for this narrow repair unless source/device evidence indicates a crossed runtime boundary.

## Acceptance-harness policy

Do not terminate evidence collection merely because an expected product value mismatches reality. Record mismatches and continue independent checks.

Use distinct concepts equivalent to:

```text
execution      EXECUTED | SKIPPED_SAFETY | SKIPPED_PREREQ | HARNESS_ERROR
observation    MATCH | MISMATCH | EXPECTED_REFUSAL | ERROR | REVIEW
classification PRODUCT_DEFECT | SAFETY_DEFECT | UX_DEFECT | ENVIRONMENT |
               EXPECTED_BEHAVIOR | EVIDENCE_GAP | HARNESS_DEFECT | CLEAN
```

A destructive/resource-sensitive subtest may skip itself if its own safety prerequisite fails. Package evidence regardless. Overall nonzero harness exit is for unsafe final appliance state or a mechanical harness error that invalidates the evidence run, not an ordinary product mismatch.

Also do not label a result `UX PASS` merely because expected strings were present. Record mechanical field/string presence separately from human operator UX judgment.

## Required handoff

```text
RELEASE 0.12.1-0.5 -> MAIN INTEGRATION
installed NEVRA:
status human result:
status --raw result:
installer kernel-plan result:
40-CU wording/state result:
general-role tool-routing smoke:
translation modality smoke:
main/task model visibility:
GPT-OSS factual smoke:
package integrity/verifier:
resource/kernel result:
final topology/residency:
operator UX review:
source defects found:
evidence archive + SHA-256:
```
