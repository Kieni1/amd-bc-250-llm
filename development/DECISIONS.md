# Durable development decisions

These are development guardrails, not operator procedures. A newer entry may supersede
an older one, but old rationale is retained. Backfilled entries below are grounded in
the package's existing `MODELS.md`, changelog and current implementation; no raw
evidence tarball is invented where it is not present in this source archive.

## DEC-001 — Keep the interactive main lane warm

**Status:** ACTIVE  
**Decision:** Keep normal main-lane residency at 20 minutes rather than unloading
after every request. The lane is a shared product-role lane, not a permanently warm
GPT-OSS lane; whichever production model was used most recently remains resident under
Ollama's normal single-model keep-alive policy.

**Observed:** Historical GPT-OSS evidence records roughly 24–25 s cold load versus
roughly 2–3 s warm response. Making the main lane ephemeral avoided one overlap case
but imposed large-model reload latency on subsequent chat. Maintenance warm-up now
defaults to the routine-office Gemma E2B model, while GPT-OSS remains the deep-reasoning
and worst-case production memory reference.

**Interpretation:** Normal interactive UX depends on warm main-lane residency; task-model
selection must fit safely beside the worst credible warm production model rather than
solving memory pressure by making every chat cold.

**Retest only if:** main-lane model/runtime behavior changes enough to materially alter
cold-load latency or a separately justified product policy changes normal residency.

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

## DEC-004 — Verify core install before optional maintenance and companion setup

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


## DEC-012 — Make model lifecycle state explicit in the public CLI

**Status:** ACTIVE

**Decision:** Treat model management as three explicit states—catalog definition, manager-owned
source/provenance, and Ollama registration—and expose lifecycle verbs that match those states:
`list`, `status`, `path`, `apply`, `refresh`, `unregister`, `remove`, and `purge-retired`.
Do not preserve the pre-0.11.3 `install`/`cleanup`/`resolve` grammar as aliases; legacy forms
produce migration hints instead.

`apply` converges to the current catalog while reusing verified source bytes; `refresh`
explicitly re-fetches source; `unregister` retains verified GGUF/state; `remove` also removes
manager-owned source/state. `status` and `apply` consume the same read-only inspection model so
currentness is not inferred independently by multiple callers.

**Why:** the old interface hid materially different operations behind `install --refresh` and
`cleanup --keep-gguf`, made reinstall/update/drift handling unclear to operators, and encouraged
callers to reason about state separately. The package is pre-v1.0 and intentionally chose a
clean contract over compatibility aliases.

**Retest only if:** real operator use shows the new verbs remain ambiguous, a lifecycle operation
cannot be represented without unsafe flag combinations, or a future package state model changes
materially. Do not restore old aliases merely to avoid updating callers/docs.

## DEC-013 — Keep task-tag JSON strict; fix repeated double-object output in the prompt

**Status:** ACTIVE

**Decision:** Keep the existing strict task evaluator and 128-token tag budget. The
package-owned tag-generation prompt must explicitly place broad themes and specific
subtopics together in one `tags` array and require exactly one raw JSON object with no
second object, prose or Markdown.

**Why:** Installed 0.11.2-0.5 and 0.11.3-0.2 both produced the same `tags-de` failure:
the model emitted two individually sensible JSON objects, apparently separating broad
and specific tags. The evaluator correctly rejects that product output. Reclassifying or
loosening the evaluator would hide a real format-contract defect; clarifying the prompt
addresses the demonstrated ambiguity while preserving the acceptance contract.

**Retest only if:** the focused six-case task qualification still shows repeated structural
failure after the 0.11.3-0.3 prompt, Open WebUI changes its task prompt/template contract,
or the production task model changes. Do not increase the budget or relax single-object
JSON merely to make the current model pass.


## DEC-014 — Measure MTP against the same target/runtime and keep the external server unprivileged

**Status:** ACTIVE — source contract; Phase-1 qualification and corrected Phase-2 optimization evidence recorded.

**Decision:** The first MTP qualification campaign compares each selected target GGUF with
the same llama.cpp build, context/cache/ubatch/request settings twice: speculative decoding
disabled, then `draft-mtp` enabled. An unrelated Ollama model is not a valid speedup baseline.
The runner verifies manager-owned source state/SHA, port/process/memory/runtime prerequisites,
and launches the external `llama-server` as the `ollama` service user rather than root.
Qualification evidence must include draft accepted/proposed counts, completion integrity,
throughput, MemAvailable/swap, exact model/runtime identity and severe GPU/kernel faults.
Missing draft-acceptance telemetry is an incomplete MTP qualification, not a silent pass.

