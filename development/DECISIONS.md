# Durable development decisions

These are development guardrails, not operator procedures. A newer entry may supersede
an older one, but old rationale is retained. Backfilled entries below are grounded in
the package's existing `MODELS.md`, changelog and current implementation; no raw
evidence tarball is invented where it is not present in this source archive.

## DEC-001 — Keep the main GPT-OSS lane warm

**Status:** ACTIVE  
**Decision:** Keep normal main-model residency at 20 minutes rather than unloading
after every request.

**Observed:** Existing BC-250 evidence records roughly 24–25 s GPT-OSS cold load versus
roughly 2–3 s warm response. Making the main lane ephemeral avoided one overlap case
but imposed large-model reload latency on subsequent chat.

**Interpretation:** Normal interactive UX depends on warm-main residency; task-model
selection must fit safely beside that product constraint rather than solving memory
pressure by making every chat cold.

**Retest only if:** the main model/runtime changes enough to materially alter cold-load
latency or a separately justified product policy changes normal residency.

## DEC-002 — Reject Qwen3.8 4B Distill for the normal task role

**Status:** ACTIVE / RETIRED CANDIDATE  
**Exact model:** `exp-qwen38-4b-distill-empero-q6-k`

**Observed:** Focused task quality improved with a larger output budget, but deliberate
simultaneous residency with warm GPT-OSS caused severe memory pressure and the task
service was OOM-killed.

**Decision:** Keep this exact Distill model out of normal discovery and do not promote
it to the normal task lane. This does **not** apply automatically to the separate active
`exp-qwen38-4b-empero-q6-k` general comparison.

**Retest only if:** a materially smaller revision/quant is evaluated, the physical or
runtime memory topology changes materially, or warm-main residency changes for an
independently justified reason.

## DEC-003 — LFM2.5 1.2B Q6_K is the normal task default

**Status:** ACTIVE  
**Exact model:** `task-lfm25-1.2b-instruct-liquidai-q6-k`

**Observed:** The package history records 15/18 direct quality, 15/18 live Open WebUI
quality, and 9/9 deliberate true-overlap trials beside warm GPT-OSS without additional
swap growth or serious OOM/GPU warnings.

**Decision:** Use LFM2.5 1.2B as the dedicated task default; keep Gemma 3 1B as a
fallback/control rather than reverting because of old baseline familiarity.

**Retest only if:** current task quality regresses, Open WebUI changes the task contract,
or a challenger first beats quality and then proves equal-or-better coexistence.

## DEC-004 — Verify core install before optional maintenance/Pi setup

**Status:** ACTIVE  
**Decision:** Full interactive installation runs core appliance verification before
optional maintenance/WOL/Pi/export setup.

**Observed:** Optional maintenance may enable an evening safe-power timer. Enabling that
policy before final installation verification creates an avoidable race between
qualification and power management.

**Retest only if:** the maintenance setup can no longer affect power state before the
installer exits, or installer verification is redesigned with equivalent protection.

## DEC-005 — Use impact-based qualification and temporary specialist lanes

**Status:** ACTIVE

**Decision:** Do not run one giant hardware/quality campaign after every source change.
Use a shared source gate, then qualify only the subsystems affected by the change. Run
full `bc250-revalidate` for meaningful release/milestone qualification or material
runtime/topology changes. Open temporary specialist chats for active quality lanes rather
than maintaining many permanently synchronized specialist handovers.

**Observed:** The project now has independent production roles, a canonical benchmark
result contract, whole-appliance revalidation, Git-only decision memory and several
quality lanes with different acceptance semantics. Older parallel handovers duplicated
current model/package facts and drifted at different rates; documentation/test-only
releases did not create a technical reason to re-run all expensive BC-250 campaigns.

**Interpretation:** Confidence is improved by testing the changed contract deeply, not by
repeating unrelated expensive tests. Shared evidence conventions plus a current
validation matrix preserve cross-lane visibility without copying the whole project state
into every specialist prompt.

**Retest only if:** impact-based qualification misses a cross-lane regression in practice,
or package architecture changes so strongly that most subsystems become coupled again.


## DEC-006 — Strengthen main-model qualification without changing production policy

**Status:** ACTIVE

