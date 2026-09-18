ID: TRANSLATION-20260917-01
Status: SUPERSEDED — ADVANCED TO STAGE-2E
Package: 0.11.1-0.10.fc44
Exact models: current DE<->FR specialist/generalist/upper-bound pool; see this record plus `MODELS.md` and the dated translation handover
Role: German <-> French office translation
Tests actually run: repaired canonical short screen, confirmations, reasoning-policy retries, large-model upper-bound batches
Tests not run in this early campaign: Stage-2 harder corpus; those questions were subsequently addressed by `2026-09-17-translation-stage2e.md`.

Observed facts:
- The eight-case canonical screen is saturated: several materially different candidates reach 8/8.
- Translate-Gemma E4B is the strongest small specialist observed: 24/24 fresh canonical evidence and later 8/8 anchors.
- Ministral 8B confirmed 24/24 and is a real harder-corpus survivor.
- TIR Qwen3.5 9B, Qwen3.8 9B and Qwen3.5 Hauhaucs changed from reasoning-budget 0/8 to 8/8 with explicit think:false; request thinking policy is part of the test contract.
- Hunyuan-MT 7B remains viable but has a reproducible CHF preservation defect.
- Production LFM 8B reproduced known weaknesses at 6/8 and is a reference rather than the current quality leader.
- 27B/35B Qwen-family models can reach 8/8 but leave only about 116-228 MiB minimum MemAvailable while resident.

Resource/service results:
- Translate-Gemma representative late anchor: about 0.68 s warm mean and about 8.3 GiB minimum MemAvailable.
- Large Qwen upper bounds are quality comparators, not practical default deployment candidates on current headroom.

Interpretation:
- Short-screen 8/8 means advance, not promotion or equality.
- Direct foreground quality does not prove Open WebUI product-path reliability or concurrent residency.

Decision at the time:
- NO PRODUCTION CHANGE from this early screen.
- Advance Translate-Gemma E4B, Ministral 8B, TIR Qwen3.5 9B non-thinking and Qwen3.6 35B upper bound to harder discrimination.

Superseding result:
- Stage-2E selected Translate-Gemma E4B; see `2026-09-17-translation-stage2e.md` and DEC-009/DEC-010.

Retest only if:
- Proceed with the prepared harder DE<->FR corpus and then narrow to 2-3 product-path finalists.

Evidence tarball: multiple batch bundles summarized in TRANSLATION_MODEL_TESTING_HANDOVER_2026-09-17.
Restoration status: direct foreground runs left model definitions unchanged and recovered the main lane between models.
Credential-scan status: current harness method requires privacy scrub/scan before bundling.
Caveats: English is secondary and not part of current candidate ranking.