The bounded first-campaign set is Qwen3.5 9B, retained Qwen3.6 27B control, HauhauCS
Qwen3.8 27B IQ2_M and Qwen3.6 35B-A3B. All remain disabled/download-only and outside
generic convergence.

**Current evidence note:** That list describes the original campaign design. The 35B stock configuration
subsequently failed baseline memory fit and is retired; YMQ XS-TI was added later and independently
qualified. Corrected Phase-2 testing is complete enough to keep current package defaults unchanged,
with only Qwen3.5 depth 2 remaining as an optional confirmation target. See DEC-021 and
`development/model-runs/2026-09-19-mtp-final-qualification.md`.

**Why:** The pre-hardware helper compared an MTP server to an unrelated Ollama baseline,
which could not isolate speculative-decoding speedup, and it lacked one evidence bundle for
resource/runtime/fault analysis. Manager-owned GGUF permissions also made direct ordinary-user
launch ambiguous. The 0.11.3-0.4 lane resolves those measurement/privilege defects before the
first real campaign without turning MTP into a production dependency.

**Retest only if:** real BC-250 evidence shows a concrete runner/comparison defect, llama.cpp
changes the MTP telemetry/CLI contract, or a candidate requires a materially different runtime
path. Do not keep polishing the framework without hardware evidence.

## DEC-015 — Keep install-time model reconciliation fast, bounded and MTP-safe

**Status:** ACTIVE

**Decision:** `bc250-install` may use the shared model-state inspector to render its optional
ordinary-model picker, but install-time state discovery must not turn into an unbounded runtime
probe or an accidental MTP acquisition path. Generic combined `apply all` / `refresh all`
therefore never select the MTP category; disabled MTP preparation remains explicit through
`bc250-fetch-mtp` / `bc250-model apply mtp ... --include-disabled`. The known-inactive agent
Ollama lane is skipped during registration discovery, and remaining local registration probes
have a short timeout rather than being allowed to stall setup indefinitely. GGUF integrity is
unchanged: matching schema-3 file identity may use the recorded verified SHA fast path, while
changed/legacy identity still forces a full checksum. Required models that are fully unchanged
may be summarized by category, but any actual download, source metadata/permission repair,
Modelfile drift or registration repair must remain visible.

**Why:** Installed pre-refinement `0.11.3-0.4.fc44` showed correct model state and a clean
54/0/0 verifier, but the optional picker took noticeably long to appear and the initial required
convergence printed a redundant catalog/current-model stream. The same run also demonstrated that
showing disabled MTP indexes inside the generic installer picker creates an unnecessary path for
operator ambiguity even though MTP is a separate experimental llama.cpp lane. These are UX/runtime
probe issues, not reasons to weaken source verification.

**Retest only if:** a bounded active-lane registration timeout causes false UNKNOWN states on a
healthy BC-250, a future topology changes which Ollama lanes are intentionally inactive during
normal setup, or the package deliberately changes MTP from an explicit experiment into normal
appliance convergence. Do not speed setup by skipping checksum validation when recorded file
identity has changed.

## DEC-016 — Keep installer maintenance and companion choices independent and surface marginal PASS evidence

**Status:** ACTIVE — carried forward in 0.11.3-1.7.

**Decision:** The guided full installer must finish core appliance verification before any
optional maintenance or Raspberry Pi work, then present local BC-250 maintenance and Pi/companion
integration as separate choices. Local maintenance can be configured independently; both choices remain optional/default-No, and existing local maintenance may be left unchanged explicitly. Selected optional setup is checked
for its relevant protected configuration/timer/SSH/account/export invariants before the installer
reports success. The completion footer stays concise: one block each for validation/benchmark,
models/runtime lanes and further setup, followed by the installed documentation root and the
important configuration/state/evidence/log paths.

Whole-appliance revalidation keeps its existing acceptance policy. A minimum MemAvailable below
512 MiB but still above the unchanged 128 MiB hard floor is an informational tight-headroom
diagnostic, not a failure. Likewise, a use-case answer that satisfies its acceptance contract but
ends at its output budget remains PASS while being surfaced under `Diagnostics`.

**Why:** Exact installed 0.11.3-0.4 showed that the appliance can be fully healthy while the
installer still asks too many optional questions after the operator has no interest in maintenance
or a Pi. The same revalidation passed 8/8 but exposed two useful marginal facts only in deep
evidence: GPT-OSS/Jina reached 193.36 MiB minimum MemAvailable, and `office-draft-e2b` passed
semantic acceptance with `output-budget`. Hiding those facts makes a green summary look roomier
than the evidence actually is; turning them into failures would instead change policy without a
quality/safety basis.