**Decision:** Keep `prod-gpt-oss20b-ggml-org-mxfp4`, Ollama `0.34.0`, the current
governor/CU policy and current KV defaults while the main-model qualification cycle is
open. Strengthen candidate evidence before considering promotion.

**Required candidate evidence:** backend-aware completion integrity; exact runtime/build
and meaningful flags; KV type; highest-precision feasible KV reference methodology; a
tiny semantic sanity stage; optional 4K/16K context evidence; optional sustained
thermal/CU evidence for finalists; GPU-journal/error capture; gfx1013 runtime-default vs
`n_ubatch=384` comparison when the affected path warrants it; and MTP draft acceptance
evidence when speculative decoding is tested.

**Do not infer yet:** no global KV-default change, no forced F16, no forced 32K tests, no
global `n_ubatch=384`, no governor/CU policy change, no Ollama upgrade and no new main
model promotion without real BC-250 evidence.

**Retest only if:** upstream/runtime changes invalidate one of these gates, or real BC-250
evidence shows that a gate is either insufficient or unnecessarily expensive.

## DEC-007 — Reject Qwen3 4B for the concurrent background-task role

**Status:** ACTIVE / ROLE-SPECIFIC REJECTION  
**Exact model:** `exp-qwen3-4b-lmstudio-q6-k`

**Observed:** Two cheap canonical task screens reached 5/6, making this the strongest
current task-quality challenger. Exact-source task-lane staging then caused global OOM.
A second task-tuned staging attempt bounded to 4096 context and 128 predicted tokens
still caused global OOM during a tiny survival request, killing the warm GPT-OSS main
model and other user services.

**Decision:** Do not spend further qualification time on this model for the concurrent
background-task role on the current 16 GB topology. This is a role-specific rejection;
it does not retire the model from unrelated general/main experiments.

**Retest only if:** the physical/runtime memory envelope changes materially, or a
materially smaller source/quant is being evaluated for the task role.

## DEC-008 — Treat the eight-case DE/FR suite as a translation screening gate

**Status:** ACTIVE

**Observed:** The repaired canonical eight-case German/French screen is saturated:
several materially different candidates reach 8/8. Translate-Gemma E4B and Ministral
both produced 24/24 confirmation evidence; TIR Qwen3.5 9B reached 8/8 when tested with
an explicit non-thinking request contract. Production LFM reproduced known weaknesses
at 6/8. Large 27B/35B models can also reach 8/8 while leaving impractically little
memory headroom.

**Decision:** An 8/8 result means "advance to harder discrimination", not promotion or
model equality. Do not repeat the same canonical screen merely to rank models already
known to saturate it. The next translation decision gate is the harder Stage-2 corpus,
followed by the real authenticated Open WebUI product path for the narrowed finalists.

**Current Stage-2 set:** Translate-Gemma E4B, Ministral 8B, TIR Qwen3.5 9B non-thinking,
and Qwen3.6 35B only as a quality upper-bound comparator.

**Retest only if:** the canonical fixture/evaluator or the tested model definition/request
contract changes materially enough that the earlier screen is no longer comparable.

## DEC-009 — Select Translate-Gemma E4B for bounded translation integration

**Status:** SUPERSEDED BY DEC-010 — historical pre-promotion decision
**Exact model:** `exp-translate-gemma4-sub-e4b-17s-q4-k-xl`

**Observed:** Stage-2E on the authenticated Open WebUI product path compared seven
configurations against the hard DE↔FR corpus. The strongest deployment configuration
was Translate-Gemma with the exact explicit-direction v1 system contract, direction in
the user wrapper, thinking policy omitted and `max_tokens=2048`. It reached 10/16 hard
passes (2/8 DE→FR, 8/8 FR→DE), 16/16 target-language checks and 72/78 advisory semantic
dimensions, with 6.91 s mean wall time, 23.01 s p95 and 8362 MiB minimum MemAvailable.
The 1024-token configuration truncated the long FR→DE case at exactly 1024 output
tokens; the 2048-token configuration completed it at 1376 output tokens.

TIR Qwen3.5 9B also reached 10/16 but only 65/78 semantic dimensions, produced different
outputs on every repeated case, averaged 10.60 s and fell to 5871 MiB minimum
MemAvailable. Forcing `think:false` on Translate-Gemma reproducibly broke the focused
FR→DE `Avoir` case and is therefore rejected for this role.