**Retest only if:** real operators find the new top-level gate hides a necessary fresh-install
choice, selected optional setup can pass the post-check while remaining unusable, or repeated
BC-250 evidence shows the 512 MiB visibility threshold should become an actual qualification
limit. Do not move the 128 MiB hard floor or convert accepted output-budget events into failures
without new evidence and an explicit policy decision.

## DEC-017 — Keep RAG qualification deterministic and dimension-separated

**Status:** ACTIVE — introduced in 0.11.3-1.1 source and carried forward.

**Decision:** Direct `rag-quality` qualification must remain deterministic and reviewable.
Acceptance terms use normalized token boundaries so shorter dates, numbers, identifiers or
currency fragments cannot collide inside larger correct values. Equivalent wording belongs in
explicit fixture metadata (`required_any`, `required_any_groups`, case-scoped `numeric_values`)
rather than fuzzy matching or an LLM judge.

RAG evidence keeps target retrieval, all-required-source retrieval, fact/abstention, language
and citation as independent checks. Language evaluation may report `not-measurable` for short
numeric/identifier-dominated answers; that state may be non-failing but must not be presented as
a positive language match. Canonical RAG summaries also validate the expected case-ID set exactly
once, with structural completeness separate from semantic quality and infrastructure health.

The Open WebUI product-path qualifier must resolve the live model surface before creating
temporary benchmark state. An exact active preset ID is authoritative; a raw Ollama base model
may be mapped only when one active preset matches it. Ambiguous/unknown mappings fail early with
actionable preset IDs. Benchmark evidence retains only the sanitized active
`preset_id -> base_model` mapping, not the raw authenticated model-export response. Open WebUI
readiness is HTTP-based rather than inferred from systemd state.

**Why:** The broader RAG campaign exposed scorer false negatives where `9 November` matched inside
`19 November`, `7 March 2028` inside `17 March 2028`, concise English technical answers lacked
stopwords, and semantically equivalent office wording was rejected. Those are evaluator defects,
not model-quality findings. A deterministic explicit schema fixes the defects without weakening the
quality bar or making benchmark results depend on another model.

**Retest only if:** a demonstrated false positive/negative survives the explicit fixture contract,
new multilingual cases show deterministic language evidence is systematically insufficient, or a
new RAG case type requires an additional independently meaningful scoring dimension. Do not add
fuzzy scoring merely to improve model pass rates.


## DEC-018 — Restore benchmark residency and report resident-session resources

**Status:** ACTIVE — introduced in 0.11.3-1.3 source.

**Decision:** Direct `rag-quality` may isolate the answer and embedding lanes for deterministic
measurement, but it must not leave the appliance in a different Ollama residency state. The
benchmark snapshots the normalized `/api/ps` residency sets before destructive isolation, restores
the same model sets on every exit path, verifies the result, and treats restoration failure as an
infrastructure failure. Reload requests intentionally omit an explicit `keep_alive` so each Ollama
service applies its configured/default lane policy; exact remaining expiry time is not reconstructed. The shared Ollama client owns this lifecycle helper so benchmark callers do
not grow separate unload/reload implementations. Embedding-only registrations are restored through
`/api/embed` when a generation load request is not valid for that model.

RAG resource reporting uses the existing telemetry sampler and chronological aggregation contract.
Each request retains MemAvailable start/min/end and swap start/peak/end; the canonical RAG summary
adds a resident-session view with first start, minimum, final state, MemAvailable end delta and
`swap_peak_delta_mib` (peak observed swap minus starting swap). These are evidence/diagnostic
improvements only; this contract does not introduce a new memory or swap failure threshold.

**Why:** Current RAG testing showed that per-case swap deltas can hide cumulative pressure while a
model remains resident, and external harnesses had to restore residency themselves after isolation.
State restoration and chronological resource visibility are therefore benchmark-integrity concerns,
not model-tuning features. Exact installed 0.11.3-1.4 subsequently confirmed the fail-closed boundary:
RAG quality passed 4/4, but Jina restoration failed because the embedding-only fallback supplied an
empty `/api/embed` input that Ollama 0.34 rejects. Release 1.5 fixes the probe payload without changing
the restoration contract or lane keep-alive policy. Reusing the existing client and sampler keeps the
pre-v1.0 implementation small and avoids a second lifecycle/telemetry framework.