**Decision at the time of Stage-2E:** Stop broad translation-model comparison. Integrate
Translate-Gemma as two explicit-direction package-owned roles using the exact Stage-2E
system prompt, no forced thinking policy, `max_tokens=2048`, and direction only through
the exact tested user wrapper. The maintainer subsequently accepted the production
identity switch in DEC-010 before post-install package verification. This record remains
the evidence boundary for how the model/configuration was selected; it is not the current
production-state decision.

**Known caveats:** Translate-Gemma still localizes protected DE→FR financial typography,
omits the trailing ordinary-language sentence in one targeted bullet case, and renders
the focused `Avoir AV-19` concept as `AV-19:` rather than an explicit accounting term.
The package does not claim byte-for-byte protected-literal preservation. Numeric
comparison must nevertheless treat locale-equivalent one-decimal forms such as `8.1`
and `8,1` as the same value.

**TIR retest only if:** the integrated Translate-Gemma path cannot meet the required
product contract for a model-level reason, or a materially different TIR model/runtime
becomes available.

**Evidence:** `bc250-translation-stage2e-config-bundle-20260917-232916.tar.gz`,
SHA-256 `63fa90ea1187b7c878da0067d3f0be91e5a9e9faadbb4c919c7ed2a374f80c1c`.

## DEC-010 — Normalize task/translation production identities for 0.11.2-0.2+

**Status:** ACCEPTED — source policy; installed-device verification still required.

**Context:** The task lane has one proven deployable model, LFM2.5 1.2B. The older
Gemma 3 1B fallback/control remains materially weaker. Stage-2E selected Translate-Gemma
E4B and closed the broad translation tournament, while the old LFM production translator
is useful only as a rollback/reference. Keeping all of those identities simultaneously
in active task/production discovery obscures the actual appliance defaults.

**Decision:**

- keep `task-lfm25-1.2b-instruct-liquidai-q6-k` as the sole active task-lane model;
- retire `task-gemma3-1b-unsloth-ud-q4-k-xl` to the source graveyard;
- promote the selected translation weights as
  `prod-translate-gemma4-sub-e4b-17s-q4-k-xl`;
- make the explicit `bc250-office-translation-de-fr` and
  `bc250-office-translation-fr-de` presets the active production translation roles;
- retire the old `prod-lfm25-8b-a1b-liquidai-q6-k` identity and retain the same LFM
  family only as `exp-lfm25-8b-a1b-liquidai-q6-k` for deliberate rollback/comparison;
- retire Hunyuan-MT and Ministral translation-only challengers and the old experimental
  Translate-Gemma alias from routine discovery;
- keep TIR Qwen3.5 9B experimental because it still has a broader office/RAG comparison
  purpose independent of its closed translation deployment path.

**Boundary:** This is a source/catalog promotion based on the accepted Stage-2E evidence
and maintainer decision. It does not claim that the newly named production identity has
already passed the post-install current-release real-device gate. That verification remains
required before calling the new release fully qualified on the appliance.

**Retest only if:** a retired model gains a materially new role, runtime/hardware envelope,
or evidence that directly addresses its recorded rejection/supersession reason.

## DEC-011 — Fail closed on coding-helper completion integrity

**Status:** ACTIVE

**Decision:** `bc250-code` must keep native model reasoning separate from the final
product output. The package uses Ollama `/api/chat` with `think:true`, consumes only
terminal non-empty `message.content`, rejects `done_reason=length` and literal reasoning
markers in final content, and must not replace an existing destination file unless all of
those checks pass. Output replacement remains atomic.

The package default request budget remains 3072 tokens. A larger default is not adopted
merely because one workflow truncated; use `CODING_AGENT_NUM_PREDICT` for bounded
real-device A/B evidence first. Static agent evaluation likewise treats reasoning leakage
as a format failure and must not weaken syntax/requirement checks to hide model misses.

**Why:** real product-path evidence showed that useful final code could be preceded by
reasoning, and that some responses could exhaust the output budget before a complete final
answer. Writing either form directly into a target file violates the coding-helper product
contract even when the underlying model is otherwise capable.

**Retest only if:** Ollama changes the chat completion/thinking contract, the default agent
model changes materially, or bounded BC-250 evidence supports changing the default output
budget.