**Retest only if:** Ollama changes its residency/load semantics, a benchmark legitimately needs to
leave residency changed by explicit operator request, or repeated BC-250 evidence justifies a new
resource-policy threshold. Do not turn the current diagnostic values into failures without that
evidence.


## DEC-019 — Keep Gemma E4B as the production RAG answer model on the 16 GiB profile

**Status:** ACTIVE — based on the completed 2026-09-19 BC-250 RAG campaign.

**Decision:** Use `bc250-office-documents` /
`prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl` as the production Open WebUI document/RAG answer
role for the current 16 GiB BC-250 profile. Keep `bc250-office-advanced` /
`prod-qwen35-9b-unsloth-q6-k` available for its separate higher-quality general-office role,
but do not present or preload Qwen 9B as an equivalent long-residency RAG default.

**Observed:** Corrected direct scoring gave Gemma 94/96 overall (95/96 fact, 96/96 language,
95/96 citation, 96/96 retrieval) and Qwen 93/96 overall (95/96 fact, 96/96 language, 94/96
citation, 96/96 retrieval); both also passed 8/8 abstention probes. The authenticated Open WebUI
short path passed 36/36 turns per model. The deciding evidence was sustained residency. Gemma
completed 42/42 continuous-residency turns with about 2.7 GiB MemAvailable remaining and no
safety/residency failure. Qwen had no quality failure before abort, but fell to roughly 338 MiB
minimum MemAvailable and reached the campaign's configured 512 MiB safety floor during the third
subrun.

**Interpretation:** This is a resource-safety/product-role decision, not a Qwen answer-quality
rejection. Gemma provides substantially more sustained-residency margin on the present 16 GiB UMA
profile while retaining comparable RAG quality. The 512 MiB value was the campaign's safety-abort
setting and does not replace the separate whole-appliance revalidation policy.

**Retest only if:** the BC-250 memory profile changes materially, Qwen/model/runtime memory behavior
changes materially, or a future document-answer model provides a clear product benefit that justifies
a new comparison. Do not reopen broad RAG answer-model tournaments without such a trigger.

## DEC-020 — Keep new Qwen3.8 27B candidates bounded and role-specific

**Status:** ACTIVE — candidates now have current BC-250 evidence; production roles remain unchanged.

**Decision:** Add ISTA GSQ/RCO IQ3_XXS as an opt-in deployability/RAG-oriented text experiment and
retune the already-packaged ISTA IQ3_S entry as the quality-first main-model experiment. IQ3_XXS
was introduced at 16K with the upstream Qwen3.8 non-thinking sampling profile and is intended to be
called with `think=false`; DEC-024 supersedes that initial context with the safer current 8K default.
IQ3_S starts at 8K with the upstream thinking profile and is intended for
`think=true`. Neither changes the production Gemma E4B RAG role, Open WebUI desired state or current
GPT-OSS/Qwen production roles. Vision projectors and MTP payloads are deliberately excluded from
these Ollama experiments so first BC-250 evidence isolates text-model deployability/quality.

Add `qwen3.8-27b-ymq-xs-ti-mtp` as a disabled/download-only native-MTP challenger to the existing
HauhauCS Qwen3.8 27B IQ2_M control. Keep both at 8192 context and draft depth 2 for the first device
comparison. Exact IDs remain the evidence contract; no convenience alias is added for the YMQ
challenger.

**Why:** ISTA currently publishes IQ3_XXS as a 10.1 GB strong all-round point and IQ3_S as an 11.8
GB recommended/task-lossless point. The YMQ XS-TI file is about 10.2 GB, close to the 10.32 GB
HauhauCS IQ2_M control, and provides a same-class architecture-aware mixed-precision MTP comparison.
These are explicit product questions, not production promotions: can a dense Qwen3.8 27B provide
useful quality/deployability on the 16 GiB appliance, and does the YMQ MTP quant improve the Qwen3.8
27B speed/quality tradeoff under matched runtime settings?

**Current evidence update:** YMQ XS-TI now passes BC-250 MTP Phase-1 qualification at 8K/depth 2
with deterministic baseline/MTP parity and clean safety/restoration. It showed faster baseline decode
and stronger absolute long-generation MTP throughput than the earlier HauhauCS evidence, but lower
observed memory headroom; do not equate smaller GGUF size with lower runtime memory. The IQ3_XXS 16K RAG follow-up then produced five correct cited answers before memory pressure
progressively collapsed to roughly 0.28 GiB MemAvailable and the safety harness aborted; unloading
recovered roughly 13.8 GiB. This rejects the 16K configuration on the current 16 GiB profile but is
not enough evidence to promote the model on quality. The two ISTA Ollama experiments remain opt-in
and still require role-specific product-quality/headroom qualification before any production
promotion.

**Retest only if:** an Ollama candidate is being considered for a production role or upstream
artifacts/runtime materially change. Final MTP package selection is recorded separately in DEC-026.



## DEC-021 — Treat MTP Phase 2 as optimization, not requalification

**Status:** SUPERSEDED BY DEC-026 — preserve as the pre-final-selection optimization record.

**Decision:** Treat `qwen3.5-9b-mtp`, `qwen3.6-27b-mtp` and
`qwen3.8-27b-hauhaucs-mtp` as Phase-1-qualified MTP configurations under the reviewed llama.cpp
Vulkan contract. Retire `qwen3.6-35b-a3b-mtp` from the active MTP catalog: the stock
8192-context / full-GPU configuration is a confirmed safety-fit failure before MTP inference, and
there is no current product-driven retest hypothesis. Preserve its exact definition in the
source-only MTP graveyard plus the historical model-run evidence. Phase 2 changes only the
draft-depth parameter family and is optimization of already working configurations.

Do not select a new draft-depth default from the first long Phase-2 sweep: that campaign accidentally
repeated catalog defaults and therefore provides repeatability/noise-floor evidence only. Require
approximately >=1.0% balanced improvement over the current catalog default before changing a depth,
with quality, completeness, safety, restoration and both 256/1024-token speedups passing. Tiny
sub-percent changes remain noise unless later evidence proves otherwise.

The package comparison harness must record catalog/requested/effective draft depth and prove the
requested MTP depth appears in the actual llama-server flags before inference evidence is accepted.
The corrected hardware canary already proved an override can reach effective depth 1; that canary
is plumbing evidence, not a depth-selection benchmark.

**Why:** The original three candidates and YMQ now demonstrate useful speculative decoding with
deterministic baseline/MTP parity. The corrected sweep answered the broad draft-depth question for
Qwen3.6 and HauhauCS and identified only one material unresolved default candidate: Qwen3.5 depth 2.
The 35B stock failure remains a baseline memory-fit limit rather than an MTP-performance result.

Corrected Phase-2 testing now supports keeping depth 2 for Qwen3.6 27B and HauhauCS Qwen3.8 27B.
Qwen3.5 depth 2 is the strongest exploratory candidate and exceeded the measured noise floor by a
material margin, but keep packaged depth 3 until confirmation-grade repeats are available if a
default change matters. YMQ XS-TI independently passes Phase-1 at depth 2; further YMQ depth tuning
is optional and only justified if preferred-role promotion is being considered.

**Retest only if:** changing Qwen3.5's package default requires confirmation-grade evidence, a
rigorous same-current-package YMQ/HauhauCS comparator is needed, YMQ is being promoted, the
model/quant/runtime changes materially, or a materially new product/hardware/runtime condition creates
a justified retest hypothesis. Do not rerun the retired 35B stock configuration unchanged.

## DEC-022 — Protect explicit credential files consistently

**Status:** ACTIVE — introduced in 0.11.3-1.7.

**Decision:** Any explicit package credential-file argument used for Open WebUI or Hugging Face
authentication must fail closed unless the target is a regular, non-empty file with no group/world
permission bits (normally mode `0600`). The RAG importer and model manager enforce the same contract
already used by Open WebUI setup/verification. Environment variables such as `OPEN_WEBUI_API_KEY`
and `HF_TOKEN` remain separate ephemeral credential inputs and are not subjected to filesystem
permission checks.

Do not silently chmod an operator-supplied secret and do not accept a permissive file merely because
the documentation recommends mode 0600. Report the path/mode problem without printing secret
contents.

**Why:** A source review found that Open WebUI setup/verification enforced private token files while
`bc250-rag-import` and `bc250-model --token-file` simply read them. The inconsistent implementation
made the package's credential-hygiene promise weaker at exactly the operator boundary where a leaked
API/HF token matters.

**Retest only if:** a supported credential provider requires a non-file secret transport, Fedora
permission semantics materially change, or a specific integration needs an explicitly documented
ACL-based alternative. Do not weaken the default private-file rule for convenience.


## DEC-023 — Keep MTP standalone and isolate Ollama residency explicitly

**Status:** ACTIVE — introduced in the final 0.11.3-1.7 source refinement.

**Decision:** Keep MTP as a standalone opt-in external llama.cpp runtime, not another persistent
Ollama/service lane. The model manager owns only catalog/provenance/source lifecycle for MTP. The
installer may show read-only MTP operational state, but MTP remains non-selectable by normal model
convergence and is never fetched implicitly.

Before any MTP llama.cpp launch, snapshot every reachable package Ollama lane and drain all resident
models so unified-memory headroom and performance are not contaminated. A direct operator
`bc250-run-mtp` owns the temporary lifecycle and restores the exact pre-run residency set on exit,
using each lane's configured/default keep-alive behavior. `bc250-compare-mtp` and specialist
qualification use `drain-only` isolation and intentionally leave Ollama cold afterward. Neither path
changes normal/agent service topology. Restoration failure on the direct path is a command failure.

**Why:** MTP competes for the same ~16 GiB UMA as Ollama. Warm Ollama residency can invalidate both
fit and throughput evidence. At the same time, turning MTP into another persistent service/mode would
add lifecycle complexity without a product requirement. The split preserves clean experimental
isolation while keeping normal operator use state-preserving.

**Retest only if:** the external llama.cpp runtime or Ollama unload/load APIs change, MTP becomes a
first-class product role, or real-device evidence shows restoration/isolation is unreliable.

## DEC-024 — Bound ISTA Qwen3.8 IQ3_XXS to 8K on the 16 GiB profile

**Status:** ACTIVE.

**Decision:** Change `exp-qwen38-27b-ista-gsq-rco-iq3-xxs` from 16K to 8K context while
keeping its model identity, verified GGUF, non-thinking sampling and opt-in experimental role
unchanged. Do not create a parallel `-8k` catalog identity for the same source artifact.

**Why:** Sustained RAG qualification on the BC-250 showed the 16K variant answering its first
five RAG cases correctly with citations while MemAvailable fell from roughly 3.17 GiB after early
residency to ~0.67 GiB after case 5 and ~0.28 GiB before the next request, where the safety harness
aborted. Unloading recovered roughly 13.8 GiB. The operator subsequently attempted an 8K duplicate definition for
the same GGUF; the cleaner green-field contract is one model identity with the safer current
context default, which also lets `apply` reuse the existing verified source without a re-download.

**Retest only if:** runtime/model memory behavior changes materially or a concrete product need
requires larger context with measured headroom.


## DEC-025 — Make companion shutdown self-exemption exact and keep public SSH protected

**Status:** ACTIVE — introduced in 0.11.3-1.8.

**Decision:** Treat either endpoint of an established connection on a protected port as activity,
using the final two `ss` fields rather than fixed column numbers. The public
`bc250-maintenance request-shutdown` path never exempts its caller: an interactive SSH session
therefore defers shutdown. The dedicated `bc250-power-control` forced-command identity preserves
OpenSSH's `SSH_CONNECTION` tuple through its exact sudo rule and invokes the package-internal
`request-shutdown-companion` path. Safe-power may ignore only that validated tuple; every second
SSH connection and all other protected activity still defer. After all guards pass, request the
system power action with systemd's non-blocking mode so the decision service can finish cleanly.

**Why:** Exact installed 1.7 device testing proved the fixed-field parser missed the local SSH
endpoint and began a poweroff during an active administrator session. Correcting the parser without
a companion-specific boundary would then make the Pi's own forced SSH session self-deferring. A
general `--ignore-ssh` switch would be too broad; the exact authenticated tuple keeps human sessions
protected while allowing the restricted control identity to request the same BC-250-owned policy.

**Retest only if:** OpenSSH/sudo environment handling, `ss` output semantics, the companion identity,
or the safe-power transport changes. The next exact installed current release must first prove public
SSH defer and healthy 40-CU return-code behavior. Companion-only/second-SSH and real idle S5/WOL are
required before unattended poweroff is enabled, not as automatic gates for unrelated releases.

## DEC-026 — Encode the final MTP selection in the existing catalog

**Status:** ACTIVE — final package-facing MTP policy from the completed BC-250 campaign.

**Decision:** Keep MTP standalone, disabled/download-only and outside normal installer/Open WebUI/
Ollama convergence. Use the existing MTP TOML catalog as the single runtime source for context,
draft and a deliberately small package-policy pair: `role` plus `recommendation`. The active set is:

```text
qwen3.5-9b-mtp             primary / fast         ctx 16384  draft 2
qwen3.8-27b-ymq-xs-ti-mtp  primary / general-27b  ctx 8192   draft 1
qwen3.8-27b-hauhaucs-mtp   alternative / specialist ctx 8192 draft 2
```

Retire `qwen3.6-27b-mtp` from active discovery while preserving its exact source definition and
positive historical qualification in the source-only graveyard. Keep `qwen3.6-35b-a3b-mtp` retired
for the already-proven stock-envelope memory-fit failure. Do not silently retarget ambiguous 27B
convenience aliases; remove them and require exact 27B IDs.

**Why:** Confirmation-grade Qwen3.5 testing selected depth 2: 256-token throughput was effectively
unchanged from depth 3 while 1024-token MTP throughput improved by about 9%, with higher acceptance
and slightly more memory headroom. YMQ depth 1 materially outperformed depth 2 at both reviewed
output sizes, kept about 2.8--3.0 GiB free-memory class and passed parity-quality checks. HauhauCS
retains a distinct short-output/parity niche. Qwen3.6 27B no longer has a strong package-facing niche
after the optimized Qwen3.8 results.

**Boundary:** `role` / `recommendation` are operator-presentation policy only. They do not alter
`enabled=false`, acquisition behavior, topology or automatic model selection. There is no benchmark
result ingestion, recommendation engine or automatic promotion/retirement state machine.

**Retest only if:** the external llama.cpp runtime/model artifacts/hardware envelope change
materially, or a concrete product workload shows the selected fast/general/specialist split is no
longer useful. A symmetric three-repeat YMQ depth-1 confirmation is optional evidence, not a release
gate.



## DEC-027 — Use the BC-250 reboot compatibility invocation for package-controlled reboot paths

**Status:** ACTIVE — exact-2.3 device evidence accepted; remaining pinned-upstream call patched in 0.11.3-2.4.

**Decision:** On BC-250 package paths that intentionally initiate a real reboot, do not invoke
`systemctl reboot`. Preserve the existing command contract where it is still appropriate, but use
`/usr/sbin/reboot` (operator-facing form: `sudo reboot`) because that invocation is repeatedly proven
reliable on the target appliance. Do not create a generic reboot wrapper merely to encode this rule.

The 2.3 repository-native source review found and changed the two persistent 40-CU enable/disable
`systemctl reboot` calls. Exact-2.3 installed-package acceptance then found a third reachable call
inside the pinned upstream CU live manager: its interactive CPU-core-unlock reboot prompt. That
upstream source is materialized only during RPM prep, so 2.4 corrects it through the existing
`patches/cu-live-manager-rpm-paths.patch`, replacing only that command with `/usr/sbin/reboot`. The
interactive prompt remains intact and upstream `--yes` remains non-rebooting.

**Why:** Exact installed 2.2 testing repeatedly distinguished `COMMAND=/usr/sbin/systemctl reboot`
from `COMMAND=/usr/sbin/reboot`. The former completed shutdown, started a new kernel and progressed
through substantial early boot before the retained journal ended and boot history recorded a crash;
the latter repeatedly reconstructed services, network, timers, firewalld, live 40/40 routing and a
clean authenticated verifier. Exact installed 2.3 again passed the supported `sudo reboot` path.
The evidence does not identify Tika, nginx, Ollama, networking, CU reconstruction, kernel restart or
generic systemd shutdown as the root cause, so the package change remains invocation-specific.

**Retest only if:** a future systemd/Fedora/hardware change proves `systemctl reboot` equivalent and
reliable on this appliance, or the package changes reboot ownership/contract. Exact 2.4 needs only a
bounded package/source-path check for the patched live-manager CPU-unlock workflow; do not
deliberately rerun the known-bad invocation merely to reproduce the failure again.

## DEC-028 — Make the Open WebUI product surface role-oriented and persist package policy

**Status:** ACTIVE — exact-2.3 Open WebUI investigation; implemented in 0.11.3-2.4.

**Decision:** Use the existing authenticated Open WebUI desired-state helper as the single package
authority for the persisted application values that define the BC-250 local-office contract. Keep
Arena disabled. Persist the existing local/offline defaults for external OpenAI, direct connections,
code execution/interpreter, memories and community sharing, and converge the upload size/count/
extension policy rather than relying only on fresh-database environment bootstrap values.

Keep the five production base models plus the dedicated task model active because package presets and
background tasks depend on them, but add package-owned workspace model overrides with
`meta.hidden=true` so the ordinary model selector presents curated office roles instead of
implementation details. Provider allowlisting remains a backend-availability mechanism; it is not
used as a substitute for UI hiding.

**Boundary:** This is an extension of the existing additive desired-state contract, not a second Open
WebUI configuration system. Unrelated operator models/users/prompts/knowledge remain untouched. Do
not add a custom Arena pool, model-order/default/pinning policy, CORS redesign, another provider/
service, direct DB edits or a generic configuration framework without a concrete product requirement.
`ui.enable_signup=false` remains the existing single-user bootstrap outcome rather than gaining a
second signup-control mechanism solely for this decision. Allowed-extension comparisons are
order-insensitive.

**Why:** Exact installed 2.3 product-path testing found the appliance functionally healthy but exposed
three ownership gaps: upstream-default Arena remained visible, raw production/task models were visible
alongside curated roles, and persisted upload/local-offline values could drift after database-side
administration without package status noticing. The supported Open WebUI APIs already expose all
three boundaries, so a small extension of current convergence is simpler and more honest than new
architecture.

**Retest only if:** Open WebUI changes its persisted config/model-override API semantics or the package
intentionally changes its role-based product surface. Exact 2.4 needs one bounded authenticated
apply/status/UI check plus harmless drift/reconvergence; it does not require another model campaign.

## DEC-029 — Keep pinned Open WebUI OpenAI-style adapter outside the external appliance contract

**Status:** ACTIVE — exact-2.3 attribution evidence; documented in 0.11.3-2.4.

**Decision:** Do not vendor-patch the pinned Open WebUI v0.11.3 container solely to make its
`/api/chat/completions` Ollama adapter a general external OpenAI-compatible BC-250 API. The package
uses that endpoint for bounded product-path testing, but does not advertise it as an external
integration contract. Package-owned callers that need a hard generation cap use Ollama-native nested
`options.num_predict`; keep the separately device-tested Open WebUI preset `params.max_tokens` path
unchanged.

Document the v0.11.3 limitations: root OpenAI-style `max_tokens` is not reliably propagated to Ollama,
`reasoning_tokens=0` can coexist with generated reasoning content, and Ollama length termination can
be surfaced as `finish_reason=stop`. Do not infer resource bounds or truncation/reasoning semantics
from those affected fields.

**Why:** Exact-device A/B attribution isolated these behaviors to the Open WebUI v0.11.3 adapter;
Ollama and the same models obeyed native `num_predict`. Carrying three container-code patches would
turn the appliance into an Open WebUI fork for a surface the package does not currently promise.
The safer pre-v1.0 boundary is explicit documentation plus native options in package-owned bounded
clients.

**Retest only if:** the appliance intentionally advertises Open WebUI's OpenAI-style endpoint as an
external contract, a newer pinned Open WebUI version is evaluated, or a package-owned caller starts
depending on root `max_tokens` / reasoning-token / finish-reason semantics. In that case qualify all
three adapter semantics together rather than fixing one field in isolation.



## DEC-030 — Retire failed long-run candidates and make pressure-heavy OWUI experiments admin-only

**Status:** ACCEPTED — 0.12.2-0.3 source policy; exact-device verification remains required.

**Context:** Corrected long-run scoring removed prior harness noise and left repeatable model-level
quality/resource signals. Experimental Gemma4 26B showed wrong/template-contaminated arithmetic and
output degeneration. Experimental LFM 8B reproduced the same DE→FR recommendation→obligation
strengthening as the production translator, so it is not a credible rollback solution. Qwen3.6 35B,
Qwen3.8 27B Unsloth and ISTA IQ3_S remained useful experiments but repeatedly operated with much
tighter UMA headroom than is desirable for routine ordinary-user selection. ISTA IQ3_XXS retained
the better deployability profile.

**Decision:**

- move Gemma4 26B and experimental LFM 8B to the source graveyard and add both identities to the
  installed retired-model catalog;
- remove the inactive legacy LFM Open WebUI preset and its dedicated quality-check wrappers; generic
  candidate screens remain available for deliberate archaeology;
- keep Qwen3.6 35B, Qwen3.8 27B Unsloth and ISTA IQ3_S package-managed in OWUI but
  admin/testing-only by default; keep ISTA IQ3_XXS as the ordinary-user 27B deployability comparison;
- on package-managed discovery records only, the package may remove its own historical `user:*:read`
  grant when changing a model to admin/testing-only, while preserving every unrelated administrator
  grant;
- normalize paired Markdown emphasis and Unicode presentation before semantic literal matching so
  formatting-only review noise does not become a model-quality defect.

**Boundary:** This does not alter production Gemma E2B/E4B, GPT-OSS Deep, lane architecture,
`OLLAMA_MAX_LOADED_MODELS=1`, or the no-generic-scheduler decision. Model/runtime acceptance remains
part of the new exact-device 0.12.2 campaign.
